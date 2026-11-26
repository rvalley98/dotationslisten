"""Moving pages between Vorgänge (a stack split at the wrong place). Synthetic data only."""

import pytest
from PIL import Image

from app import config as C
from app import jobs as J


def _values(job, sheet):
    return (job["data"].get(sheet) or {}).get("fields", {}).get("x")


@pytest.fixture()
def arbeit(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "ARBEIT", tmp_path / "arbeit")
    C.ARBEIT.mkdir()
    return C.ARBEIT


def _scan_job(index, kinds, source_hash="abcdef0123456789"):
    pages = [{"n": i + 1, "kind": k, "rotation": 0, "source_page": i + 1} for i, k in enumerate(kinds)]
    job = J.new_job("stapel.pdf", source_hash, index, pages, recognize=False)
    (J.job_dir(job["id"]) / "pages").mkdir(parents=True)
    for p in job["pages"]:
        p["image"] = f"pages/{p['n']:03d}.png"
        Image.new("RGB", (4, 4), (p["n"] * 40, 0, 0)).save(J.job_dir(job["id"]) / p["image"])
        if p["sheet"]:
            job["data"][p["sheet"]] = {"fields": {"x": f"Seite {p['n']}"}, "tables": {}}
    job["reviewed"] = [p["sheet"] for p in job["pages"] if p["sheet"]][:1]
    J.save(job)
    return job


def _pixel(job_id, page):
    with Image.open(J.job_dir(job_id) / page["image"]) as im:
        return im.getpixel((0, 0))


def test_split_off_with_following_pages(arbeit):
    # Veranstaltungsabrechnung of the 2nd Veranstaltung missing: its Fahrtkosten ended up in the 1st
    job = _scan_job(0, ["abrechnung", "tagegeld", "fahrtkosten", "fahrtkosten"])
    J.update(job["id"], lambda j: j.update(export={"file": "x.xlsx", "problems": []}))
    new_id, first, taken = J.move_pages(job["id"], [3, 4], None)

    src, dst = J.load(job["id"]), J.load(new_id)
    assert [p["sheet"] for p in src["pages"]] == ["abrechnung", "tagegeld"]
    assert src["reviewed"] == ["abrechnung"] and set(src["data"]) == {"abrechnung", "tagegeld"}
    assert src["export"]["veraltet"]
    assert first == 1 and taken == []
    assert [p["n"] for p in dst["pages"]] == [1, 2]
    assert [p["sheet"] for p in dst["pages"]] == ["fahrtkosten_1", "fahrtkosten_2"]
    assert dst["data"]["fahrtkosten_1"]["fields"]["x"] == "Seite 3"
    assert dst["data"]["fahrtkosten_2"]["fields"]["x"] == "Seite 4"
    assert dst["source"] == "stapel.pdf" and dst["source_hash"] == job["source_hash"]
    assert [_pixel(new_id, p)[0] for p in dst["pages"]] == [120, 160]  # the right scans came along
    assert sorted(f.name for f in (J.job_dir(job["id"]) / "pages").iterdir()) == ["001.png", "002.png"]


def test_move_into_other_vorgang_and_remove_empty(arbeit):
    a = _scan_job(0, ["abrechnung", "tagegeld", "fahrtkosten"])
    b = _scan_job(1, ["abrechnung", "fahrtkosten"])
    new_id, first, taken = J.move_pages(a["id"], [2, 3], b["id"])
    dst = J.load(b["id"])
    assert new_id == b["id"] and first == 3 and taken == []
    assert [p["sheet"] for p in dst["pages"]] == ["abrechnung", "fahrtkosten_1", "tagegeld", "fahrtkosten_2"]
    assert dst["data"]["fahrtkosten_2"]["fields"]["x"] == "Seite 3"

    # a second Veranstaltungsabrechnung: that sheet is taken, the page arrives unassigned
    _id, _first, taken = J.move_pages(a["id"], [1], b["id"])
    assert taken == ["Abrechnungsbogen"]
    dst = J.load(b["id"])
    assert dst["pages"][-1]["sheet"] is None
    assert dst["pages"][-1]["kept"]["values"]["fields"]["x"] == "Seite 1"  # a's values are not lost
    assert not J.job_dir(a["id"]).exists()  # nothing left in it


def test_imports_cannot_be_split(arbeit):
    job = J.new_manual_job(["abrechnung"])
    job["pages"][0]["kind"] = J.IMPORT
    J.save(job)
    with pytest.raises(ValueError):
        J.move_pages(job["id"], [1], None)


def test_move_route(data_dir, monkeypatch):
    monkeypatch.setenv("WORKER", "0")
    from fastapi.testclient import TestClient
    from app import main

    a = _scan_job(0, ["abrechnung", "tagegeld", "fahrtkosten"])
    b = _scan_job(1, ["abrechnung"])
    with TestClient(main.app) as client:
        page = client.get(f"/vorgang/{a['id']}/seite/2").text
        assert "Seite gehört zu einer anderen Veranstaltung?" in page
        assert f'value="{b["id"]}">' in page and "gleicher Scan, Scan-Seite 1 (1 Seite)" in page
        r = client.post(f"/vorgang/{a['id']}/seite/2/verschieben", data={"ziel": "", "folgende": "1"},
                        follow_redirects=False)
        assert r.status_code == 303
        new_id = r.headers["location"].split("/")[2]
        assert [p["sheet"] for p in J.load(new_id)["pages"]] == ["tagegeld", "fahrtkosten_1"]
        assert client.get(r.headers["location"]).status_code == 200
        r = client.post(f"/vorgang/{a['id']}/seite/1/verschieben", data={"ziel": b["id"]}, follow_redirects=False)
        assert "belegt=" in r.headers["location"]
        assert "Diese Blätter gab es hier schon" in client.get(r.headers["location"]).text
        assert client.get(f"/vorgang/{a['id']}").status_code == 404

        # assign the arrived Abrechnungsbogen: its values come back, b's own are kept on its page
        n = J.load(b["id"])["pages"][-1]["n"]
        client.post(f"/vorgang/{b['id']}/seite/{n}/zuordnung", data={"sheet": "abrechnung"})
        j = J.load(b["id"])
        assert _values(j, "abrechnung") == "Seite 1" and j["pages"][0]["kept"]
        assert "aufbewahrte Werte" in client.get(f"/vorgang/{b['id']}/seite/1").text

        # Excel of a Vorgang split off without Abrechnungsbogen, and of the one that got pages
        for jid in (new_id, b["id"]):
            r = client.post(f"/vorgang/{jid}/export", data={"back": "1"}, follow_redirects=False)
            assert r.status_code == 303, r.text
            exp = J.load(jid)["export"]
            assert (C.AUSGANG / exp["file"]).exists() and not exp.get("veraltet")


def test_reassigning_keeps_every_pages_values(arbeit):
    a = _scan_job(0, ["abrechnung", "tagegeld"])
    b = _scan_job(1, ["abrechnung"], source_hash="ffff000011112222")
    J.update(b["id"], lambda j: j["data"]["abrechnung"]["fields"].update(x="B"))
    J.move_pages(a["id"], [1], b["id"])  # b now has two Abrechnungsbögen, the moved one without a sheet
    moved = J.load(b["id"])["pages"][-1]
    assert moved["sheet"] is None and moved["kept"]["reviewed"]

    def swap(j):  # what "Blatt: Abrechnungsbogen" on the moved page does
        for other in j["pages"]:
            if other is not j["pages"][-1] and other.get("sheet") == "abrechnung":
                J.detach(j, other)
        J.attach(j, j["pages"][-1], "abrechnung", recognize=True)

    j = J.update(b["id"], swap)
    assert _values(j, "abrechnung") == "Seite 1" and "abrechnung" in j["reviewed"]  # its own values, checked
    assert j["pages"][0]["sheet"] is None and j["pages"][0]["kept"]["values"]["fields"]["x"] == "B"
    assert j["pages"][-1]["recog"] == J.R_SKIP  # nothing to recognise again

    J.update(b["id"], lambda j: J.attach(j, j["pages"][0], "teilnehmer", recognize=True))
    j = J.load(b["id"])
    assert "teilnehmer" not in j["data"] and j["pages"][0]["recog"] == J.R_OPEN  # other kind: read afresh
    assert j["pages"][0]["kept"]["values"]["fields"]["x"] == "B"  # still kept for later
