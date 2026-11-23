"""Fill the template and let LibreOffice recalculate it: the template's formulas must produce
the expected totals (km rate, Tagegeld, sums, IBAN check, bank lookup)."""

import subprocess
import zipfile
from pathlib import Path

import openpyxl
import pytest

from app import config as C
from app import workbook as W

DATA = {
    "abrechnung": {
        "fields": {
            "thema": "KatS Tauchen",
            "art": "ausbildung",
            "ort": "Altenberge",
            "gliederungsnummer": "1321013",
            "beginn_datum": "26.06.2026",
            "beginn_uhrzeit": "15:00",
            "ende_datum": "26.06.26",
            "ende_uhrzeit": "17.00",
            "materialausgaben": "12,50 €",
        },
        "tables": {"fahrzeuge": [{"kennzeichen": "ST-DL 1", "km": "100", "mitfahrer": "2", "anhaenger": "ja"}]},
    },
    "teilnehmer": {"tables": {"teilnehmer": [
        {"name": "Muster", "vorname": "Max", "wohnort": "Greven"},
        {"name": "Beispiel", "vorname": "Erika", "wohnort": "Emsdetten"},
    ]}},
    "tagegeld": {"fields": {"ausserhalb_gemeinde": "nein", "teilnehmer_aufwand": "2"}},
    "fahrtkosten_1": {
        "fields": {"fahrer": "Max Muster", "kennzeichen": "ST-AB 123", "iban": "DE89 3704 0044 0532 0130 00", "km": "60", "anhaenger": "nein"},
        "tables": {"mitfahrer": [{"name": "Erika Beispiel"}]},
    },
}


def recalculated_text(xlsx: Path, tmp: Path) -> str:
    subprocess.run([C.SOFFICE, "--headless", f"-env:UserInstallation=file://{tmp}/lo", "--convert-to", "pdf", "--outdir", str(tmp), str(xlsx)],
                   check=True, capture_output=True, timeout=180)
    pdf = tmp / (xlsx.stem + ".pdf")
    out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True, capture_output=True, text=True)
    return out.stdout


@pytest.fixture(scope="module")
def filled(template_xlsx, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("fill")
    blank = tmp / "blank.xlsx"
    W.blank_template(template_xlsx, blank)
    out = tmp / "filled.xlsx"
    problems = W.fill(blank, DATA, out)
    return blank, out, problems, tmp


def test_blank_template_has_no_example_data(filled):
    blank, *_ = filled
    wb = openpyxl.load_workbook(blank)
    assert wb["Abrechnungsbogen"]["B3"].value is None
    assert wb["Teilnehmerliste"]["B12"].value is None
    assert wb["Fahrtkosten (1)"]["C30"].value is None
    assert wb["Abrechnungsbogen"]["G27"].value == 1


def test_values_are_typed(filled):
    _, out, problems, _ = filled
    assert problems == []
    ws = openpyxl.load_workbook(out)["Abrechnungsbogen"]
    assert ws["B4"].value == "Ausbildung"
    assert ws["B6"].value == 1321013
    assert ws["B8"].value.year == 2026 and ws["B9"].value.day == 26
    assert ws["G13"].value == 12.5
    fk = openpyxl.load_workbook(out)["Fahrtkosten (1)"]
    assert fk["B14"].value == "DE89370400440532013000"


def test_text_cell_starting_with_equals_survives(filled):
    _, out, *_ = filled
    with zipfile.ZipFile(out) as z:
        names = [n for n in z.namelist() if n.startswith("xl/worksheets/sheet")]
        xml = "".join(z.read(n).decode() for n in names)
    assert "<f>24 Stunden</f>" not in xml


def amounts(text: str) -> set[str]:
    """All money amounts in the PDF text, normalized to 1234.56 (locale independent)."""
    import re
    return {m.replace(".", "").replace(",", ".") if "," in m else m for m in re.findall(r"\d[\d.,]*\d(?= ?€)", text)}


def test_formulas_calculate(filled):
    _, out, _, tmp = filled
    text = recalculated_text(out, tmp)
    found = amounts(text)
    # Abrechnungsbogen Fahrzeug 1: 100 km x (0,30 + 2 x 0,02 + 0,02 Anhänger) = 36,00
    assert "36.00" in found
    # Gesamtkosten = 36,00 + 12,50 Material = 48,50, Anteil KatS 100 % -> Kosten KatS 48,50
    assert "48.50" in found
    assert text.count("48") >= 2
    # Fahrtkosten (1): 60 km x (0,30 + 1 Mitfahrer x 0,02) = 19,20
    assert "19.20" in found
    # Gliederung looked up from the number
    assert "OG Greven" in text
    # Participants and Fahrer arrive on their sheets
    assert "Muster" in text and "Erika Beispiel" in text


def test_aufwandsverguetung_flows_into_gesamtkosten(template_xlsx, tmp_path):
    """G16 is not linked in the template: the app writes the link unless the paper has an amount."""
    blank = tmp_path / "blank.xlsx"
    W.blank_template(template_xlsx, blank)
    data = {
        "abrechnung": {"fields": {"art": "Übung", "gliederungsnummer": "1321013",
                                  "beginn_datum": "17.10.2026", "beginn_uhrzeit": "8:00",
                                  "ende_datum": "17.10.2026", "ende_uhrzeit": "17:00", "materialausgaben": "10"}},
        "tagegeld": {"fields": {"ausserhalb_gemeinde": "NEIN", "teilnehmer_aufwand": "3"}},
    }
    W.fill(blank, data, tmp_path / "a.xlsx")
    ws = W.recalculate(tmp_path / "a.xlsx")["Abrechnungsbogen"]
    # 9 hours inside the Gemeinde: 4,00 € x 3 participants
    assert ws["G16"].value == pytest.approx(12)
    assert ws["G26"].value == pytest.approx(22)

    data["abrechnung"]["fields"]["aufwandverguetungen"] = "5,00"
    W.fill(blank, data, tmp_path / "b.xlsx")
    assert W.recalculate(tmp_path / "b.xlsx")["Abrechnungsbogen"]["G16"].value == pytest.approx(5)
