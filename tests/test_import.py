"""Existing Abrechnungen from Excel -> Vorgänge (inverse of workbook.fill)."""

import datetime as dt

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app import fields as F
from app import importer
from app import jobs as J
from app import workbook as W
from tests.test_fill import DATA


def test_to_raw():
    assert importer.to_raw(dt.datetime(2026, 10, 17), F.DATE) == "17.10.2026"
    assert importer.to_raw(dt.time(7, 30), F.TIME) == "07:30"
    assert importer.to_raw(dt.timedelta(hours=21, minutes=30), F.TIME) == "21:30"
    assert importer.to_raw(0.3125, F.TIME) == "07:30"
    assert importer.to_raw(12.5, F.MONEY) == "12,50"
    assert importer.to_raw(1, F.PERCENT) == "100"
    assert importer.to_raw(0.5, F.PERCENT) == "50"
    assert importer.to_raw(1321013.0, F.INT) == "1321013"
    assert importer.to_raw("=A1", F.TEXT) == ""


def test_round_trip_through_the_template(template_xlsx, tmp_path):
    """fill -> import gives the same values as Excel sees them."""
    blank = tmp_path / "blank.xlsx"
    W.blank_template(template_xlsx, blank)
    W.fill(blank, DATA, tmp_path / "a.xlsx")
    data = importer.read_data(openpyxl.load_workbook(tmp_path / "a.xlsx"))
    assert set(data) == {"abrechnung", "teilnehmer", "tagegeld", "fahrtkosten_1"}
    for key, sd in DATA.items():
        sheet = F.SHEETS_BY_KEY[key]
        for f in sheet.fields:
            raw = (sd.get("fields") or {}).get(f.key)
            if raw is None and f.default is None:
                continue
            want = W.convert(raw if raw is not None else f.default, f.type, f.options)
            assert W.convert(data[key]["fields"][f.key], f.type, f.options) == want, (key, f.key)
        for t in sheet.tables:
            for i, row in enumerate((sd.get("tables") or {}).get(t.key) or []):
                for k, _l, _c, typ in t.columns:
                    assert W.convert(data[key]["tables"][t.key][i][k], typ) == W.convert(row.get(k), typ)


def test_web_import_xls_and_duplicate(template_xlsx, data_dir, monkeypatch):
    """The Muster of the template (as .xlsx) imports with its example values; a second upload is skipped."""
    monkeypatch.setenv("WORKER", "0")
    from app import main

    with TestClient(main.app) as client:
        content = template_xlsx.read_bytes()
        client.post("/import", files=[("files", ("Muster.xlsx", content, "application/octet-stream")),
                                      ("files", ("kaputt.xlsx", b"no excel", "application/octet-stream"))])
        assert main.last_import["ok"] == ["Muster.xlsx"] and len(main.last_import["errors"]) == 1
        job = next(j for j in J.all_jobs() if j["source"] == "Import: Muster.xlsx")
        muster = openpyxl.load_workbook(template_xlsx)["Abrechnungsbogen"]
        assert job["data"]["abrechnung"]["fields"]["thema"] == muster["B3"].value
        assert set(job["reviewed"]) == {p["sheet"] for p in job["pages"]}
        assert "Aus Excel importiert" in client.get(f"/vorgang/{job['id']}/seite/1").text

        client.post("/import", files={"files": ("Muster-kopie.xlsx", content, "application/octet-stream")})
        assert main.last_import["duplicate"] == ["Muster-kopie.xlsx"]

        client.post(f"/vorgang/{job['id']}/export", data={"back": "1"})
        assert J.load(job["id"])["export"]["summen"]["gesamt"] is not None


@pytest.mark.parametrize("edit", ["tagegelder_geleert", "teilnehmer_leer", "tagegelder_getippt", "tagegeld_eine_zeile_hoeher"])
def test_import_is_the_excel_and_keeps_its_totals(template_xlsx, data_dir, monkeypatch, edit):
    """The imported file is the Vorgang's Excel (with its totals); a later "Excel erzeugen"
    gives the same totals even where the file was changed by hand against the formulas."""
    import copy
    from app import config as C
    from app import verwendungsnachweis as VN

    monkeypatch.setenv("WORKER", "0")
    from app import main

    data = copy.deepcopy(DATA)
    data["tagegeld"] = {"fields": {"ausserhalb_gemeinde": "JA", "teilnehmer_tagegeld": "2"}}
    src = data_dir / "abrechnung.xlsx"
    W.fill(C.VORLAGE_LEER, data, src)
    wb = openpyxl.load_workbook(src)
    if edit == "tagegelder_geleert":
        wb["Abrechnungsbogen"]["G17"].value = None
    elif edit == "teilnehmer_leer":
        wb["Tagegeld_Aufwandsvergütung"]["F15"].value = None
    elif edit == "tagegelder_getippt":
        wb["Abrechnungsbogen"]["G17"].value = 30
    else:  # older files: the Tagegeld link in "Gezahlte Aufwandvergütungen", Tagegelder empty
        wb["Abrechnungsbogen"]["G16"].value = "=Tagegeld_Aufwandsvergütung!H19"
        wb["Abrechnungsbogen"]["G17"].value = None
    wb.save(src)
    want = VN.abrechnung_summen(src)["gesamt"]

    job_id = importer.import_file(src, "abrechnung.xlsx")
    job = J.load(job_id)
    assert job["export"]["summen"]["gesamt"] == want
    assert (C.AUSGANG / job["export"]["file"]).read_bytes() == src.read_bytes()
    assert not main._needs_export(job)
    assert importer.import_file(src, "nochmal.xlsx") is None

    main._export_sync(job_id)  # e.g. after a correction
    assert J.load(job_id)["export"]["summen"]["gesamt"] == want
