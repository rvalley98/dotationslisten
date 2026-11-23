"""Smoke test of a BUILT app (CI, after PyInstaller): server answers, a scanned PDF dropped into
the scanner folder is read (PDFium) and classified (bundled Tesseract over stdin + deu data).
With SMOKE_EXPECT_OLLAMA=1 also: the bundled Ollama server was started and answers (no model
is downloaded - that is several GB).

    python desktop/smoke_test.py <data dir> [base url]
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.read()


def wait(what: str, check, seconds: float) -> object:
    end = time.time() + seconds
    while time.time() < end:
        try:
            result = check()
            if result:
                return result
        except Exception:
            pass
        time.sleep(1)
    raise SystemExit(f"FEHLER: {what} (nach {seconds:.0f} s)")


def scan_pdf(path: Path) -> None:
    """A4 page at 200 dpi with a printed title, like a scanned Veranstaltungsabrechnung."""
    im = Image.new("RGB", (1654, 2339), "white")
    d = ImageDraw.Draw(im)
    d.text((150, 120), "Veranstaltungsabrechnung", fill="black", font=ImageFont.load_default(size=80))
    body = ImageFont.load_default(size=40)
    for i, line in enumerate(["Veranstaltungsbezogene Kosten", "Teilnehmergebühren", "Thema: Test",
                              "Ort: Musterstadt", "Datum: 01.01.2026"]):
        d.text((150, 500 + i * 90), line, fill="black", font=body)
    im.save(path, "PDF", resolution=200)


def main(data: Path, base: str) -> None:
    health = json.loads(wait("Server antwortet nicht", lambda: get(f"{base}/health"), 90))
    print("health:", health)
    assert health["app"] == "dotationslisten", health
    if os.environ.get("SMOKE_EXPECT_OLLAMA") == "1":
        assert health.get("ollama") == "mitgeliefert", f"mitgeliefertes Ollama nicht gewählt: {health}"
        v = json.loads(wait("mitgeliefertes Ollama antwortet nicht", lambda: get(f"{health['ollama_url']}/api/version"), 60))
        print("Ollama:", v)

    eingang = data / "eingang"
    eingang.mkdir(parents=True, exist_ok=True)
    tmp = data / "scan.tmp"
    scan_pdf(tmp)
    tmp.replace(eingang / "Test-Scan.pdf")

    def job():
        for p in (data / "arbeit").glob("*/job.json"):
            j = json.loads(p.read_text("utf-8"))
            if j["pages"] and all("kind" in pg for pg in j["pages"]):
                return j
        return None

    j = wait("Scan wurde nicht eingelesen", job, 180)
    kinds = [p["kind"] for p in j["pages"]]
    print("Vorgang:", j["id"], kinds)
    assert kinds == ["abrechnung"], f"Seite falsch zugeordnet: {kinds} (Tesseract/Sprachdaten?)"
    assert (data / "archiv").exists() and not (eingang / "Test-Scan.pdf").exists(), "Scan nicht archiviert"
    page = get(f"{base}/").decode("utf-8")
    assert j["id"] in page or "Test-Scan" in page, "Vorgang fehlt auf der Startseite"
    assert health.get("version") and health["version"] in page, "Version fehlt auf der Seite"
    print("OK")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8765")
