"""Plausibility hints for the review UI. The model never decides alone: every value can be
checked against the template's own rules."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import openpyxl

from . import config as C
from . import fields as F
from . import workbook as W


@lru_cache(maxsize=1)
def gliederungen() -> dict[int, str]:
    """Gliederungsnummer (LV*100000 + Bezirk*1000 + OG) -> name, from the template sheet."""
    try:
        ws = openpyxl.load_workbook(C.VORLAGE_LEER, read_only=True)["Gliederungen"]
    except (OSError, KeyError):
        return {}
    out = {}
    for row in ws.iter_rows(min_row=2, max_col=5, values_only=True):
        lv, bez, og, ebene, name = row
        if isinstance(lv, (int, float)) and isinstance(bez, (int, float)) and isinstance(og, (int, float)):
            out[int(lv) * 100000 + int(bez) * 1000 + int(og)] = f"{ebene} {name}"
    return out


def check(data: dict[str, Any]) -> dict[str, dict[str, str]]:
    """{sheet_key: {input name: message}}; input names as in the review form."""
    out: dict[str, dict[str, str]] = {}
    for sheet in F.SHEETS:
        sd = data.get(sheet.key) or {}
        msgs: dict[str, str] = {}
        fields_ = sd.get("fields") or {}
        for f in sheet.fields:
            raw = fields_.get(f.key)
            try:
                value = W.convert(raw, f.type, f.options)
            except W.ValueError_ as e:
                msgs[f"f:{f.key}"] = str(e)
                continue
            if value is None:
                continue
            if f.type == F.IBAN and not W.iban_valid(value):
                msgs[f"f:{f.key}"] = "IBAN-Prüfziffer stimmt nicht"
            if f.key == "gliederungsnummer" and gliederungen() and value not in gliederungen():
                msgs[f"f:{f.key}"] = "Gliederungsnummer nicht in der Liste der Vorlage"
        for t in sheet.tables:
            rows = (sd.get("tables") or {}).get(t.key) or []
            for i, row in enumerate(rows[: t.rows]):
                for k, _lbl, _c, typ in t.columns:
                    try:
                        W.convert(row.get(k), typ)
                    except W.ValueError_ as e:
                        msgs[f"t:{t.key}:{i}:{k}"] = str(e)
        if msgs:
            out[sheet.key] = msgs
    return out


def gliederung_name(data: dict[str, Any]) -> str | None:
    raw = ((data.get("abrechnung") or {}).get("fields") or {}).get("gliederungsnummer")
    try:
        n = W.convert(raw, F.INT)
    except W.ValueError_:
        return None
    return gliederungen().get(n) if n else None
