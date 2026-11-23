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
