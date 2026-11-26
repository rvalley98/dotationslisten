"""Finished Vorgänge -> rows in the Kosten sheet of the Verwendungsnachweis; LibreOffice
calculates the summary with the file's own formulas."""

import shutil

import openpyxl
import pytest

from app import config as C
from app import raumkosten as RK
from app import verwendungsnachweis as VN
from app import workbook as W


@pytest.fixture()
def basis(tmp_path, monkeypatch, vn_xlsx):
    monkeypatch.setattr(C, "VN_BASIS", tmp_path / "basis.xlsx")
    monkeypatch.setattr(C, "VN_DIR", tmp_path)
    monkeypatch.setattr(C, "VN_SETTINGS", tmp_path / "einstellungen.json")
    monkeypatch.setattr(C, "VN_RAUMKOSTEN", tmp_path / "raumkosten.json")
    shutil.copy(vn_xlsx, C.VN_BASIS)
    return C.VN_BASIS


def row(id_, datum, thema, art="Übung", gesamt=100.0, anteil=1):
    return {"id": id_, "datum": datum, "thema": thema, "art": art, "ort": "Greven",
            "gliederungsnummer": 1321013, "gesamt": gesamt, "anteil": anteil, "kats": gesamt * anteil}


def test_rows_go_into_free_rows_and_sums_follow(basis, tmp_path):
    before = W.recalculate(basis)["Verwendungsnachweis"]
    kosten = openpyxl.load_workbook(basis)["Kosten"]
    first_free = next(r for r in range(VN.FIRST_ROW, VN.LAST_ROW) if VN._is_free(kosten, r))

    out = tmp_path / "vn.xlsx"
    result = VN.generate([row("a", "2026-10-17", "KatS Bezirksübung", gesamt=108.8),
                          row("b", "2026-10-18", "KatS Ausbildung", art="Ausbildung", gesamt=50, anteil=0.5)], out)

    assert [w["row"] for w in result["written"]] == [first_free, first_free + 1]
    s = result["summary"]
    assert s["uebungen"] == pytest.approx(before["H37"].value + 108.8)
    assert s["ausbildung"] == pytest.approx(before["H38"].value + 25)
    assert s["verwaltung"] == pytest.approx(before["H39"].value)
    ws = openpyxl.load_workbook(out)["Kosten"]
    assert [ws.cell(first_free, c).value for c in (4, 5, 6, 7, 9, 10)] == [1321013, "Übung", "KatS Bezirksübung", "Greven", 108.8, 1]
    assert ws.cell(first_free, 8).value.date().isoformat() == "2026-10-17"
    assert ws.cell(first_free, 11).value == f"=I{first_free}*J{first_free}"  # formula untouched
    assert ws.protection.sheet  # sheet protection kept


def test_rows_already_in_the_base_are_not_duplicated(basis, tmp_path):
    kosten = openpyxl.load_workbook(basis)["Kosten"]
    datum, thema = kosten["H88"].value, kosten["F88"].value  # an entry typed by hand
    result = VN.generate([row("dup", datum.date().isoformat(), thema.upper()),
                          row("x", "2026-11-01", "Neu"), row("x2", "2026-11-01", "neu")], tmp_path / "vn.xlsx")
    assert result["skipped"] == ["dup", "x2"]
    assert [w["id"] for w in result["written"]] == ["x"]


def test_settings_zuwendung_and_mindestanteil(basis, tmp_path):
    rows = [row("a", "2026-10-17", "Übung", gesamt=1000)]
    default = VN.generate(rows, tmp_path / "a.xlsx")
    assert default["einstellungen"] == {"zuwendung": None, "mindestanteil": 0.6}

    VN.save_settings(10_000, 0.95)
    s = VN.generate(rows, tmp_path / "b.xlsx")["summary"]
    assert s["zuwendung"] == 10_000
    assert s["anteil_ua"] == pytest.approx((s["uebungen"] + s["ausbildung"]) / 10_000)
    assert s["pruefung_anteil"] == ("i.O." if s["anteil_ua"] >= 0.95 else "zu gering")
    ws = openpyxl.load_workbook(tmp_path / "b.xlsx")["Verwendungsnachweis"]
    assert ws["J46"].value == '=IF(L37>=0.95,"i.O.","zu gering")' and "95%" in ws["A46"].value
    if C.soffice_available():  # the rewritten check calculates the same in LibreOffice
        assert W.recalculate(tmp_path / "b.xlsx")["Verwendungsnachweis"]["J46"].value == s["pruefung_anteil"]
    with pytest.raises(ValueError):
        VN.save_settings(None, 1.5)


def test_basis_with_other_layout_is_rejected(basis, tmp_path):
    wb = openpyxl.load_workbook(basis)
    wb["Verwendungsnachweis"]["A37"] = "Sonstiges"
    wb.save(tmp_path / "anders.xlsx")
    with pytest.raises(ValueError, match="Aufbau"):
        VN.check_basis(tmp_path / "anders.xlsx")
    VN.check_basis(basis)


def test_entry_status():
    job = {"id": "j", "created": "", "source": "s", "data": {}, "reviewed": ["abrechnung"],
           "pages": [{"n": 1, "sheet": "abrechnung"}, {"n": 2, "sheet": "tagegeld"}]}
    assert VN.entry(job)["status"] == "noch kein Excel erzeugt"
    job["export"] = {"at": "x", "summen": {"art": "Übung", "datum": "2026-10-17", "thema": "T"}}
    assert VN.entry(job)["status"] == "noch nicht alle Blätter geprüft"
    job["reviewed"].append("tagegeld")
    assert VN.entry(job, 2026)["status"] == VN.FINAL
    assert VN.entry(job, 2025)["status"] == "nicht aus 2025"
    job["export"]["veraltet"] = True
    assert VN.entry(job, 2026)["status"].startswith("nach dem Export geändert")


def test_raumkosten_edited_in_the_app(basis, tmp_path):
    """A Verwaltung room (Gebäude 1, Raum 1): its KatS share changes the Verwaltung line; the
    uploaded file stays as it is; reset = the values of the file again."""
    out = tmp_path / "vn.xlsx"
    start = VN.generate([], out)
    raeume = RK.current()
    assert raeume == RK.read(openpyxl.load_workbook(basis)) and RK.saved() is None

    raeume[0]["raeume"][0].update(raum="Büro", nutzung="Verwaltung", groesse=10.0, miete_qm=5.0, anteil=1.0)
    raeume[0]["flaeche"] = raeume[0]["flaeche"] or 100.0
    old = start["raumkosten_kosten"][RK.room_ref(0, 0)] or 0
    RK.save(raeume)
    res = VN.generate([], out)
    room = res["raumkosten_kosten"][RK.room_ref(0, 0)]
    assert room == pytest.approx(10 * 5 * 12 + (raeume[0]["nebenkosten"] or 0) * 10 / raeume[0]["flaeche"])
    assert res["summary"]["verwaltung"] == pytest.approx((start["summary"]["verwaltung"] or 0) - old + room)
    assert RK.read(openpyxl.load_workbook(basis)) != raeume  # basis unchanged

    RK.reset()
    assert VN.generate([], out)["summary"]["verwaltung"] == pytest.approx(start["summary"]["verwaltung"] or 0)


def test_raumkosten_form_round_trip_and_checks():
    raeume = [{k: None for k, *_ in RK.GEBAEUDE_FIELDS} | {"raeume": [{k: None for k, *_ in RK.RAUM_FIELDS}
                                                               for _ in range(RK.RAEUME)]} for _ in range(RK.GEBAEUDE)]
    raeume[0].update(anschrift="Musterweg 1", besitz="Gemietet", flaeche=100.0, miete=250.0)
    raeume[0]["raeume"][0].update(raum="Büro", nutzung="Verwaltung", groesse=12.5, miete_qm=2.5, anteil=0.3)
    form = {}
    for g in RK.form_view(raeume):
        form.update({f"g{g['n']}_{k}": g[k] for k, *_ in RK.GEBAEUDE_FIELDS})
        for r in g["raeume"]:
            form.update({f"g{g['n']}_r{r['n']}_{k}": r[k] for k, *_ in RK.RAUM_FIELDS})
    assert form["g0_r0_anteil"] == "30" and form["g0_r0_groesse"] == "12,5"
    assert RK.from_form(form) == raeume
    for key, value, msg in [("g0_r0_nutzung", "", "Nutzungsart fehlt"), ("g0_flaeche", "", "Gesamtfläche"),
                            ("g0_r0_anteil", "120", "höchstens 100"), ("g0_r0_groesse", "zwölf", "keine Zahl")]:
        with pytest.raises(ValueError, match=msg):
            RK.from_form(form | {key: value})
