"""External programs (Tesseract, LibreOffice) - the same on macOS, Windows and Linux."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from . import config as C

# Windows: no console window flashing up for every call from the windowed app
_NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def run(args: list[str], **kw: Any) -> subprocess.CompletedProcess:
    kw.setdefault("stdin", None if "input" in kw else subprocess.DEVNULL)
    return subprocess.run(args, **_NO_WINDOW, **kw)


def soffice_convert(src: Path, outdir: Path, fmt: str = "xlsx") -> Path:
    """src -> outdir/<stem>.<fmt> with LibreOffice (own profile: works while LibreOffice is open)."""
    if not C.soffice_available():
        raise RuntimeError("LibreOffice ist nicht installiert (kostenlos: libreoffice.org)")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        run([C.SOFFICE, "--headless", f"-env:UserInstallation={Path(profile).as_uri()}", "--convert-to", fmt,
             "--outdir", str(outdir), str(src)], check=True, capture_output=True, timeout=300)
    out = outdir / f"{src.stem}.{fmt}"
    if not out.exists():
        raise RuntimeError(f"LibreOffice hat {src.name} nicht umgewandelt")
    return out
