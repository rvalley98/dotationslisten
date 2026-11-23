"""Intake -> classification -> Vorgänge -> review UI -> export, on pages rendered from the
blank template (printed titles only; real handwriting is not part of these tests)."""

import io
import shutil
import subprocess
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import config as C
from app import intake
from app import jobs as J
from app import pages as P
from app import worker
from app.recognize import NoneRecognizer, Unavailable, OllamaRecognizer, clean, schema
from app import fields as F


@pytest.fixture(scope="session")
def blank_pdf(template_xlsx, tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("render")
    from app import workbook as W
    W.blank_template(template_xlsx, tmp / "leer.xlsx")
    subprocess.run([C.SOFFICE, "--headless", f"-env:UserInstallation=file://{tmp}/lo", "--convert-to", "pdf",
                    "--outdir", str(tmp), str(tmp / "leer.xlsx")], check=True, capture_output=True, timeout=300)
    return tmp / "leer.pdf"


def test_classification_of_rendered_pages(blank_pdf):
    # page breaks differ between LibreOffice versions (Linux/Mac): check the order of the sheets,
    # ignoring overflow pages (blank or untitled) and "Belege"
    kinds = [P.analyse(im).kind for im in P.load_pages(blank_pdf)]
    sheets = [k for k in kinds if k not in ("leer", "folgeseite", "belege")]
    assert sheets == ["abrechnung", "teilnehmer", "tagegeld"] + ["fahrtkosten"] * 5 + ["tauchprotokoll"], kinds


def test_upside_down_and_blank_pages(blank_pdf):
    first = P.load_pages(blank_pdf)[0]
    page = P.analyse(first.rotate(180))
    assert page.kind == "abrechnung" and page.rotation == 180
    assert P.analyse(Image.new("RGB", first.size, "white")).kind == "leer"


def test_sheet_assignment_and_stack_split():
    kinds = ["abrechnung", "teilnehmer", "fahrtkosten", "leer", "fahrtkosten",
             "abrechnung", "fahrtkosten", "teilnehmer", "teilnehmer"]
    groups = J.split_vorgaenge(kinds)
    assert groups == [[0, 1, 2, 3, 4], [5, 6, 7, 8]]
    assert J.assign_sheets([kinds[i] for i in groups[0]]) == ["abrechnung", "teilnehmer", "fahrtkosten_1", None, "fahrtkosten_2"]
    # a second Teilnehmerliste is left for the user to assign
    assert J.assign_sheets([kinds[i] for i in groups[1]]) == ["abrechnung", "fahrtkosten_1", "teilnehmer", None]


def test_intake_stack_is_idempotent(blank_pdf, data_dir):
    stack = C.EINGANG / "stapel.pdf"
    subprocess.run(["pdfunite", str(blank_pdf), str(blank_pdf), str(stack)], check=True)
    assert intake.poll(recognize=True) == []          # first sight: size not yet stable
    ids = intake.poll(recognize=True)
    assert len(ids) == 2
    job = J.load(ids[0])
    sheets = [p["sheet"] for p in job["pages"] if p["sheet"]]
    assert sheets[:3] == ["abrechnung", "teilnehmer", "tagegeld"]
    assert "fahrtkosten_5" in sheets and "tauchprotokoll" in sheets
    assert all(p["recog"] == J.R_OPEN for p in job["pages"] if p["sheet"])
    assert not stack.exists() and list((C.ARCHIV).glob("*/stapel.pdf"))
    # same file again -> no new Vorgang
    shutil.copy(next(C.ARCHIV.glob("*/stapel.pdf")), C.EINGANG / "nochmal.pdf")
    intake.poll(recognize=True)
    assert intake.poll(recognize=True) == []
    assert (C.ARCHIV / "duplikate" / "nochmal.pdf").exists()


class FakeRecognizer:
    enabled = True

    def __init__(self):
        self.calls = 0

    def status(self):
        return True, "fake"

    def recognize(self, image, sheet):
        self.calls += 1
        if sheet.key == "abrechnung":
            return clean(sheet, {"fields": {"thema": "KatS Tauchen", "art": "Übung", "gliederungsnummer": "1321013",
                                            "beginn_datum": "26.06.2026", "materialausgaben": "12,50"},
                                 "tables": {"fahrzeuge": [{"kennzeichen": "ST-DL 1", "km": "100", "mitfahrer": "2", "anhaenger": "ja"}]}})
        return clean(sheet, {})


def test_worker_recognition_does_not_overwrite_reviewed(blank_pdf, data_dir):
    shutil.copy(blank_pdf, C.EINGANG / "a.pdf")
    intake.poll(True)
    (job_id,) = intake.poll(True)
    J.update(job_id, lambda j: (j["data"].update({"teilnehmer": {"fields": {}, "tables": {"teilnehmer": [{"name": "Hand"}]}}}),
                                j["reviewed"].append("teilnehmer")))
    rec = FakeRecognizer()
    while worker.recognize_one(rec):
        pass
    job = J.load(job_id)
    assert job["data"]["abrechnung"]["fields"]["thema"] == "KatS Tauchen"
    assert job["data"]["teilnehmer"]["tables"]["teilnehmer"] == [{"name": "Hand"}]
    assert rec.calls == sum(1 for p in job["pages"] if p["sheet"])


def test_ollama_unreachable_keeps_pages_queued(blank_pdf, data_dir):
    shutil.copy(blank_pdf, C.EINGANG / "a.pdf")
    intake.poll(True)
    (job_id,) = intake.poll(True)
    with pytest.raises(Unavailable):
        worker.recognize_one(OllamaRecognizer(url="http://127.0.0.1:9", timeout=2))
    assert all(p["recog"] == J.R_OPEN for p in J.load(job_id)["pages"] if p["sheet"])


def test_schema_covers_field_map():
    s = schema(F.SHEETS_BY_KEY["fahrtkosten_1"])
    assert set(s["properties"]["fields"]["properties"]) == {"fahrer", "kennzeichen", "iban", "km", "anhaenger"}
    assert s["properties"]["tables"]["properties"]["mitfahrer"]["maxItems"] == 8
    out = clean(F.SHEETS_BY_KEY["teilnehmer"], {"tables": {"teilnehmer": [{"name": " A "}, {}, "x"] + [{"name": "B"}] * 30}})
    assert out["tables"]["teilnehmer"][0] == {"name": "A", "vorname": "", "wohnort": ""}
    assert len(out["tables"]["teilnehmer"]) == 20


def test_web_review_and_export(blank_pdf, data_dir, monkeypatch):
    monkeypatch.setenv("WORKER", "0")
    monkeypatch.setattr(C, "RECOGNIZER", "none")
    from app.main import app
    with TestClient(app) as client:
        r = client.post("/upload", files={"files": ("scan.pdf", blank_pdf.read_bytes(), "application/pdf")})
        assert r.status_code == 200
        intake.poll(False)
        (job_id,) = intake.poll(False)
        assert job_id in client.get("/").text

        page = client.get(f"/vorgang/{job_id}/seite/1")
        assert page.status_code == 200 and "Bezeichnung / Thema" in page.text
        client.post(f"/vorgang/{job_id}/seite/1", data={
            "f:thema": "KatS Tauchen", "f:art": "übung", "f:gliederungsnummer": "1321013",
            "f:beginn_datum": "26.06.2026", "f:beginn_uhrzeit": "15:00",
            "t:fahrzeuge:0:kennzeichen": "ST-DL 1", "t:fahrzeuge:0:km": "100",
            "t:fahrzeuge:0:mitfahrer": "2", "t:fahrzeuge:0:anhaenger": "ja"})
        assert J.load(job_id)["pages"][0]["recog"] == J.R_SKIP
        fk = next(p["n"] for p in J.load(job_id)["pages"] if p["sheet"] == "fahrtkosten_1")
        client.post(f"/vorgang/{job_id}/seite/{fk}", data={"f:fahrer": "Max Muster", "f:iban": "DE89 3704 0044 0532 0130 01", "f:km": "60"})
        page = client.get(f"/vorgang/{job_id}/seite/{fk}").text
        assert "IBAN-Prüfziffer stimmt nicht" in page
        assert "OG Greven" in client.get(f"/vorgang/{job_id}/seite/1").text

        client.post(f"/vorgang/{job_id}/export", data={"back": "1"})
        dl = client.get(f"/vorgang/{job_id}/download")
        assert dl.status_code == 200
        assert J.load(job_id)["export"]["file"].startswith("20260626 KatS Tauchen (")
        wb = openpyxl.load_workbook(io.BytesIO(dl.content))
        ws = wb["Abrechnungsbogen"]
        assert ws["B3"].value == "KatS Tauchen" and ws["B4"].value == "Übung" and ws["C20"].value == 100
        assert wb["Fahrtkosten (1)"]["B12"].value == "Max Muster"

        # reassigning a page to a sheet that another page holds frees the other page
        client.post(f"/vorgang/{job_id}/seite/2/zuordnung", data={"sheet": "fahrtkosten_1"})
        job = J.load(job_id)
        assert [p["n"] for p in job["pages"] if p["sheet"] == "fahrtkosten_1"] == [2]


def test_signature_count_on_rendered_tagegeld_page(blank_pdf):
    from PIL import ImageDraw
    from app import signatures

    page = P.analyse(P.load_pages(blank_pdf)[2]).image
    assert signatures.count(page) == 0
    # scribble "signatures" on three lines, one of them right across its printed label
    left, right = signatures._label_tops(page.convert("L"))
    signed = page.copy()
    d = ImageDraw.Draw(signed)
    w, h = page.size
    for cx, top in (left[0], left[2], right[1]):
        y = top - int(h * 0.015)
        for k in range(6):
            d.line((cx - 200, y - 20 + k * 6, cx + 200, y + 15 - k * 4), fill=(20, 40, 160), width=5)
    cx, top = right[1]
    d.line((cx - 150, top - 30, cx + 150, top + 25), fill=(20, 40, 160), width=8)
    assert signatures.count(signed) == 3


def test_manual_abrechnung_without_scan(data_dir, monkeypatch):
    monkeypatch.setenv("WORKER", "0")
    from app.main import app

    with TestClient(app) as client:
        r = client.post("/neu", data={"s:teilnehmer": "1", "s:tagegeld": "1"})
        job_id = r.url.path.split("/")[2]
        job = J.load(job_id)
        assert [p["sheet"] for p in job["pages"]] == ["abrechnung", "teilnehmer", "tagegeld"]
        assert all(p["kind"] == J.MANUAL and p["recog"] == J.R_SKIP for p in job["pages"])
        page = client.get(f"/vorgang/{job_id}/seite/1").text
        assert "Von Hand erfasst" in page and "/bild/1" not in page
        assert client.get(f"/vorgang/{job_id}/bild/1").status_code == 404

        client.post(f"/vorgang/{job_id}/seite/1", data={
            "f:thema": "KatS Übung", "f:art": "Übung", "f:ort": "Greven", "f:gliederungsnummer": "1321013",
            "f:beginn_datum": "07.11.2026", "f:beginn_uhrzeit": "08:00",
            "f:ende_datum": "08.11.2026", "f:ende_uhrzeit": "17:00"})
        client.post(f"/vorgang/{job_id}/seite/2", data={"t:teilnehmer:0:name": "Muster", "t:teilnehmer:1:name": "Beispiel"})
        client.post(f"/vorgang/{job_id}/seite/3", data={"f:ausserhalb_gemeinde": "NEIN"})
        # a missing sheet can be added later; Fahrtkosten get the next free number
        r = client.post(f"/vorgang/{job_id}/blatt", data={"sheet": "fahrtkosten_1"})
        assert r.url.path.endswith("/seite/4")
        assert client.post(f"/vorgang/{job_id}/blatt", data={"sheet": "fahrtkosten_1"}).status_code == 400
        assert "fahrtkosten_2" in J.free_sheets(J.load(job_id))
        # reassigning a manual page never queues it for recognition
        client.post(f"/vorgang/{job_id}/seite/4/zuordnung", data={"sheet": "tauchprotokoll"})
        assert J.load(job_id)["pages"][3]["recog"] == J.R_SKIP

        client.post(f"/vorgang/{job_id}/export", data={"back": "1"})
        job = J.load(job_id)
        ws = openpyxl.load_workbook(C.AUSGANG / job["export"]["file"])["Tagegeld_Aufwandsvergütung"]
        assert ws["F23"].value == 2  # Teilnehmeranzahl from the Teilnehmerliste
        assert ws["H25"].value == "=B25*C25*$F$23"  # missing template formula added
        # two days inside the Gemeinde: Anreise-/Abreisetag 14,00 € x 2 participants
        assert job["export"]["summen"]["gesamt"] == pytest.approx(28)


def test_save_and_export_in_one_step(data_dir, monkeypatch):
    monkeypatch.setenv("WORKER", "0")
    from app.main import app

    with TestClient(app) as client:
        job_id = client.post("/neu", data={}).url.path.split("/")[2]
        assert f'action="/vorgang/{job_id}/export"' in client.get("/").text  # "erzeugen" on the start page
        r = client.post(f"/vorgang/{job_id}/seite/1", data={"f:thema": "Von Hand", "f:art": "Ausbildung",
                                                              "f:beginn_datum": "07.11.2026", "export": "1"})
        assert r.status_code == 200
        job = J.load(job_id)
        assert job["data"]["abrechnung"]["fields"]["thema"] == "Von Hand"
        assert job["export"] and not job["export"].get("veraltet")
        assert client.get(f"/vorgang/{job_id}/download").status_code == 200


def test_export_missing_and_all(data_dir, monkeypatch):
    import time
    monkeypatch.setenv("WORKER", "0")
    from app import main

    def wait():
        for _ in range(240):
            if not main.bulk.get("running"):
                return
            time.sleep(0.5)
        raise AssertionError("Excel-Erzeugung hängt")

    with TestClient(main.app) as client:
        ids = [client.post("/neu", data={}).url.path.split("/")[2] for _ in range(2)]
        for i, job_id in enumerate(ids):
            client.post(f"/vorgang/{job_id}/seite/1", data={"f:thema": f"Kurs {i}", "f:beginn_datum": "07.11.2026"})
        client.post(f"/vorgang/{ids[0]}/export", data={"back": "1"})
        first_at = J.load(ids[0])["export"]["at"]
        assert "Fehlende erzeugen (1)" in client.get("/").text

        client.post("/excel", data={"mode": "fehlende"})
        wait()
        assert main.bulk["total"] == 1 and main.bulk["done"] == 1 and not main.bulk["errors"]
        assert J.load(ids[1])["export"]["file"]
        assert J.load(ids[0])["export"]["at"] == first_at  # up to date: left alone
        assert "Fehlende erzeugen (0)" in client.get("/").text

        time.sleep(1.1)  # export timestamps have second resolution
        client.post("/excel", data={"mode": "alle"})
        wait()
        assert main.bulk["done"] == 2
        assert J.load(ids[0])["export"]["at"] != first_at
