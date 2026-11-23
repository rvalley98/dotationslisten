import os
from pathlib import Path

import pytest

from app import config as C

DATA = Path(os.environ.get("DATA_DIR", "/data"))


@pytest.fixture(scope="session")
def template_xlsx() -> Path:
    path = DATA / "vorlage" / "vorlage.xlsx"
    if not path.exists():
        pytest.skip("Vorlage fehlt (data/vorlage/vorlage.xlsx)")
    return path


@pytest.fixture(scope="session")
def vn_xlsx() -> Path:
    path = DATA / "verwendungsnachweis" / "original.xlsx"
    if not path.exists():
        pytest.skip("Verwendungsnachweis fehlt (data/verwendungsnachweis/original.xlsx)")
    return path


@pytest.fixture()
def data_dir(tmp_path, monkeypatch, template_xlsx):
    for name, sub in [("EINGANG", "eingang"), ("ARBEIT", "arbeit"), ("AUSGANG", "ausgang"),
                      ("ARCHIV", "archiv"), ("VORLAGE_DIR", "vorlage")]:
        monkeypatch.setattr(C, name, tmp_path / sub)
    monkeypatch.setattr(C, "VORLAGE", tmp_path / "vorlage" / "vorlage.xlsx")
    monkeypatch.setattr(C, "VORLAGE_LEER", tmp_path / "vorlage" / "vorlage-leer.xlsx")
    C.ensure_dirs()
    from app import workbook as W
    W.blank_template(template_xlsx, C.VORLAGE_LEER)
    return tmp_path
