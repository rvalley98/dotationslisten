"""Web UI for the home LAN: upload/scan intake, review each page next to its fields, export."""

from __future__ import annotations

import copy
import json
import logging
import threading
import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as FormFile

from . import checks
from . import config as C
from . import fields as F
from . import jobs as J
from . import importer
from . import pages as P
from . import rules
from . import updates
from . import verwendungsnachweis as VN
from . import workbook as W
from .recognize import from_config
from .setup_template import prepare
from .worker import Worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    C.ensure_dirs()
    updates.start()
    rec = from_config()
    state["recognizer"] = rec
    if os.environ.get("WORKER", "1") == "1":
        w = Worker(rec)
        w.start()
        state["worker"] = w
    yield
    if "worker" in state:
        state["worker"].stop()


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
SHEET_CHOICES = [(s.key, s.name) for s in F.SHEETS]


def _eur(value: Any) -> str:
    """1234.5 -> "1.234,50 €" """
    if not isinstance(value, (int, float)):
        return "–"
    return f"{value:,.2f} €".replace(",", "_").replace(".", ",").replace("_", ".")


def _pct(value: Any) -> str:
    return f"{value * 100:.1f} %".replace(".", ",") if isinstance(value, (int, float)) else "–"


def _datum(value: Any) -> str:
    """2026-10-17 -> 17.10.2026"""
    y, m, d = (str(value or "").split("-") + ["", "", ""])[:3]
    return f"{d}.{m}.{y}" if y and m and d else "–"


templates.env.filters["datum"] = _datum
templates.env.filters["eur"] = _eur
templates.env.filters["pct"] = _pct
templates.env.globals["version"] = C.VERSION


def _status() -> dict[str, Any]:
    w = state.get("worker")
    rec = state["recognizer"]
    ok, msg = w.status if w else rec.status()
    ollama = "ok" if ok else ("modell" if "fehlt" in msg else ("offline" if rec.enabled else "aus"))
    return {"template": C.VORLAGE_LEER.exists(), "recog_ok": ok, "recog_msg": msg,
            "recog_enabled": rec.enabled, "busy": w.busy if w else None,
            "soffice": C.soffice_available(), "ollama": ollama, "ollama_source": C.OLLAMA_SOURCE, "model": C.OLLAMA_MODEL, "pull": pull,
            "new_release": updates.info()}


# Download of the recognition model through Ollama (several GB, runs in the background)
pull: dict[str, Any] = {"running": False}


def _pull_run() -> None:
    try:
        with httpx.stream("POST", f"{C.OLLAMA_URL}/api/pull", json={"model": C.OLLAMA_MODEL, "stream": True},
                          timeout=httpx.Timeout(60, read=600)) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                msg = json.loads(line)
                if msg.get("error"):
                    raise RuntimeError(msg["error"])
                if msg.get("total"):
                    pull["percent"] = round(100 * (msg.get("completed") or 0) / msg["total"])
                pull["step"] = msg.get("status")
        pull["error"] = None
    except Exception as e:
        logging.getLogger("dotationslisten").exception("Modell laden fehlgeschlagen")
        pull["error"] = str(e)[:300]
    finally:
        pull["running"] = False
        w = state.get("worker")
        if w:
            w.status = state["recognizer"].status()


@app.post("/ollama/pull")
def ollama_pull(request: Request):
    if not pull.get("running"):
        pull.clear()
        pull.update(running=True, percent=0, step="startet", error=None)
        threading.Thread(target=_pull_run, daemon=True, name="pull").start()
    return RedirectResponse(request.headers.get("referer") or "/", 303)


@app.get("/health")
def health():
    """Lets a second start of the Mac app find the running one."""
    return {"app": "dotationslisten", "version": C.VERSION, "ollama": C.OLLAMA_SOURCE, "ollama_url": C.OLLAMA_URL}


def _job(job_id: str) -> dict[str, Any]:
    try:
        return J.load(job_id)
    except KeyError:
        raise HTTPException(404, "Vorgang nicht gefunden")


def _mark_stale(job: dict[str, Any]) -> None:
    """Values changed after the Excel export: its sums no longer count for the Verwendungsnachweis."""
    if job.get("export"):
        job["export"]["veraltet"] = True


def _page(job: dict[str, Any], n: int) -> dict[str, Any]:
    for p in job["pages"]:
        if p["n"] == n:
            return p
    raise HTTPException(404, "Seite nicht gefunden")


@app.get("/")
def index(request: Request):
    jobs = J.all_jobs()
    rows = [{
        "id": j["id"], "title": J.title(j), "created": j["created"].replace("T", " ")[:16], "source": j["source"],
        "pages": len(j["pages"]),
        "open": sum(p.get("recog") == J.R_OPEN for p in j["pages"]),
        "reviewed": len(j["reviewed"]), "sheets": sum(1 for p in j["pages"] if p.get("sheet")),
        "export": (j.get("export") or {}).get("file"),
    } for j in jobs]
    return templates.TemplateResponse(request, "index.html", {
        "jobs": rows, "status": _status(), "sheets": F.SHEETS, "default_sheets": DEFAULT_MANUAL_SHEETS,
        "bulk": bulk, "last_import": last_import, "missing": sum(1 for j in jobs if _needs_export(j) and any(p.get("sheet") for p in j["pages"]))})


DEFAULT_MANUAL_SHEETS = ("abrechnung", "teilnehmer", "tagegeld")


@app.post("/neu")
async def new_manual(request: Request):
    """A complete Abrechnung without a scan: the chosen sheets are filled in by hand."""
    form = await request.form()
    chosen = [s.key for s in F.SHEETS if form.get(f"s:{s.key}")]
    if "abrechnung" not in chosen:
        chosen.insert(0, "abrechnung")  # the other sheets take their header from it
    job = J.new_manual_job(chosen)
    J.save(job)
    return RedirectResponse(f"/vorgang/{job['id']}/seite/1", 303)


@app.post("/vorgang/{job_id}/blatt")
async def add_sheet(request: Request, job_id: str):
    """Add a sheet to fill in by hand (also for a scanned Vorgang where a page is missing)."""
    sheet = str((await request.form()).get("sheet") or "")
    if sheet not in F.SHEETS_BY_KEY:
        raise HTTPException(400, "Unbekanntes Blatt")
    added = {}

    def apply(j):
        if sheet in {p.get("sheet") for p in j["pages"]}:
            raise HTTPException(400, "Blatt ist schon vorhanden")
        _mark_stale(j)
        n = max((p["n"] for p in j["pages"]), default=0) + 1
        j["pages"].append(J.manual_page(n, sheet))
        added["n"] = n

    J.update(job_id, apply)
    return RedirectResponse(f"/vorgang/{job_id}/seite/{added['n']}", 303)


@app.post("/upload")
async def upload(request: Request):
    form = await request.form()
    for f in form.getlist("files"):
        if not isinstance(f, FormFile) or not f.filename:
            continue
        name = Path(f.filename).name
        if Path(name).suffix.lower() not in C.SCAN_SUFFIXES:
            continue
        # write under a hidden name first, so the watcher never sees a half-written file
        tmp = C.EINGANG / f".upload-{name}"
        with tmp.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        os.replace(tmp, C.EINGANG / name)
    return RedirectResponse("/", 303)


@app.post("/vorlage")
async def vorlage(file: UploadFile):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".xls", ".xlsx"):
        raise HTTPException(400, "Bitte die Excel-Vorlage (.xls oder .xlsx) hochladen")
    if suffix == ".xls" and not C.soffice_available():
        raise HTTPException(409, "Für eine .xls-Vorlage wird LibreOffice benötigt (kostenlos: libreoffice.org) – "
                                 "oder die Vorlage in Excel als .xlsx speichern und diese hochladen")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"vorlage{suffix}"
        with src.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        try:
            prepare(src)
        except Exception as e:
            raise HTTPException(400, f"Vorlage passt nicht: {e}")
    checks.gliederungen.cache_clear()
    return RedirectResponse("/", 303)


@app.get("/vorgang/{job_id}")
def job_view(job_id: str):
    job = _job(job_id)
    first = next((p["n"] for p in job["pages"] if p.get("sheet")), job["pages"][0]["n"] if job["pages"] else 1)
    return RedirectResponse(f"/vorgang/{job_id}/seite/{first}", 302)


@app.get("/vorgang/{job_id}/seite/{n}")
def page_view(request: Request, job_id: str, n: int):
    job = _job(job_id)
    page = _page(job, n)
    sheet = F.SHEETS_BY_KEY.get(page.get("sheet") or "")
    values = (job["data"].get(sheet.key) if sheet else None) or {}
    hints = checks.check(job["data"])
    tables = []
    if sheet:
        for t in sheet.tables:
            rows = (values.get("tables") or {}).get(t.key) or []
            tables.append({"t": t, "rows": [rows[i] if i < len(rows) else {} for i in range(t.rows)]})
    assigned = {p["sheet"]: p["n"] for p in job["pages"] if p.get("sheet")}
    ctx = {
        "job": job, "page": page, "sheet": sheet, "fields": (values.get("fields") or {}), "tables": tables,
        "hints": hints.get(sheet.key, {}) if sheet else {}, "all_hints": hints, "status": _status(),
        "kind_labels": P.KIND_LABELS, "sheet_choices": SHEET_CHOICES, "assigned": assigned,
        "gliederung": checks.gliederung_name(job["data"]), "title": J.title(job),
        "reviewed": sheet is not None and sheet.key in job["reviewed"],
        "next_n": next((p["n"] for p in job["pages"] if p["n"] > n and p.get("sheet")), None),
        "sheets_by_key": F.SHEETS_BY_KEY, "free_sheets": J.free_sheets(job),
    }
    return templates.TemplateResponse(request, "page.html", ctx)


@app.get("/vorgang/{job_id}/bild/{n}")
def page_image(job_id: str, n: int):
    job = _job(job_id)
    image = _page(job, n).get("image")
    if not image:
        raise HTTPException(404, "Kein Scan – von Hand erfasst")
    return FileResponse(J.job_dir(job_id) / image, media_type="image/png")


def _form_values(sheet: F.Sheet, form) -> dict[str, Any]:
    out: dict[str, Any] = {"fields": {}, "tables": {}}
    for f in sheet.fields + sheet.extras:
        out["fields"][f.key] = str(form.get(f"f:{f.key}", "")).strip()
    for t in sheet.tables:
        rows = []
        for i in range(t.rows):
            rows.append({k: str(form.get(f"t:{t.key}:{i}:{k}", "")).strip() for k, *_ in t.columns})
        while rows and not any(rows[-1].values()):
            rows.pop()
        out["tables"][t.key] = rows
    return out


@app.post("/vorgang/{job_id}/seite/{n}")
async def page_save(request: Request, job_id: str, n: int):
    form = await request.form()
    job = _job(job_id)
    sheet = F.SHEETS_BY_KEY.get(_page(job, n).get("sheet") or "")
    if not sheet:
        raise HTTPException(400, "Seite ist keinem Blatt zugeordnet")
    values = _form_values(sheet, form)

    def apply(j):
        _mark_stale(j)
        j["data"][sheet.key] = values
        if sheet.key not in j["reviewed"]:
            j["reviewed"].append(sheet.key)
        pg = _page(j, n)
        if pg.get("recog") == J.R_OPEN:  # entered by hand: no need to spend minutes on the model
            pg["recog"] = J.R_SKIP

    J.update(job_id, apply)
    if form.get("export"):
        await _export(job_id)
        return RedirectResponse(f"/vorgang/{job_id}/seite/{n}#export", 303)
    target = form.get("next") or n
    return RedirectResponse(f"/vorgang/{job_id}/seite/{target}", 303)


@app.post("/vorgang/{job_id}/seite/{n}/zuordnung")
async def page_assign(request: Request, job_id: str, n: int):
    form = await request.form()
    new = str(form.get("sheet") or "") or None
    if new is not None and new not in F.SHEETS_BY_KEY:
        raise HTTPException(400, "Unbekanntes Blatt")
    rec_enabled = state["recognizer"].enabled

    def apply(j):
        _mark_stale(j)
        for p in j["pages"]:
            if new and p["n"] != n and p.get("sheet") == new:  # a sheet belongs to one page
                p["sheet"], p["recog"] = None, J.R_SKIP
        p = _page(j, n)
        p["sheet"] = new
        p["recog"] = J.R_OPEN if (new and rec_enabled and p.get("image")) else J.R_SKIP
        p["recog_error"] = None

    J.update(job_id, apply)
    return RedirectResponse(f"/vorgang/{job_id}/seite/{n}", 303)


@app.post("/vorgang/{job_id}/seite/{n}/erkennen")
def page_rerun(job_id: str, n: int):
    """Recognise again; the result replaces the values of this sheet (also checked ones)."""

    def apply(j):
        _mark_stale(j)
        p = _page(j, n)
        if p.get("sheet") and p.get("image"):
            p["recog"], p["recog_error"] = J.R_OPEN, None
            if p["sheet"] in j["reviewed"]:
                j["reviewed"].remove(p["sheet"])

    J.update(job_id, apply)
    return RedirectResponse(f"/vorgang/{job_id}/seite/{n}", 303)


@app.post("/vorgang/{job_id}/export")
async def export(request: Request, job_id: str):
    back = (await request.form()).get("back") or "1"
    await _export(job_id)
    return RedirectResponse(f"/vorgang/{job_id}/seite/{int(back)}#export", 303)


async def _export(job_id: str) -> None:
    try:
        await run_in_threadpool(_export_sync, job_id)
    except W.FileLocked as e:
        raise HTTPException(409, str(e))


def _export_sync(job_id: str) -> None:
    if not C.VORLAGE_LEER.exists():
        raise HTTPException(409, "Vorlage fehlt")
    job = _job(job_id)
    name = J.export_name(job)
    data = copy.deepcopy(job["data"])
    if not importer.is_import(job):  # imported: as in the file, an empty Teilnehmeranzahl stays empty
        rules.apply_teilnehmeranzahl(data, only_if_empty=True)
    problems = W.fill(C.VORLAGE_LEER, data, C.AUSGANG / name)
    try:
        summen = VN.abrechnung_summen(C.AUSGANG / name)
    except Exception:
        logging.getLogger("dotationslisten").exception("Summen berechnen fehlgeschlagen: %s", job_id)
        summen = None

    def apply(j):
        old = (j.get("export") or {}).get("file")
        if old and old != name and (C.AUSGANG / old).exists():
            (C.AUSGANG / old).unlink()  # renamed (e.g. Thema corrected): keep one file per Vorgang
        j["export"] = {"file": name, "problems": problems, "at": J._now(), "summen": summen}

    J.update(job_id, apply)


# "Excel erzeugen" for many Vorgänge at once, in the background (a few seconds per Vorgang)
bulk: dict[str, Any] = {"running": False}
_bulk_lock = threading.Lock()


def _needs_export(job: dict[str, Any]) -> bool:
    exp = job.get("export")
    return not exp or bool(exp.get("veraltet")) or not exp.get("summen")


def _bulk_run(ids: list[str]) -> None:
    try:
        for job_id in ids:
            bulk["current"] = job_id
            try:
                _export_sync(job_id)
                bulk["done"] += 1
            except Exception as e:
                logging.getLogger("dotationslisten").exception("Excel erzeugen fehlgeschlagen: %s", job_id)
                detail = e.detail if isinstance(e, HTTPException) else str(e)
                bulk["errors"].append(f"{job_id}: {detail}"[:300])
    finally:
        bulk.update(running=False, current=None, finished=J._now())


last_import: dict[str, Any] = {}


@app.post("/import")
async def import_excel(request: Request):
    """Existing Abrechnungen (filled template, .xlsx/.xls) -> Vorgänge."""
    form = await request.form()
    result: dict[str, Any] = {"ok": [], "duplicate": [], "errors": []}
    for f in form.getlist("files"):
        if not isinstance(f, FormFile) or not f.filename:
            continue
        name = Path(f.filename).name
        if Path(name).suffix.lower() not in importer.SUFFIXES:
            result["errors"].append(f"{name}: keine Excel-Datei")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / ("upload" + Path(name).suffix.lower())
            with src.open("wb") as out:
                shutil.copyfileobj(f.file, out)
            try:
                job_id = await run_in_threadpool(importer.import_file, src, name)
            except Exception as e:
                logging.getLogger("dotationslisten").exception("Import fehlgeschlagen: %s", name)
                result["errors"].append(f"{name}: {e}"[:300])
                continue
        result["duplicate" if job_id is None else "ok"].append(name)
    last_import.clear()
    last_import.update(result, at=J._now())
    return RedirectResponse("/", 303)


@app.post("/excel")
async def export_many(request: Request):
    """mode=fehlende: Vorgänge without an up-to-date Excel; mode=alle: every Vorgang again.
    Vorgänge still waiting for recognition are left out."""
    mode = (await request.form()).get("mode")
    if not C.VORLAGE_LEER.exists():
        raise HTTPException(409, "Vorlage fehlt")
    with _bulk_lock:
        if bulk.get("running"):
            return RedirectResponse("/", 303)
        jobs = [j for j in J.all_jobs() if any(p.get("sheet") for p in j["pages"])]
        waiting = [j for j in jobs if any(p.get("recog") == J.R_OPEN for p in j["pages"])]
        # "alle" keeps the files of imported Vorgänge (still unchanged): they are the originals
        todo = [j["id"] for j in jobs if j not in waiting
                and (_needs_export(j) or (mode == "alle" and not (j.get("export") or {}).get("import")))]
        bulk.clear()
        bulk.update(running=bool(todo), mode=mode, total=len(todo), done=0, errors=[], current=None,
                    waiting=len(waiting), finished=None if todo else J._now())
        if todo:
            threading.Thread(target=_bulk_run, args=(todo,), daemon=True, name="excel").start()
    return RedirectResponse("/", 303)


@app.get("/vorgang/{job_id}/download")
def download(job_id: str):
    job = _job(job_id)
    name = (job.get("export") or {}).get("file")
    if not name or not (C.AUSGANG / name).exists():
        raise HTTPException(404, "Noch nicht exportiert")
    return FileResponse(C.AUSGANG / name, filename=name,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


CHART_PARTS = (("uebungen", "Übungen", "var(--series-1)"), ("ausbildung", "Ausbildung", "var(--series-2)"),
               ("verwaltung", "Verwaltung", "var(--series-3)"))


def _vn_chart(s: dict[str, Any]) -> dict[str, Any] | None:
    """Split of the expenses as one stacked bar (positions in % of the bar width), with markers
    for the Zuwendung and the minimum share of Ausbildung + Übung."""
    values = {k: (s.get(k) if isinstance(s.get(k), (int, float)) else 0) for k, _, _ in CHART_PARTS}
    total = sum(values.values())
    zuwendung = s.get("zuwendung") if isinstance(s.get("zuwendung"), (int, float)) else 0
    mindest = (VN.stand() or {}).get("einstellungen", {}).get("mindestanteil", VN.DEFAULT_MINDESTANTEIL)
    scale = max(total, zuwendung)
    if scale <= 0:
        return None
    parts, x = [], 0.0
    for key, label, color in CHART_PARTS:
        w = 100 * values[key] / scale
        parts.append({"label": label, "color": color, "value": values[key], "x": x, "w": w,
                      "share": values[key] / total if total else 0})
        x += w
    marks = []
    if zuwendung:
        marks.append({"x": 100 * zuwendung / scale, "label": f"Zuwendung {_eur(zuwendung)}"})
        marks.append({"x": 100 * zuwendung * mindest / scale,
                      "label": f"Mindestanteil Ausbildung + Übung: {mindest * 100:g} % = {_eur(zuwendung * mindest)}"})
    for m in marks:  # keep the labels inside the chart
        m["shift"] = "-100%" if m["x"] > 75 else "0" if m["x"] < 25 else "-50%"
    return {"parts": parts, "marks": marks, "total": total}


@app.get("/verwendungsnachweis")
def vn_view(request: Request):
    info = VN.basis_info()
    rows = VN.entries(info["jahr"] if info else None)
    st = VN.stand()
    ctx = {"status": _status(), "info": info, "rows": rows, "stand": st, "final": VN.FINAL,
           "settings": VN.settings(), "chart": _vn_chart(st["summary"]) if st else None,
           "outdated": st is not None and VN.is_outdated(st, info, rows),
           "written": {w["id"]: w["row"] for w in (st or {}).get("written", [])},
           "skipped": set((st or {}).get("skipped", []))}
    return templates.TemplateResponse(request, "verwendungsnachweis.html", ctx)


@app.post("/verwendungsnachweis/basis")
async def vn_basis(file: UploadFile):
    if Path(file.filename or "").suffix.lower() != ".xlsx":
        raise HTTPException(400, "Bitte den Verwendungsnachweis als .xlsx hochladen")
    tmp = C.VN_DIR / ".upload-basis.xlsx"
    with tmp.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    try:
        VN.check_basis(tmp)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(400, f"Datei passt nicht: {e}")
    os.replace(tmp, C.VN_BASIS)
    return RedirectResponse("/verwendungsnachweis", 303)


@app.post("/verwendungsnachweis/berechnen")
def vn_calculate():
    try:
        VN.calculate()
    except FileNotFoundError:
        raise HTTPException(409, "Erst den Verwendungsnachweis hochladen")
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))
    return RedirectResponse("/verwendungsnachweis", 303)


def _number(text: Any) -> float | None:
    t = str(text or "").strip().replace("€", "").replace("%", "").replace(" ", "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        raise HTTPException(400, f"Keine Zahl: {text}")


@app.post("/verwendungsnachweis/einstellungen")
async def vn_settings(request: Request):
    form = await request.form()
    anteil = _number(form.get("mindestanteil"))
    try:
        VN.save_settings(_number(form.get("zuwendung")),
                         VN.DEFAULT_MINDESTANTEIL if anteil is None else anteil / 100)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return RedirectResponse("/verwendungsnachweis", 303)


@app.get("/verwendungsnachweis/download")
def vn_download():
    st = VN.stand()
    if not st or not (C.AUSGANG / st["file"]).exists():
        raise HTTPException(404, "Noch nicht berechnet")
    return FileResponse(C.AUSGANG / st["file"], filename=st["file"],
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
