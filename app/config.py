"""Settings from environment variables - the desktop launcher (desktop/launcher.py) sets them."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR") or Path.home() / "Documents" / "Dotationslisten")

try:  # repo root (development) or the bundle's resources (Mac/Windows app)
    VERSION = (Path(__file__).resolve().parent.parent / "VERSION").read_text("utf-8").strip()
except OSError:
    VERSION = "dev"

EINGANG = DATA_DIR / "eingang"      # scanner target folder (SMB share)
ARBEIT = DATA_DIR / "arbeit"        # one folder per Vorgang
AUSGANG = DATA_DIR / "ausgang"      # filled workbooks
ARCHIV = DATA_DIR / "archiv"        # original scans after intake
VORLAGE_DIR = DATA_DIR / "vorlage"
VORLAGE = VORLAGE_DIR / "vorlage.xlsx"          # converted template
VORLAGE_LEER = VORLAGE_DIR / "vorlage-leer.xlsx"  # template without the Muster example data
VN_DIR = DATA_DIR / "verwendungsnachweis"
VN_BASIS = VN_DIR / "basis.xlsx"    # the year's Verwendungsnachweis as filled so far (uploaded)
VN_STAND = VN_DIR / "stand.json"    # result of the last calculation
VN_SETTINGS = VN_DIR / "einstellungen.json"  # Zuwendung / Mindestanteil set in the app

# Notice about new releases (GitHub releases API, once a day)
UPDATE_CHECK = os.environ.get("UPDATE_CHECK", "1") != "0"
UPDATE_REPO = os.environ.get("UPDATE_REPO", "rvalley98/dotationslisten")
UPDATE_URL = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
UPDATE_PAGE = f"https://github.com/{UPDATE_REPO}/releases/latest"

# Recognition: "ollama" or "none" (manual entry only)
RECOGNIZER = os.environ.get("RECOGNIZER", "ollama")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5vl:7b")
# CPU inference takes minutes per page
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "1800"))

POLL_SECONDS = float(os.environ.get("POLL_SECONDS", "5"))
SCAN_DPI = int(os.environ.get("SCAN_DPI", "200"))

SCAN_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}

# External programs. The desktop apps set TESSERACT (bundled) and find LibreOffice in its default
# install folder (a Finder/Explorer-launched app has no useful PATH), otherwise the PATH.
# LibreOffice is optional: only .xls files need it - the sums are calculated by app/formulas.py.
_SOFFICE_KNOWN = ("/Applications/LibreOffice.app/Contents/MacOS/soffice",
                  str(Path.home() / "Applications/LibreOffice.app/Contents/MacOS/soffice"),
                  *(str(Path(os.environ.get(v, "")) / "LibreOffice" / "program" / "soffice.exe")
                    for v in ("ProgramFiles", "ProgramFiles(x86)") if os.environ.get(v)))
TESSERACT = os.environ.get("TESSERACT") or shutil.which("tesseract") or "tesseract"
SOFFICE = (os.environ.get("SOFFICE") or shutil.which("soffice")
           or next((p for p in _SOFFICE_KNOWN if Path(p).exists()), "soffice"))


def soffice_available() -> bool:
    """LibreOffice calculates the sums (Verwendungsnachweis) and converts .xls files."""
    return Path(SOFFICE).exists() or shutil.which(SOFFICE) is not None


def ensure_dirs() -> None:
    for d in (EINGANG, ARBEIT, AUSGANG, ARCHIV, VORLAGE_DIR, VN_DIR):
        d.mkdir(parents=True, exist_ok=True)
