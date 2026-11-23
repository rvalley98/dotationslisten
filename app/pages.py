"""Scanned file -> page images, with orientation fix, blank detection and classification.

Classification reads the printed title in the top part of a page with Tesseract (printed text,
fast and local); handwriting is never read here.
"""

from __future__ import annotations

import difflib
import io
import re
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import Image, ImageOps

from . import config as C
from . import tools as T

# page kind -> words of the printed title (normalized, lower case)
TITLES: dict[str, tuple[str, ...]] = {
    "abrechnung": ("veranstaltungsabrechnung",),
    "teilnehmer": ("teilnehmerliste",),
    "tagegeld": ("tagegeld", "aufwandsvergütung"),
    "fahrtkosten": ("fahrtkosten",),
    "tauchprotokoll": ("tauchprotokoll",),
    "belege": ("belege",),
}
# Fallback when the printed title is unreadable (e.g. the Tagegeld title sits in a grey
# screened box): words found anywhere on the page that only this sheet has. "tagegeld" alone
# is not enough - the Abrechnungsbogen mentions "Tagegelder" too.
FULLPAGE_MARKERS: dict[str, tuple[str, ...]] = {
    "abrechnung": ("veranstaltungsbezogene", "teilnehmergebühren"),
    "tagegeld": ("tagegeld", "abreisetag"),
}

KIND_LABELS = {
    "abrechnung": "Abrechnungsbogen",
    "teilnehmer": "Teilnehmerliste",
    "tagegeld": "Tagegeld / Aufwandsvergütung",
    "fahrtkosten": "Fahrtkosten",
    "tauchprotokoll": "Tauchprotokoll",
    "belege": "Belege (wird nicht übernommen)",
    "folgeseite": "Folgeseite / ohne Titel",
    "manuell": "Manuell erfasst",
    "import": "Aus Excel importiert",
    "leer": "Leerseite",
}


@dataclass
class Page:
    image: Image.Image
    kind: str
    rotation: int = 0


def load_pages(path: Path) -> list[Image.Image]:
    if path.suffix.lower() == ".pdf":
        pdf = pdfium.PdfDocument(str(path))
        try:
            return [_pdf_page(page) for page in pdf]
        finally:
            pdf.close()
    images = []
    with Image.open(path) as im:  # multi-page TIFF
        i = 0
        while True:
            try:
                im.seek(i)
            except EOFError:
                break
            images.append(ImageOps.exif_transpose(im.copy()).convert("RGB"))
            i += 1
    return images


def _pdf_page(page) -> Image.Image:
    """A scanner PDF page is one full-page image: take it as is and scale it down with Lanczos
    (cleaner than rendering - the printed titles must stay readable for Tesseract).
    Anything else (rotated page, text, several objects) is rendered."""
    w_pt, h_pt = page.get_size()
    size = (round(w_pt / 72 * C.SCAN_DPI), round(h_pt / 72 * C.SCAN_DPI))
    objs = list(page.get_objects())
    if len(objs) == 1 and objs[0].type == pdfium_c.FPDF_PAGEOBJ_IMAGE and page.get_rotation() == 0:
        left, bottom, right, top = objs[0].get_pos()
        if abs(right - left - w_pt) < w_pt * 0.02 and abs(top - bottom - h_pt) < h_pt * 0.02:
            try:
                image = objs[0].get_bitmap(render=False).to_pil().convert("RGB")
                return image.resize(size, Image.LANCZOS) if image.width > size[0] else image
            except Exception:
                pass  # unusual image encoding: render instead
    return page.render(scale=C.SCAN_DPI / 72).to_pil().convert("RGB")


def is_blank(image: Image.Image) -> bool:
    """Empty duplex back side: almost no dark pixels (ignoring the scanner's border)."""
    g = image.convert("L")
    w, h = g.size
    g = g.crop((int(w * 0.05), int(h * 0.05), int(w * 0.95), int(h * 0.95))).resize((400, 560))
    dark = sum(g.histogram()[:160])
    return dark / (400 * 560) < 0.002


def _tesseract(image: Image.Image, *args: str) -> str:
    """Tesseract on an image handed over through stdin (no temp file: Leptonica rewrites /tmp
    paths on macOS). stderr is ignored - Leptonica prints harmless noise there, partly binary."""
    buf = io.BytesIO()
    image.save(buf, "PNG")
    r = T.run([C.TESSERACT, "stdin", "stdout", *args], input=buf.getvalue(),
                       capture_output=True, timeout=120)
    return r.stdout.decode("utf-8", "replace")


def orientation(image: Image.Image) -> tuple[int, float]:
    """(degrees to rotate counter-clockwise (PIL convention) so the text is upright, confidence)."""
    out = _tesseract(image, "--psm", "0")
    m = re.search(r"Rotate:\s*(\d+)", out)
    conf = re.search(r"Orientation confidence:\s*([\d.]+)", out)
    if not m:
        return 0, 0.0
    # tesseract: rotate clockwise by N degrees -> PIL rotate(-N)
    return (-int(m[1])) % 360, float(conf[1]) if conf else 0.0


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zäöüß]{4,}", text.lower())


def classify_text(text: str, titles: dict[str, tuple[str, ...]] = TITLES) -> str | None:
    words = _words(text)
    for kind, title in titles.items():
        if all(difflib.get_close_matches(t, words, n=1, cutoff=0.8) for t in title):
            return kind
    return None


def classify(image: Image.Image) -> str:
    w, h = image.size
    top = image.crop((0, 0, w, int(h * 0.2)))
    kind = classify_text(_tesseract(top, "-l", "deu", "--psm", "3"))
    if kind is None:
        kind = classify_text(_tesseract(image, "-l", "deu", "--psm", "3"), FULLPAGE_MARKERS)
    return kind or "folgeseite"


def analyse(image: Image.Image) -> Page:
    if is_blank(image):
        return Page(image, "leer")
    rot, conf = orientation(image)
    if rot and conf >= 1.0:
        image = image.rotate(rot, expand=True)
    else:
        rot = 0
    kind = classify(image)
    if kind == "folgeseite" and conf < 5.0:
        # orientation detection failed on a sparse page: try upside down once
        flipped = image.rotate(180, expand=True)
        k2 = classify(flipped)
        if k2 != "folgeseite":
            return Page(flipped, k2, 180)
    return Page(image, kind, rot)
