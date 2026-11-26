"""Raumkosten of the Verwendungsnachweis: up to 10 Gebäude with 8 Räume each.

Each Raum has a Nutzungsart (Ausbildung or Verwaltung) and a KatS share; the Kosten sheet links
rows 2-81 to these rooms, so they make up the Verwaltung line (and part of Ausbildung).

The values are read from the uploaded Verwendungsnachweis. Changed in the app, they are kept in
raumkosten.json and written into the new file on every calculation - the uploaded file stays
as it is. A new upload discards them (the new file is the new starting point).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import openpyxl

from . import config as C

SHEET = "Raumkosten"
GEBAEUDE, RAEUME = 10, 8
BESITZ = ("Eigentum", "Gemietet")
NUTZUNG = ("Ausbildung", "Verwaltung")

# (key, label, column, type) - type: text | num | pct | besitz | nutzung
GEBAEUDE_FIELDS = (
    ("anschrift", "Anschrift", "A", "text"),
    ("ort", "Ort", "B", "text"),
    ("besitz", "Besitzverhältnis", "D", "besitz"),
    ("flaeche", "Gesamtfläche (qm)", "E", "num"),
    ("miete", "Mietpreis pro Monat (€)", "G", "num"),
    ("nebenkosten", "Nebenkosten im Jahr (€)", "I", "num"),
)
RAUM_FIELDS = (
    ("raum", "Raumbezeichnung", "A", "text"),
    ("nutzung", "Nutzungsart", "B", "nutzung"),
    ("groesse", "Größe (qm)", "C", "num"),
    ("miete_qm", "Miete pro qm und Monat (€)", "E", "num"),
    ("anteil", "Anteil KatS (%)", "J", "pct"),
)


def header_row(g: int) -> int:
    return 8 + 14 * g


def room_row(g: int, r: int) -> int:
    return header_row(g) + 3 + r


def sum_ref(g: int) -> str:
    return f"{SHEET}!K{header_row(g) + 11}"


def room_ref(g: int, r: int) -> str:
    return f"{SHEET}!K{room_row(g, r)}"


# checked on upload together with the Verwendungsnachweis layout
LAYOUT = {(SHEET, f"A{header_row(g) - 1}"): f"Gebäude {g + 1}" for g in range(GEBAEUDE)}
LAYOUT.update({(SHEET, f"A{header_row(g) + 1}"): "Raumbezeichnung" for g in range(GEBAEUDE)})
LAYOUT[(SHEET, "J9")] = "Anteil"


def _cell(v: Any, typ: str) -> Any:
    if v in (None, "") or (isinstance(v, str) and v.startswith("=")):
        return None
    if typ in ("num", "pct"):
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    return str(v).strip() or None


def read(wb: openpyxl.Workbook) -> list[dict[str, Any]]:
    ws = wb[SHEET]
    out = []
    for g in range(GEBAEUDE):
        h = header_row(g)
        geb = {k: _cell(ws[f"{col}{h}"].value, typ) for k, _l, col, typ in GEBAEUDE_FIELDS}
        geb["raeume"] = [{k: _cell(ws[f"{col}{room_row(g, r)}"].value, typ) for k, _l, col, typ in RAUM_FIELDS}
                         for r in range(RAEUME)]
        out.append(geb)
    return out


def write(wb: openpyxl.Workbook, gebaeude: list[dict[str, Any]]) -> None:
    ws = wb[SHEET]
    for g, geb in enumerate(gebaeude[:GEBAEUDE]):
        h = header_row(g)
        for k, _l, col, _t in GEBAEUDE_FIELDS:
            ws[f"{col}{h}"].value = geb.get(k)
        for r, raum in enumerate((geb.get("raeume") or [])[:RAEUME]):
            for k, _l, col, _t in RAUM_FIELDS:
                ws[f"{col}{room_row(g, r)}"].value = raum.get(k)


def is_empty(geb: dict[str, Any]) -> bool:
    return not any(geb.get(k) is not None for k, *_ in GEBAEUDE_FIELDS) and \
        not any(v is not None for raum in geb.get("raeume") or [] for v in raum.values())


def saved() -> list[dict[str, Any]] | None:
    """The values changed in the app, or None (= as in the uploaded file)."""
    try:
        return json.loads(C.VN_RAUMKOSTEN.read_text("utf-8"))["gebaeude"]
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def current() -> list[dict[str, Any]] | None:
    own = saved()
    if own is not None:
        return own
    if not C.VN_BASIS.exists():
        return None
    return read(openpyxl.load_workbook(C.VN_BASIS))


def save(gebaeude: list[dict[str, Any]]) -> None:
    C.VN_DIR.mkdir(parents=True, exist_ok=True)
    tmp = C.VN_RAUMKOSTEN.with_suffix(".tmp")
    tmp.write_text(json.dumps({"gebaeude": gebaeude}, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, C.VN_RAUMKOSTEN)


def reset() -> None:
    C.VN_RAUMKOSTEN.unlink(missing_ok=True)


def _number(text: Any, label: str) -> float | None:
    t = str(text or "").strip().replace("€", "").replace("%", "").replace(" ", "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        raise ValueError(f"{label}: keine Zahl („{text}“)")


def _parse(raw: Any, typ: str, label: str) -> Any:
    text = str(raw or "").strip()
    if typ == "text":
        return text or None
    if typ == "besitz":
        if text and text not in BESITZ:
            raise ValueError(f"{label}: Eigentum oder Gemietet")
        return text or None
    if typ == "nutzung":
        if text and text not in NUTZUNG:
            raise ValueError(f"{label}: Ausbildung oder Verwaltung")
        return text or None
    v = _number(text, label)
    if v is not None and v < 0:
        raise ValueError(f"{label}: darf nicht negativ sein")
    if typ == "pct" and v is not None:
        if v > 100:
            raise ValueError(f"{label}: höchstens 100 %")
        return v / 100
    return v


def from_form(form: Any) -> list[dict[str, Any]]:
    """Form fields g<n>_<key> and g<n>_r<m>_<key> -> list of Gebäude. Raises ValueError."""
    out = []
    for g in range(GEBAEUDE):
        name = f"Gebäude {g + 1}"
        geb = {k: _parse(form.get(f"g{g}_{k}"), t, f"{name} › {lbl}") for k, lbl, _c, t in GEBAEUDE_FIELDS}
        geb["raeume"] = []
        for r in range(RAEUME):
            raum = {k: _parse(form.get(f"g{g}_r{r}_{k}"), t, f"{name} › Raum {r + 1} › {lbl}")
                    for k, lbl, _c, t in RAUM_FIELDS}
            if raum["groesse"] is not None and raum["nutzung"] is None:
                raise ValueError(f"{name} › Raum {r + 1}: Nutzungsart fehlt (sonst zählt der Raum nirgends)")
            geb["raeume"].append(raum)
        if any(raum["groesse"] for raum in geb["raeume"]) and not geb["flaeche"]:
            raise ValueError(f"{name}: Gesamtfläche fehlt")
        out.append(geb)
    return out


def _fmt(v: Any, typ: str) -> str:
    if v is None:
        return ""
    if typ == "pct":
        v = v * 100
    if typ in ("num", "pct"):
        return f"{v:.4f}".rstrip("0").rstrip(".").replace(".", ",")
    return str(v)


def form_view(gebaeude: list[dict[str, Any]], kosten: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Gebäude with the values as form text and the calculated Kosten KatS (if known)."""
    kosten = kosten or {}
    out = []
    for g, geb in enumerate(gebaeude):
        flaeche, miete = geb.get("flaeche"), geb.get("miete")
        raeume = [{"n": r, **{k: _fmt(raum.get(k), t) for k, _l, _c, t in RAUM_FIELDS},
                   "kosten": kosten.get(room_ref(g, r))} for r, raum in enumerate(geb.get("raeume") or [])]
        out.append({"n": g, "leer": is_empty(geb), **{k: _fmt(geb.get(k), t) for k, _l, _c, t in GEBAEUDE_FIELDS},
                    "miete_qm": _fmt(round(miete / flaeche, 2), "num") if miete and flaeche else "",
                    "summe": kosten.get(sum_ref(g)), "raeume": raeume})
    return out


def refs() -> list[str]:
    return [room_ref(g, r) for g in range(GEBAEUDE) for r in range(RAEUME)] + [sum_ref(g) for g in range(GEBAEUDE)]


def raw_view(form: Any) -> list[dict[str, Any]]:
    """The submitted form again as form_view (after an input error nothing is lost)."""
    out = []
    for g in range(GEBAEUDE):
        geb = {k: str(form.get(f"g{g}_{k}") or "") for k, *_ in GEBAEUDE_FIELDS}
        raeume = [{"n": r, **{k: str(form.get(f"g{g}_r{r}_{k}") or "") for k, *_ in RAUM_FIELDS}, "kosten": None}
                  for r in range(RAEUME)]
        leer = not any(geb.values()) and not any(v for raum in raeume for k, v in raum.items() if k not in ("n", "kosten"))
        out.append({"n": g, "leer": leer, **geb, "miete_qm": "", "summe": None, "raeume": raeume})
    return out
