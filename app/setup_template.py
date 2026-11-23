"""Prepare the template once: .xls (password-less Excel protection is handled by LibreOffice)
-> vorlage.xlsx -> vorlage-leer.xlsx (input cells emptied).

    python -m app.setup_template "20250105 Muster.xls"
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from . import config as C
from . import tools as T
from . import workbook as W


def prepare(src: Path) -> None:
    C.ensure_dirs()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        if src.suffix.lower() == ".xlsx":
            xlsx = tmp_path / "vorlage.xlsx"
            shutil.copy(src, xlsx)
        else:
            original = tmp_path / ("vorlage-original" + src.suffix.lower())
            shutil.copy(src, original)
            xlsx = T.soffice_convert(original, tmp_path)
            shutil.copy(original, C.VORLAGE_DIR / original.name)
        W.blank_template(xlsx, tmp_path / "leer.xlsx")  # validates the field map against the file
        shutil.copy(xlsx, C.VORLAGE)
        shutil.copy(tmp_path / "leer.xlsx", C.VORLAGE_LEER)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    prepare(Path(sys.argv[1]))
    print(f"Vorlage bereit: {C.VORLAGE_LEER}")
