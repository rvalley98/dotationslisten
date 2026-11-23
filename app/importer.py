"""Import finished Abrechnungen from Excel (filled copies of the template, .xlsx or .xls).

The input cells of the field map are read back into the raw text form the review UI uses
("17.10.2026", "07:30", "12,50", "100" for 100 %), so an imported Vorgang behaves like one
entered by hand. Formulas are never imported - the export recalculates everything.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Any

import openpyxl

from . import config as C
from . import tools as T
from . import fields as F
from . import jobs as J

SUFFIXES = {".xlsx", ".xls"}
IMPORT = "import"  # page kind


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


def read_data(wb: openpyxl.Workbook) -> dict[str, Any]:
    """{sheet_key: {"fields": ..., "tables": ...}} for every template sheet that holds a value."""
    data: dict[str, Any] = {}
    for sheet in F.SHEETS:
        if sheet.name not in wb.sheetnames:
            continue
        ws = wb[sheet.name]
        fields = {f.key: to_raw(ws[f.cell].value, f.type) for f in sheet.fields}
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


def _load(path: Path) -> openpyxl.Workbook:
    if path.suffix.lower() == ".xlsx":
        return openpyxl.load_workbook(path)
    if not C.soffice_available():
        raise ValueError(".xls-Dateien brauchen LibreOffice (kostenlos: libreoffice.org) – oder in Excel als .xlsx speichern")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:  # .xls -> .xlsx (LibreOffice)
        src = Path(tmp) / "in" / ("abrechnung" + path.suffix.lower())
        src.parent.mkdir()
        shutil.copy(path, src)
        return openpyxl.load_workbook(T.soffice_convert(src, Path(tmp) / "out"))


def import_file(path: Path, name: str) -> str | None:
    """Excel file -> new Vorgang (all sheets marked as geprüft). Returns the job id, or None if
    the same file was imported before."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if any(j.get("source_hash") == digest for j in J.all_jobs()):
        return None
    wb = _load(path)
    if "Abrechnungsbogen" not in wb.sheetnames:
        raise ValueError("kein Abrechnungsbogen in der Datei")
    data = read_data(wb)
    job = J.new_manual_job(list(data))
    for p in job["pages"]:
        p["kind"] = IMPORT
    job.update(source=f"Import: {name}", source_hash=digest, data=data, reviewed=list(data))
    J.save(job)
    return job["id"]
