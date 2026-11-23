"""One background thread: intake of new scans, then recognition of one page at a time
(a CPU-only server can handle exactly one model call at once)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from PIL import Image

from . import config as C
from . import fields as F
from . import intake
from . import jobs as J
from . import rules
from . import signatures
from .recognize import Recognizer, Unavailable

log = logging.getLogger("dotationslisten.worker")


def next_open_page() -> tuple[str, int] | None:
    for job in sorted(J.all_jobs(), key=lambda j: j["created"]):
        for p in job["pages"]:
            if p.get("recog") == J.R_OPEN and p.get("sheet") and p.get("image"):
                return job["id"], p["n"]
    return None


def apply_result(job: dict[str, Any], n: int, result: dict[str, Any]) -> None:
    page = next(p for p in job["pages"] if p["n"] == n)
    page["recog"] = J.R_DONE
    page["recog_error"] = None
    page["recognized"] = result
    if page["sheet"] not in job["reviewed"]:  # never overwrite what a person has checked
        job["data"][page["sheet"]] = result
    if "tagegeld" not in job["reviewed"]:
        rules.apply_teilnehmeranzahl(job["data"])


def recognize_one(rec: Recognizer) -> bool:
    """Returns True if a page was processed."""
    nxt = next_open_page()
    if not nxt:
        return False
    job_id, n = nxt
    job = J.load(job_id)
    page = next(p for p in job["pages"] if p["n"] == n)
    sheet = F.SHEETS_BY_KEY[page["sheet"]]
    with Image.open(J.job_dir(job_id) / page["image"]) as im:
        image = im.convert("RGB")
    started = time.monotonic()
    try:
        result = rec.recognize(image, sheet)
    except Unavailable:
        raise
    except Exception as e:  # model returned garbage etc. – the page stays editable by hand
        log.exception("Erkennung fehlgeschlagen: %s Seite %s", job_id, n)

        def fail(j):
            pg = next(p for p in j["pages"] if p["n"] == n)
            pg["recog"], pg["recog_error"] = J.R_ERROR, str(e)[:300]

        J.update(job_id, fail)
        return True
    if sheet.key == "tagegeld":
        try:
            n_signed = signatures.count(image)
        except Exception:
            log.exception("Unterschriften zählen fehlgeschlagen: %s Seite %s", job_id, n)
            n_signed = None
        result["fields"]["unterschriften"] = "" if n_signed is None else str(n_signed)
    log.info("%s Seite %s (%s) erkannt in %.0fs", job_id, n, sheet.name, time.monotonic() - started)

    def done(j):
        pg = next(p for p in j["pages"] if p["n"] == n)
        if pg.get("recog") == J.R_OPEN and pg.get("sheet") == sheet.key:  # not reassigned meanwhile
            apply_result(j, n, result)
            pg["recog_seconds"] = round(time.monotonic() - started)

    J.update(job_id, done)
    return True


class Worker(threading.Thread):
    def __init__(self, rec: Recognizer):
        super().__init__(daemon=True, name="worker")
        self.rec = rec
        self.status: tuple[bool, str] = rec.status()
        self.busy: str | None = None
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        last_status = 0.0
        while not self._stop.is_set():
            try:
                intake.poll(self.rec.enabled)
                if time.monotonic() - last_status > 30:
                    self.status = self.rec.status()
                    last_status = time.monotonic()
                if self.rec.enabled and self.status[0]:
                    self.busy = "Erkennung läuft"
                    try:
                        if recognize_one(self.rec):
                            self.busy = None
                            continue  # next page right away
                    except Unavailable as e:
                        self.status = (False, str(e))
                    finally:
                        self.busy = None
            except Exception:
                log.exception("Worker-Fehler")
            self._stop.wait(C.POLL_SECONDS)
