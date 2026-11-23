"""Count the signed lines on the Tagegeld page by image analysis.

The vision model miscounts signatures, so this uses the printed layout instead: two columns
of five lines, each labelled "Ort, Datum, Unterschrift" below the line. Tesseract finds the
printed labels; a line counts as signed when there is ink just above its label. A label that
is crossed by a signature is often not found - its position is inferred from the even
spacing of the other labels.
"""

from __future__ import annotations

import csv
import io
import statistics

from PIL import Image

from . import config as C

ROWS = 5                 # signature lines per column in the template
INK_THRESHOLD = 140      # grey value below which a pixel counts as ink
SIGNED_FRACTION = 0.02   # share of ink pixels in the field above a label -> signed
# field above a label, relative to the page: x around the label centre, y above its top
FIELD_LEFT, FIELD_RIGHT = 0.17, 0.20
FIELD_TOP, FIELD_BOTTOM = 0.035, 0.004


def _label_tops(image: Image.Image) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """(left column, right column): (x centre, top) of every "Datum" label in the lower half."""
    w, h = image.size
    from .pages import _tesseract
    out = _tesseract(image, "-l", "deu", "--psm", "11", "tsv")
    left, right = [], []
    for r in csv.DictReader(io.StringIO(out), delimiter="\t", quoting=csv.QUOTE_NONE):
        if "datum" not in (r.get("text") or "").lower():
            continue
        x, top, width = int(r["left"]), int(r["top"]), int(r["width"])
        if top < h * 0.5:
            continue
        cx = x + width // 2
        (left if cx < w / 2 else right).append((cx, top))
    return sorted(left, key=lambda p: p[1]), sorted(right, key=lambda p: p[1])


def _complete(col: list[tuple[int, int]], other: list[tuple[int, int]], step: float) -> list[tuple[int, int]]:
    """Fill in labels that were not found: gaps inside the column and missing first/last rows
    (the two columns are printed on the same rows)."""
    if not col:  # a whole column unreadable: do not guess
        return []
    out = [col[0]]
    for cx, top in col[1:]:
        while top - out[-1][1] > 1.5 * step:  # gap -> missing row(s) in between
            out.append((cx, round(out[-1][1] + step)))
        out.append((cx, top))
    if other:
        while len(out) < ROWS and out[0][1] - other[0][1] > step / 2:
            out.insert(0, (out[0][0], round(out[0][1] - step)))
        while len(out) < ROWS and other[-1][1] - out[-1][1] > step / 2:
            out.append((out[-1][0], round(out[-1][1] + step)))
    return out[:ROWS]


def count(image: Image.Image) -> int | None:
    """Number of signed lines, or None if the signature block cannot be found."""
    grey = image.convert("L")
    w, h = grey.size
    left, right = _label_tops(grey)
    diffs = [b[1] - a[1] for col in (left, right) for a, b in zip(col, col[1:])]
    diffs = [d for d in diffs if d > h * 0.02]
    if not diffs:
        return None
    base = min(diffs)
    step = statistics.median(d for d in diffs if d < 1.5 * base)
    ink = grey.point(lambda v: 255 if v < INK_THRESHOLD else 0)
    signed = 0
    for col, other in ((left, right), (right, left)):
        for cx, top in _complete(col, other, step):
            box = (max(0, cx - int(w * FIELD_LEFT)), max(0, top - int(h * FIELD_TOP)),
                   min(w, cx + int(w * FIELD_RIGHT)), max(0, top - int(h * FIELD_BOTTOM)))
            area = (box[2] - box[0]) * (box[3] - box[1])
            if area and ink.crop(box).histogram()[255] / area > SIGNED_FRACTION:
                signed += 1
    return signed
