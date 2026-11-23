"""Fill the Excel template from a reviewed Vorgang.

Only cells from the field map are written (never formulas). Values are converted to real
Excel types (dates, times, numbers), so the template's own formulas calculate as usual.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.workbook.properties import CalcProperties

from . import config as C
from . import formulas as XF
from . import tools as T
from . import fields as F


class ValueError_(ValueError):
    pass


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def parse_date(value: Any) -> dt.datetime | None:
    s = _clean(value)
    if not s:
        return None
    s = s.replace("/", ".").replace("-", ".")
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})", s)
    if not m:
        m2 = re.fullmatch(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", s)
        if not m2:
            raise ValueError_(f"Datum nicht lesbar: {value!r}")
        y, mo, d = int(m2[1]), int(m2[2]), int(m2[3])
    else:
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        if y < 100:
            y += 2000
    return dt.datetime(y, mo, d)


def parse_time(value: Any) -> dt.timedelta | None:
    """hh:mm as duration since midnight (like the template, format [h]:mm); 24:00 allowed."""
    s = _clean(value).lower().replace("uhr", "").strip()
    if not s:
        return None
    m = re.fullmatch(r"(\d{1,2})(?:[:.,h](\d{2}))?", s)
    if not m:
        raise ValueError_(f"Uhrzeit nicht lesbar: {value!r}")
    h, mi = int(m[1]), int(m[2] or 0)
    if not (0 <= mi < 60 and (0 <= h < 24 or (h == 24 and mi == 0))):
        raise ValueError_(f"Uhrzeit ungültig: {value!r}")
    return dt.timedelta(hours=h, minutes=mi)


def parse_number(value: Any) -> float | None:
    s = _clean(value).replace("€", "").replace(" ", "")
    if not s:
        return None
    # German notation: 1.234,56 -> 1234.56
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError as e:
        raise ValueError_(f"Zahl nicht lesbar: {value!r}") from e


def normalize_iban(value: Any) -> str | None:
    s = re.sub(r"\s+", "", _clean(value)).upper()
    return s or None


def iban_valid(iban: str) -> bool:
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", iban):
        return False
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


def convert(value: Any, typ: str, options: tuple[str, ...] = ()) -> Any:
    """Raw (possibly handwritten-OCR) string -> value written into Excel."""
    s = _clean(value)
    if s == "":
        return None
    if typ == F.DATE:
        return parse_date(s)
    if typ == F.TIME:
        return parse_time(s)
    if typ == F.INT:
        n = parse_number(s)
        return None if n is None else int(round(n))
    if typ == F.MONEY:
        n = parse_number(s)
        return None if n is None else round(n, 2)
    if typ == F.PERCENT:
        n = parse_number(s.replace("%", ""))
        return None if n is None else (n / 100 if n > 1 else n)
    if typ == F.JA_NEIN_UPPER:
        return _ja_nein(s).upper()
    if typ == F.JA_NEIN_LOWER:
        return _ja_nein(s)
    if typ == F.IBAN:
        return normalize_iban(s)
    if typ == F.ENUM:
        for opt in options:
            if opt.lower() == s.lower():
                return opt
        raise ValueError_(f"Erlaubt: {', '.join(options)} – gelesen: {value!r}")
    return s


def _ja_nein(s: str) -> str:
    t = s.strip().lower()
    if t in ("ja", "j", "x", "yes", "y", "1", "true"):
        return "ja"
    if t in ("nein", "n", "no", "0", "false"):
        return "nein"
    raise ValueError_(f"ja/nein erwartet, gelesen: {s!r}")


def blank_template(src: Path, dst: Path) -> None:
    """Copy of the template with every input cell emptied (removes the Muster example data)."""
    wb = openpyxl.load_workbook(src)
    for sheet in F.SHEETS:
        ws = wb[sheet.name]
        for cell in F.all_input_cells(sheet):
            ws[cell].value = None
        for f in sheet.fields:
            if f.default is not None:
                ws[f.cell].value = convert(f.default, f.type, f.options)
    _save(wb, dst)


# Formulas missing in the template, added on export (only if the cell is still empty, so a
# corrected template version wins): Aufwandsvergütung "Anreise- und Abreisetag" (row 25) has
# no "€ je Teilnehmer" and "Gesamt", unlike the other rows and the Tagegeld row 17.
TEMPLATE_FIXES = {
    ("Tagegeld_Aufwandsvergütung", "D25"): "=$B25*$C25",
    ("Tagegeld_Aufwandsvergütung", "H25"): "=B25*C25*$F$23",
}


def fill(template: Path, data: dict[str, Any], dst: Path) -> list[str]:
    """Write reviewed values into a copy of the blank template.

    data = {sheet_key: {"fields": {key: raw}, "tables": {table_key: [{col: raw}, ...]}}}
    Returns a list of conversion problems (cells that were left empty).
    """
    wb = openpyxl.load_workbook(template)
    problems: list[str] = []

    for sheet in F.SHEETS:
        sheet_data = data.get(sheet.key) or {}
        ws = wb[sheet.name]
        for f in sheet.fields:
            raw = (sheet_data.get("fields") or {}).get(f.key)
            if _clean(raw) == "" and f.default is not None:
                raw = f.default
            if _clean(raw) == "" and f.formula:
                ws[f.cell].value = f.formula
                continue
            _write(ws, f.cell, raw, f.type, f.options, f"{sheet.name} › {f.label}", problems)
        for table in sheet.tables:
            rows = (sheet_data.get("tables") or {}).get(table.key) or []
            for i, col_key, cell, typ in F.table_cells(table):
                raw = rows[i].get(col_key) if i < len(rows) and isinstance(rows[i], dict) else None
                _write(ws, cell, raw, typ, (), f"{sheet.name} › {table.label} Zeile {i + 1}", problems)

    for (sheet_name, cell), formula in TEMPLATE_FIXES.items():
        if wb[sheet_name][cell].value in (None, ""):
            wb[sheet_name][cell].value = formula

    _save(wb, dst)
    return problems


def _write(ws, cell: str, raw: Any, typ: str, options: tuple[str, ...], where: str, problems: list[str]) -> None:
    try:
        value = convert(raw, typ, options)
    except ValueError_ as e:
        problems.append(f"{where}: {e}")
        value = None
    ws[cell].value = value


class FileLocked(RuntimeError):
    """Windows: the target file is open in Excel."""


def _save(wb: openpyxl.Workbook, dst: Path) -> None:
    # Excel and LibreOffice recalculate every formula when the file is opened
    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.tmp")
    wb.save(tmp)
    try:
        os.replace(tmp, dst)
    except PermissionError:
        tmp.unlink(missing_ok=True)
        raise FileLocked(f"„{dst.name}“ ist noch geöffnet (z. B. in Excel) – bitte schließen und erneut erzeugen")


def recalculate(src: Path) -> openpyxl.Workbook:
    """Every formula's value, calculated by LibreOffice."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "in").mkdir()
        f = tmp_path / "in" / "wb.xlsx"
        shutil.copy(src, f)
        out = T.soffice_convert(f, tmp_path / "out")
        return openpyxl.load_workbook(out, data_only=True)


def calculate(src: Path, refs: list[str]) -> dict[str, Any]:
    """{'Sheet!A1': value}: computed by the built-in evaluator (no office program needed),
    LibreOffice only for formulas it does not know."""
    try:
        return XF.evaluate(src, refs)
    except XF.Unsupported as e:
        if not C.soffice_available():
            raise RuntimeError(f"Formel wird nicht unterstützt ({e}) und LibreOffice fehlt")
        logging.getLogger("dotationslisten").warning("Formel nicht unterstützt (%s) – rechne mit LibreOffice", e)
        wb = recalculate(src)
        values = {}
        for ref in refs:
            sheet, _, cell = ref.rpartition("!")
            v = wb[sheet][cell].value
            values[ref] = XF.serial(v) if isinstance(v, (dt.date, dt.datetime)) else v
        return values
