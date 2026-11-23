"""Built-in formula evaluator: unit tests (no template needed) and, with the template and
LibreOffice available, the same values as LibreOffice for every formula cell."""

import datetime as dt

import openpyxl
import pytest

from app import config as C
from app import formulas as F
from app import workbook as W


@pytest.fixture()
def book(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Kosten"
    rows = [("Art", "Betrag", "Anteil"), ("Übung", 100, 1), ("Ausbildung", 50, 0.5), ("übung", 10, 1), (None, 7, 1)]
    for r in rows:
        ws.append(r)
    for i in range(2, 6):
        ws[f"D{i}"] = f'=IF(A{i}="","",B{i}*C{i})'
    o = wb.create_sheet("Übersicht (1)")
    o["A1"] = '=SUMIF(Kosten!A2:A65000,"Übung",Kosten!D2:D65000)'
    o["A2"] = "=SUM(Kosten!D2:D5)"
    o["A3"] = "=A2/0"
    o["A4"] = '=IF(ISNUMBER(1),1,2)'
    o["A5"] = "=DATE(2026,13,1)"
    o["A6"] = '=LOOKUP(25,{1,2})'
    o["B1"] = "=-2^2"
    o["B2"] = '=IF(AND(A1>100,NOT(A2=0)),"ja","nein")&"!"'
    o["B3"] = "=MOD(-7,3)"
    o["B4"] = '=TEXT(5,"00")&"/"&TEXT(1234.5,"0,00 €")'
    o["B5"] = "=LEN(MID(\"DE12345678\",3,4))+RIGHT(\"x42\",2)"
    o["B6"] = "='Übersicht (1)'!B3*10%"
    o["C1"] = "=Kosten!E9"
    o["C2"] = '=COUNTA(Kosten!D2:D5)'
    lk = wb.create_sheet("Liste")
    for i, (k, v) in enumerate([(10, "a"), (20, "b"), (30, "c")], start=1):
        lk.cell(i, 1, k), lk.cell(i, 2, v)
    o["C3"] = "=LOOKUP(25,Liste!A1:A3,Liste!B1:B3)"
    o["C4"] = "=LOOKUP(5,Liste!A1:A3,Liste!B1:B3)"
    o["C5"] = "=Kosten!B2+Kosten!A1"
    path = tmp_path / "t.xlsx"
    wb.save(path)
    return F.Book(path)


def test_values(book):
    g = lambda ref: book.get(ref)  # noqa: E731
    assert g("'Übersicht (1)'!A1") == 110  # SUMIF ignores case, range clipped to the used rows
    assert g("Übersicht (1)!A2") == 135  # "" from the IF is not summed
    assert g("Übersicht (1)!A3") == F.DIV0
    assert g("Übersicht (1)!A5") == F.serial(dt.date(2027, 1, 1))
    assert g("Übersicht (1)!B1") == 4  # Excel: unary minus binds tighter than ^
    assert g("Übersicht (1)!B2") == "ja!"
    assert g("Übersicht (1)!B3") == 2
    assert g("Übersicht (1)!B4") == "05/1234,50 €"
    assert g("Übersicht (1)!B5") == 46
    assert g("Übersicht (1)!B6") == pytest.approx(0.2)
    assert g("Übersicht (1)!C1") is None
    assert g("Übersicht (1)!C2") == 4  # "" from a formula counts
    assert g("Übersicht (1)!C3") == "b"
    assert g("Übersicht (1)!C4") == F.NA
    assert g("Übersicht (1)!C5") == F.VALUE


def test_unknown_function_is_reported(book):
    with pytest.raises(F.Unsupported):
        book.get("Übersicht (1)!A4")
    with pytest.raises(F.Unsupported):
        book.get("Übersicht (1)!A6")


def _norm(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return F.serial(v)
    if isinstance(v, dt.timedelta):
        return v.total_seconds() / 86400
    if isinstance(v, dt.time):
        return (v.hour * 3600 + v.minute * 60 + v.second) / 86400
    if isinstance(v, F.XLError) or v == "":
        return None
    return v


@pytest.mark.parametrize("which", ["vorlage", "verwendungsnachweis"])
def test_same_values_as_libreoffice(which, template_xlsx, vn_xlsx, tmp_path):
    if not C.soffice_available():
        pytest.skip("LibreOffice fehlt")
    src = template_xlsx if which == "vorlage" else vn_xlsx  # the template holds the Muster example
    lo = W.recalculate(src)
    book = F.Book(src)
    checked = 0
    for ws in book.wb:
        if ws.title == "Bankleitzahlen_DE":
            continue
        for row in ws.iter_rows():
            for c in row:
                if not (isinstance(c.value, str) and c.value.startswith("=")):
                    continue
                if "TEXT(" in c.value and "€" in c.value:
                    continue  # "0,00 €": German Excel shows 18,00 €, LibreOffice reads "," as thousands separator
                try:
                    mine = book.value(ws.title, c.row, c.column)
                except F.Unsupported:
                    continue  # e.g. a label typed as "=24 Stunden" - LibreOffice is the fallback
                theirs = _norm(lo[ws.title][c.coordinate].value)
                mine = _norm(mine)
                if isinstance(mine, (int, float)) and isinstance(theirs, (int, float)):
                    assert mine == pytest.approx(theirs, abs=1e-7), f"{ws.title}!{c.coordinate} {c.value}"
                else:
                    assert mine == theirs, f"{ws.title}!{c.coordinate} {c.value}"
                checked += 1
    assert checked > 1000
