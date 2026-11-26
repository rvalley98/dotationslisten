"""Verwendungsnachweis: one row per finished Vorgang in its "Kosten" sheet.

The base file is the year's Verwendungsnachweis as filled so far (Raumkosten, rows typed by
hand, the Zuwendung). The app never changes it: it writes base + finished Vorgänge into a new
file and calculates the summary (app/formulas.py) (Übungen / Ausbildung / Verwaltung, 60 % check).

Kosten columns (unlocked, rows 82-559; rows 2-81 are linked to the Raumkosten sheet):
D Gliederungsnummer, E Art (Ausbildung/Übung/Verwaltung), F Thema, G Ort, H Datum,
I Gesamtkosten, J Anteil KatS. K = I*J is a formula.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

import openpyxl

from . import config as C
from . import formulas as F
from . import jobs as J
from . import raumkosten as RK
from . import workbook as W

FIRST_ROW, LAST_ROW = 82, 559
ARTEN = ("Ausbildung", "Übung")
REQUIRED_SHEETS = ("Verwendungsnachweis", "Kosten", "Raumkosten")

# summary cells of the Verwendungsnachweis sheet
SUMMARY = {
    "zuwendung": "F20",
    "uebungen": "H37",
    "ausbildung": "H38",
    "verwaltung": "H39",
    "insgesamt": "H40",
    "eigenanteil": "K30",
    "anteil_ua": "L37",
    "anteil_verwaltung": "L39",
    "pruefung_summe": "J45",
    "pruefung_anteil": "J46",
}

# Vorgang status
FINAL = "final"


ABRECHNUNG_CELLS = {"thema": "B3", "art": "B4", "ort": "B5", "gliederungsnummer": "B6", "datum": "B8",
                    "gesamt": "G26", "anteil": "G27", "kats": "G28"}


def _plain(v: Any) -> Any:
    if isinstance(v, F.XLError) or v == "":
        return None
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def abrechnung_summen(xlsx: Path) -> dict[str, Any]:
    """Calculated key values of an exported Abrechnung (what goes into one Kosten row)."""
    refs = {k: f"Abrechnungsbogen!{c}" for k, c in ABRECHNUNG_CELLS.items()}
    v = W.calculate(xlsx, list(refs.values()))
    out = {k: _plain(v[r]) for k, r in refs.items()}
    datum = v[refs["datum"]]
    if isinstance(datum, (int, float)) and not isinstance(datum, bool):
        datum = F.from_serial(datum)
    out["datum"] = datum.date().isoformat() if isinstance(datum, dt.datetime) else None
    for k in ("gesamt", "anteil", "kats"):
        if out[k] is not None and not isinstance(out[k], (int, float)):
            out[k] = None
    for k in ("gesamt", "kats"):  # floating point noise: 6.800000000000001 -> 6.8
        if isinstance(out[k], float):
            out[k] = _plain(round(out[k], 6))
    return out


# the layout of "Anlage 3 - Verwendungsnachweis mit Raumkosten": checked on upload, so a changed
# form is rejected instead of being filled in the wrong cells
LAYOUT = {
    ("Verwendungsnachweis", "A37"): "Übungen",
    ("Verwendungsnachweis", "A38"): "Ausbildung",
    ("Verwendungsnachweis", "A39"): "Verwaltung",
    ("Verwendungsnachweis", "A40"): "Insgesamt",
    ("Verwendungsnachweis", "A46"): "Anteil der Ausbildungen",
    ("Kosten", "E1"): "Art",
    ("Kosten", "F1"): "Thema",
    ("Kosten", "I1"): "Gesamt",
    ("Kosten", "J1"): "Anteil",
}
LAYOUT.update(RK.LAYOUT)
DEFAULT_MINDESTANTEIL = 0.6


def settings() -> dict[str, Any]:
    """Zuwendung (share of the Gliederung after the Binnenverteilung; None = as in the uploaded
    file) and the minimum share of Ausbildung + Übung."""
    try:
        s = json.loads(C.VN_SETTINGS.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        s = {}
    return {"zuwendung": s.get("zuwendung"), "mindestanteil": s.get("mindestanteil") or DEFAULT_MINDESTANTEIL}


def save_settings(zuwendung: float | None, mindestanteil: float) -> None:
    if zuwendung is not None and zuwendung <= 0:
        raise ValueError("Die Zuwendung muss größer als 0 sein")
    if not 0 < mindestanteil <= 1:
        raise ValueError("Der Mindestanteil muss zwischen 1 und 100 % liegen")
    C.VN_DIR.mkdir(parents=True, exist_ok=True)
    tmp = C.VN_SETTINGS.with_suffix(".tmp")
    tmp.write_text(json.dumps({"zuwendung": zuwendung, "mindestanteil": mindestanteil}, indent=1), "utf-8")
    os.replace(tmp, C.VN_SETTINGS)


def _apply_settings(wb: openpyxl.Workbook, st: dict[str, Any]) -> None:
    vn = wb["Verwendungsnachweis"]
    if st["zuwendung"] is not None:
        vn[SUMMARY["zuwendung"]].value = st["zuwendung"]
    if abs(st["mindestanteil"] - DEFAULT_MINDESTANTEIL) > 1e-9:
        pct = f"{st['mindestanteil'] * 100:g}"
        vn["J46"].value = f'=IF(L37>={st["mindestanteil"]:g},"i.O.","zu gering")'
        vn["A46"].value = f"Anteil der Ausbildungen und Übungen ≥ {pct}%"


def basis_info() -> dict[str, Any] | None:
    if not C.VN_BASIS.exists():
        return None
    wb = openpyxl.load_workbook(C.VN_BASIS, data_only=True)
    return {
        "jahr": wb["Raumkosten"]["B5"].value,
        "gliederung": wb["Verwendungsnachweis"]["F14"].value,
        "zuwendung": wb["Verwendungsnachweis"]["F20"].value,
        "zeilen": len(_existing(wb["Kosten"])),
        "geaendert": dt.datetime.fromtimestamp(C.VN_BASIS.stat().st_mtime).isoformat(timespec="seconds"),
    }


def check_basis(path: Path) -> None:
    wb = openpyxl.load_workbook(path)
    missing = [s for s in REQUIRED_SHEETS if s not in wb.sheetnames]
    if missing:
        raise ValueError(f"Blatt fehlt: {', '.join(missing)}")
    for (sheet, cell), text in LAYOUT.items():
        if not str(wb[sheet][cell].value or "").strip().startswith(text):
            raise ValueError(f"unerwarteter Aufbau – in {sheet}!{cell} steht nicht „{text}“ "
                             "(erwartet: Anlage 3 – Verwendungsnachweis mit Raumkosten)")


def _is_free(ws, row: int) -> bool:
    # Art and Anteil may be pre-filled in empty rows - a row is used once it has a Thema or an amount
    return ws.cell(row, 6).value in (None, "") and ws.cell(row, 9).value in (None, "")


def _key(datum: Any, thema: Any) -> tuple[str, str]:
    if isinstance(datum, dt.datetime):
        datum = datum.date()
    if isinstance(datum, dt.date):
        datum = datum.isoformat()
    return str(datum or ""), str(thema or "").strip().casefold()


def _existing(ws) -> set[tuple[str, str]]:
    return {_key(ws.cell(r, 8).value, ws.cell(r, 6).value)
            for r in range(FIRST_ROW, LAST_ROW + 1) if not _is_free(ws, r)}


def entry(job: dict[str, Any], jahr: Any = None) -> dict[str, Any]:
    """One Vorgang as a Kosten row, with the reason if it cannot be taken over yet."""
    exp = job.get("export") or {}
    s = exp.get("summen") or {}
    assigned = {p["sheet"] for p in job["pages"] if p.get("sheet")}
    status = FINAL
    if not exp:
        status = "noch kein Excel erzeugt"
    elif exp.get("veraltet"):
        status = "nach dem Export geändert – Excel neu erzeugen"
    elif not s:
        status = "Summen fehlen – Excel neu erzeugen"
    elif not assigned <= set(job.get("reviewed") or []):
        status = "noch nicht alle Blätter geprüft"
    elif s.get("art") not in ARTEN:
        status = "Veranstaltungsart muss Ausbildung oder Übung sein"
    elif not s.get("datum"):
        status = "Datum fehlt"
    elif jahr and not str(s["datum"]).startswith(str(jahr)):
        status = f"nicht aus {jahr}"
    return {"id": job["id"], "title": J.title(job), "status": status, **s}


def entries(jahr: Any = None) -> list[dict[str, Any]]:
    return sorted((entry(j, jahr) for j in J.all_jobs()), key=lambda e: (e.get("datum") or "", e["title"]))


def output_name(jahr: Any) -> str:
    return f"Verwendungsnachweis {jahr or ''}".strip() + ".xlsx"


def generate(rows: list[dict[str, Any]], dst: Path) -> dict[str, Any]:
    """Base + rows -> dst; returns the recalculated summary and what was written/skipped."""
    wb = openpyxl.load_workbook(C.VN_BASIS)
    st = settings()
    _apply_settings(wb, st)
    raeume = RK.saved()
    if raeume is not None:
        RK.write(wb, raeume)
    ws = wb["Kosten"]
    existing = _existing(ws)
    written, skipped = [], []
    row = FIRST_ROW
    for e in rows:
        key = _key(e["datum"], e["thema"])
        if key in existing:
            skipped.append(e["id"])
            continue
        while row <= LAST_ROW and not _is_free(ws, row):
            row += 1
        if row > LAST_ROW:
            raise ValueError("Kostenblatt ist voll")
        values = [e["gliederungsnummer"], e["art"], e["thema"], e["ort"],
                  dt.datetime.fromisoformat(e["datum"]), e["gesamt"], e["anteil"]]
        for col, value in zip(range(4, 11), values):
            ws.cell(row, col).value = value
        existing.add(key)
        written.append({"id": e["id"], "row": row})
        row += 1
    W._save(wb, dst)
    v = W.calculate(dst, [f"Verwendungsnachweis!{c}" for c in SUMMARY.values()] + RK.refs())
    return {
        "summary": {k: _plain(v[f"Verwendungsnachweis!{c}"]) for k, c in SUMMARY.items()},
        "einstellungen": st,
        "raumkosten": raeume,
        "raumkosten_kosten": {r: _plain(v[r]) for r in RK.refs()},
        "written": written,
        "skipped": skipped,
    }


def calculate() -> dict[str, Any]:
    info = basis_info()
    if info is None:
        raise FileNotFoundError("Verwendungsnachweis fehlt")
    final = [e for e in entries(info["jahr"]) if e["status"] == FINAL]
    name = output_name(info["jahr"])
    result = generate(final, C.AUSGANG / name)
    stand = {"at": J._now(), "file": name, "basis": info["geaendert"],
             "exports": {e["id"]: J.load(e["id"])["export"]["at"] for e in final}, **result}
    C.VN_STAND.write_text(json.dumps(stand, ensure_ascii=False, indent=1, default=str), "utf-8")
    return stand


def stand() -> dict[str, Any] | None:
    try:
        return json.loads(C.VN_STAND.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def is_outdated(st: dict[str, Any], info: dict[str, Any] | None, rows: list[dict[str, Any]]) -> bool:
    if not info or st.get("basis") != info["geaendert"] or st.get("einstellungen") != settings() \
            or st.get("raumkosten") != RK.saved():
        return True
    current = {e["id"]: (J.load(e["id"]).get("export") or {}).get("at") for e in rows if e["status"] == FINAL}
    return current != st.get("exports")
