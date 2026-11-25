"""Import finished Abrechnungen from Excel (filled copies of the template, .xlsx or .xls).

The input cells of the field map are read back into the raw text form the review UI uses
("17.10.2026", "07:30", "12,50", "100" for 100 %), so an imported Vorgang behaves like one
entered by hand. Formulas are never imported - the export recalculates everything.

The imported file is the Vorgang's Excel: it goes to "ausgang" as it is (an .xls as the .xlsx
LibreOffice makes of it) and its totals go into the Verwendungsnachweis. The values are read so
that a later "Excel erzeugen" gives the same totals: a formula cell that was emptied in Excel
(e.g. "Gezahlte Tagegelder") becomes 0, and the Teilnehmeranzahl is not filled in by the app.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

import openpyxl

from . import config as C
from . import tools as T
from . import fields as F
from . import formulas as XF
from . import jobs as J
from . import verwendungsnachweis as VN
from . import workbook as W

SUFFIXES = {".xlsx", ".xls"}
IMPORT = "import"  # page kind
_lock = threading.Lock()  # two uploads of the same file at once must not both pass the check


def is_import(job: dict[str, Any]) -> bool:
    return any(p.get("kind") == IMPORT for p in job.get("pages", []))


def _num(v: float, decimals: int = 2) -> str:
    s = f"{v:.{decimals}f}".rstrip("0").rstrip(".") if decimals else str(int(round(v)))
    return s.replace(".", ",")


def to_raw(value: Any, typ: str) -> str:
    """Excel cell value -> text as typed in the review form."""
    if value is None:
        return ""
    if isinstance(value, str):
        return "" if value.startswith("=") else value.strip()
    if typ == F.DATE:
        if isinstance(value, (dt.datetime, dt.date)):
            return value.strftime("%d.%m.%Y")
    if typ == F.TIME:
        if isinstance(value, dt.datetime):
            value = value.time()
        if isinstance(value, dt.time):
            return f"{value.hour:02d}:{value.minute:02d}"
        if isinstance(value, (int, float)):  # fraction of a day
            value = dt.timedelta(days=value)
        if isinstance(value, dt.timedelta):
            minutes = round(value.total_seconds() / 60)
            return f"{minutes // 60:02d}:{minutes % 60:02d}"
    if isinstance(value, bool):
        return "ja" if value else "nein"
    if isinstance(value, (int, float)):
        if typ == F.MONEY:
            return f"{value:.2f}".replace(".", ",")
        if typ == F.PERCENT:
            return _num(value * 100 if value <= 1 else value, 1)
        if typ == F.INT or float(value).is_integer():
            return str(int(round(value)))
        return _num(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.strftime("%d.%m.%Y")
    return str(value).strip()


def _is_formula(v: Any) -> bool:
    return isinstance(v, str) and v.startswith("=")


def formula_refs(wb: openpyxl.Workbook) -> list[str]:
    """Cells whose calculated value read_data needs: the targets of the fields' own formulas
    and every input cell that holds some other formula in this file."""
    refs = []
    for sheet in F.SHEETS:
        if sheet.name not in wb.sheetnames:
            continue
        ws = wb[sheet.name]
        for f in sheet.fields:
            if f.formula:
                refs.append(f.formula.lstrip("="))
            if _is_formula(ws[f.cell].value) and ws[f.cell].value != f.formula:
                refs.append(f"{sheet.name}!{f.cell}")
    return refs


def read_data(wb: openpyxl.Workbook, values: dict[str, Any] | None = None) -> dict[str, Any]:
    """{sheet_key: {"fields": ..., "tables": ...}} for every template sheet that holds a value.
    values: the calculated values of formula_refs(wb). An input cell keeps what it gave in the
    file: its own formula stays a formula (""), another formula becomes its value, a formula
    cell emptied in Excel becomes 0."""
    values = values or {}
    data: dict[str, Any] = {}
    for sheet in F.SHEETS:
        if sheet.name not in wb.sheetnames:
            continue
        ws = wb[sheet.name]
        fields = {}
        for f in sheet.fields:
            v = ws[f.cell].value
            if _is_formula(v) and v != f.formula:
                v = values.get(f"{sheet.name}!{f.cell}")  # e.g. the Tagegeld link one row too high
                if isinstance(v, XF.XLError):
                    v = None
            fields[f.key] = to_raw(v, f.type)
            if f.formula and v in (None, "") and values.get(f.formula.lstrip("=")) not in (None, "", 0):
                fields[f.key] = "0"  # emptied in Excel: the export must not bring the formula back
        tables = {}
        for t in sheet.tables:
            rows = []
            for i in range(t.rows):
                row_no = t.first_row + i * t.row_step
                rows.append({k: to_raw(ws[f"{col}{row_no}"].value, typ) for k, _l, col, typ in t.columns})
            while rows and not any(rows[-1].values()):
                rows.pop()
            tables[t.key] = rows
        if sheet.key == "abrechnung" or any(fields.values()) or any(tables.values()):
            data[sheet.key] = {"fields": fields, "tables": tables}
    return data


def _as_xlsx(path: Path, tmp: Path) -> Path:
    if path.suffix.lower() == ".xlsx":
        return path
    if not C.soffice_available():
        raise ValueError(".xls-Dateien brauchen LibreOffice (kostenlos: libreoffice.org) – oder in Excel als .xlsx speichern")
    src = tmp / "in" / ("abrechnung" + path.suffix.lower())  # .xls -> .xlsx (LibreOffice)
    src.parent.mkdir()
    shutil.copy(path, src)
    return T.soffice_convert(src, tmp / "out")


def import_file(path: Path, name: str) -> str | None:
    """Excel file -> new Vorgang (all sheets marked as geprüft, the file itself as its Excel).
    Returns the job id, or None if the same file was imported before."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if any(j.get("source_hash") == digest for j in J.all_jobs()):
        return None
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        xlsx = _as_xlsx(path, Path(tmp))
        wb = openpyxl.load_workbook(xlsx)
        if "Abrechnungsbogen" not in wb.sheetnames:
            raise ValueError("kein Abrechnungsbogen in der Datei")
        data = read_data(wb, W.calculate(xlsx, formula_refs(wb)))
        summen = VN.abrechnung_summen(xlsx)
        with _lock:
            if any(j.get("source_hash") == digest for j in J.all_jobs()):
                return None
            job = J.new_manual_job(list(data))
            for p in job["pages"]:
                p["kind"] = IMPORT
            job.update(source=f"Import: {name}", source_hash=digest, data=data, reviewed=list(data))
            out = J.export_name(job)
            C.AUSGANG.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(xlsx, C.AUSGANG / out)
            job["export"] = {"file": out, "problems": [], "at": J._now(), "summen": summen, "import": True}
            J.save(job)
            shutil.copyfile(path, J.job_dir(job["id"]) / ("original" + path.suffix.lower()))
    return job["id"]
