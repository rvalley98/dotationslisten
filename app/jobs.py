"""Vorgänge (one filled-in set of forms = one workbook), stored as data/arbeit/<id>/job.json.

A Vorgang is a list of pages. Each page has a kind (from its printed title) and is assigned to
one worksheet of the template; the reviewed values live in job["data"] in the shape that
workbook.fill() expects.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import threading
from pathlib import Path
from typing import Any

from . import config as C
from . import fields as F

LOCK = threading.RLock()

# recognition state of a page
R_OPEN = "offen"        # waiting for the recognizer
R_DONE = "fertig"
R_ERROR = "fehler"
R_SKIP = "-"            # nothing to recognise (blank, Belege, unassigned)


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def job_dir(job_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", job_id):
        raise KeyError(job_id)
    return C.ARBEIT / job_id


def load(job_id: str) -> dict[str, Any]:
    path = job_dir(job_id) / "job.json"
    if not path.exists():
        raise KeyError(job_id)
    return json.loads(path.read_text("utf-8"))


def save(job: dict[str, Any]) -> None:
    with LOCK:
        d = job_dir(job["id"])
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "job.json.tmp"
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, d / "job.json")


def all_jobs() -> list[dict[str, Any]]:
    jobs = []
    for p in C.ARBEIT.glob("*/job.json"):
        try:
            jobs.append(json.loads(p.read_text("utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(jobs, key=lambda j: j["created"], reverse=True)


def update(job_id: str, fn) -> dict[str, Any]:
    """Load, modify and save under the lock (the worker and the web UI share files)."""
    with LOCK:
        job = load(job_id)
        fn(job)
        job["updated"] = _now()
        save(job)
        return job


def assign_sheets(kinds: list[str]) -> list[str | None]:
    """Page kinds of one Vorgang -> worksheet keys (Fahrtkosten 1-5 in order, others once)."""
    used: set[str] = set()
    out: list[str | None] = []
    fk = 0
    for kind in kinds:
        key: str | None = None
        if kind == "fahrtkosten":
            fk += 1
            key = f"fahrtkosten_{fk}" if fk <= len(F.FAHRTKOSTEN) else None
        elif kind in F.SHEETS_BY_KEY and kind not in used:
            key = kind
        if key:
            used.add(key)
        out.append(key)
    return out


def split_vorgaenge(kinds: list[str]) -> list[list[int]]:
    """Page indices per Vorgang: every Abrechnungsbogen starts a new one (stack mode)."""
    groups: list[list[int]] = []
    for i, kind in enumerate(kinds):
        if kind == "abrechnung" and groups and any(kinds[j] == "abrechnung" for j in groups[-1]):
            groups.append([])
        if not groups:
            groups.append([])
        groups[-1].append(i)
    return groups


def new_job(source: str, source_hash: str, index: int, pages: list[dict[str, Any]], recognize: bool) -> dict[str, Any]:
    job_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{source_hash[:8]}-{index + 1}"
    kinds = [p["kind"] for p in pages]
    for p, sheet in zip(pages, assign_sheets(kinds)):
        p["sheet"] = sheet
        p["recog"] = R_OPEN if (sheet and recognize) else R_SKIP
        p["recog_error"] = None
    return {
        "id": job_id,
        "created": _now(),
        "updated": _now(),
        "source": source,
        "source_hash": source_hash,
        "pages": pages,
        "data": {},
        "reviewed": [],
        "export": None,
    }


MANUAL = "manuell"  # page kind of a sheet entered by hand (no scan)


def manual_page(n: int, sheet: str) -> dict[str, Any]:
    return {"n": n, "kind": MANUAL, "rotation": 0, "source_page": None, "sheet": sheet,
            "recog": R_SKIP, "recog_error": None, "image": None}


def new_manual_job(sheets: list[str]) -> dict[str, Any]:
    job_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + os.urandom(4).hex() + "-m"
    return {
        "id": job_id,
        "created": _now(),
        "updated": _now(),
        "source": "Manuell erfasst",
        "source_hash": None,
        "pages": [manual_page(i + 1, s) for i, s in enumerate(sheets)],
        "data": {},
        "reviewed": [],
        "export": None,
    }


def free_sheets(job: dict[str, Any]) -> list[str]:
    """Sheets not yet assigned to a page (Fahrtkosten: only the next free one)."""
    used = {p.get("sheet") for p in job["pages"]}
    free = [s.key for s in F.SHEETS if s.key not in used and not s.key.startswith("fahrtkosten_")]
    fk = next((s.key for s in F.FAHRTKOSTEN if s.key not in used), None)
    if fk:
        free.insert(min(len(free), 3), fk)
    return free


def title(job: dict[str, Any]) -> str:
    f = (job.get("data", {}).get("abrechnung") or {}).get("fields") or {}
    parts = [f.get("beginn_datum") or "", f.get("thema") or ""]
    return " ".join(p for p in parts if p).strip() or job["source"]


def export_name(job: dict[str, Any]) -> str:
    f = (job.get("data", {}).get("abrechnung") or {}).get("fields") or {}
    date = ""
    m = re.fullmatch(r"\s*(\d{1,2})\.(\d{1,2})\.(\d{2,4})\s*", f.get("beginn_datum") or "")
    if m:
        y = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
        date = f"{y:04d}{int(m[2]):02d}{int(m[1]):02d} "
    name = re.sub(r"[^\w äöüÄÖÜß.-]+", "_", (f.get("thema") or "").strip())[:60] or "Abrechnung"
    return f"{date}{name} ({job['id'][-10:]}).xlsx"


IMPORT = "import"  # page kind of a Vorgang imported from Excel (the file is its Excel)


def is_import(job: dict[str, Any]) -> bool:
    return any(p.get("kind") == IMPORT for p in job["pages"])


def _base(sheet: str) -> str:
    return "fahrtkosten" if sheet.startswith("fahrtkosten_") else sheet


def detach(job: dict[str, Any], page: dict[str, Any]) -> None:
    """Take a page off its sheet. Its values stay with the page ("kept") instead of being lost or
    sticking to the sheet - assigned to the same kind of sheet again, they come back."""
    sheet = page.get("sheet")
    if not sheet:
        return
    values = job["data"].pop(sheet, None)
    reviewed = sheet in job["reviewed"]
    if reviewed:
        job["reviewed"].remove(sheet)
    if values:
        page["kept"] = {"base": _base(sheet), "values": values, "reviewed": reviewed}
    page["sheet"], page["recog"], page["recog_error"] = None, R_SKIP, None


def attach(job: dict[str, Any], page: dict[str, Any], sheet: str, recognize: bool) -> None:
    """Put a page (without a sheet) on a free sheet: its kept values if they fit, else recognition."""
    page["sheet"], page["recog_error"] = sheet, None
    kept = page.get("kept")
    if kept and kept["base"] == _base(sheet):
        page.pop("kept")
        job["data"][sheet] = kept["values"]
        if kept["reviewed"] and sheet not in job["reviewed"]:
            job["reviewed"].append(sheet)
        page["recog"] = R_SKIP
    else:
        job["data"].pop(sheet, None)
        page["recog"] = R_OPEN if (recognize and page.get("image")) else R_SKIP


def _target_sheet(sheet: str | None, used: set[str]) -> str | None:
    """Sheet of a moved page in its new Vorgang: the same one if free, Fahrtkosten the next free."""
    if not sheet:
        return None
    if sheet.startswith("fahrtkosten_"):
        return next((s.key for s in F.FAHRTKOSTEN if s.key not in used), None)
    return None if sheet in used else sheet


def move_pages(src_id: str, numbers: list[int], target_id: str | None) -> tuple[str, int, list[str]]:
    """Move pages (with their scan, read and checked values) into another Vorgang or - target_id
    None - into a new one with the same source PDF. Returns (target id, first moved page there,
    names of sheets that were taken in the target already: those pages arrive without a sheet and
    keep their values until they are assigned to such a sheet).

    A Vorgang left without pages is removed. Both lose their Excel's validity (veraltet).
    """
    with LOCK:
        src = load(src_id)
        moving = [p for p in src["pages"] if p["n"] in set(numbers)]
        if not moving:
            raise ValueError("Keine Seite ausgewählt")
        if is_import(src):
            raise ValueError("Ein aus Excel importierter Vorgang lässt sich nicht aufteilen")
        if target_id == src_id:
            raise ValueError("Die Seite ist schon in diesem Vorgang")
        if target_id:
            dst = load(target_id)
            if is_import(dst):
                raise ValueError("In einen aus Excel importierten Vorgang lassen sich keine Seiten verschieben")
        else:
            dst = {
                "id": dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + os.urandom(4).hex() + "-t",
                "created": src["created"],  # same place in the list as the stack it came from
                "updated": _now(),
                "source": src["source"],
                "source_hash": src.get("source_hash"),
                "pages": [], "data": {}, "reviewed": [], "export": None,
            }
        used = {p["sheet"] for p in dst["pages"] if p.get("sheet")}
        n = max((p["n"] for p in dst["pages"]), default=0)
        dst_dir = job_dir(dst["id"])
        (dst_dir / "pages").mkdir(parents=True, exist_ok=True)
        taken, first, copied = [], n + 1, []
        for p in moving:
            n += 1
            old_sheet, was_open = p.get("sheet"), p.get("recog") == R_OPEN
            src["pages"].remove(p)
            new = dict(p, n=n)
            detach(src, new)  # values onto the page ...
            if p.get("image"):
                name = f"pages/{dst['id'][-6:]}-{n:03d}.png"
                while (dst_dir / name).exists():
                    name = f"pages/{os.urandom(3).hex()}-{n:03d}.png"
                shutil.copy2(job_dir(src_id) / p["image"], dst_dir / name)
                copied.append(job_dir(src_id) / p["image"])
                new["image"] = name
            sheet = _target_sheet(old_sheet, used)
            if sheet:  # ... and into the sheet of the new Vorgang
                used.add(sheet)
                attach(dst, new, sheet, recognize=was_open)
            elif old_sheet:
                taken.append(F.SHEETS_BY_KEY[old_sheet].name)
            dst["pages"].append(new)
        for j in (src, dst):
            if j.get("export"):
                j["export"]["veraltet"] = True
            j["updated"] = _now()
        save(dst)
        if src["pages"]:
            save(src)
            for f in copied:  # the scans now live in the other Vorgang
                f.unlink(missing_ok=True)
        else:
            old = (src.get("export") or {}).get("file")
            if old:  # its Excel has no Vorgang any more (regenerated by the Vorgänge that got the pages)
                (C.AUSGANG / old).unlink(missing_ok=True)
            shutil.rmtree(job_dir(src_id))
        return dst["id"], first, taken
