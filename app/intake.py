"""Watch the scanner folder (polling: files arrive via SMB on a bind mount, inotify is unreliable).

A file is taken once its size has been stable for one poll interval. Its hash makes intake
idempotent; the original is moved to data/archiv afterwards.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import shutil
from pathlib import Path

from . import config as C
from . import jobs as J
from . import pages as P

log = logging.getLogger("dotationslisten.intake")

_seen: dict[Path, tuple[int, float]] = {}
INDEX = "index.json"  # hash -> archived file


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _index() -> dict[str, str]:
    p = C.ARCHIV / INDEX
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def _archive(path: Path, sub: str) -> Path:
    target_dir = C.ARCHIV / sub
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / path.name
    n = 1
    while target.exists():
        target = target_dir / f"{path.stem} ({n}){path.suffix}"
        n += 1
    shutil.move(str(path), target)
    return target


def ready_files() -> list[Path]:
    """Files whose size did not change since the previous call."""
    ready = []
    current = {}
    for p in sorted(C.EINGANG.iterdir()):
        if not p.is_file() or p.name.startswith((".", "~")) or p.suffix.lower() not in C.SCAN_SUFFIXES:
            continue
        st = p.stat()
        current[p] = (st.st_size, st.st_mtime)
        if st.st_size > 0 and _seen.get(p) == current[p]:
            ready.append(p)
    _seen.clear()
    _seen.update(current)
    return ready


def ingest(path: Path, recognize: bool) -> list[str]:
    """Scan file -> one or more Vorgänge. Returns the new job ids."""
    digest = _hash(path)
    index = _index()
    if digest in index:
        log.info("%s wurde schon eingelesen (%s) – nach archiv/duplikate", path.name, index[digest])
        _archive(path, "duplikate")
        return []

    analysed = [P.analyse(im) for im in P.load_pages(path)]
    kinds = [a.kind for a in analysed]
    groups = J.split_vorgaenge(kinds)
    ids = []
    for gi, group in enumerate(groups):
        pages = [{"n": k + 1, "kind": analysed[i].kind, "rotation": analysed[i].rotation,
                  "source_page": i + 1} for k, i in enumerate(group)]
        job = J.new_job(path.name, digest, gi, pages, recognize)
        d = J.job_dir(job["id"]) / "pages"
        d.mkdir(parents=True, exist_ok=True)
        for p, i in zip(pages, group):
            p["image"] = f"pages/{p['n']:03d}.png"
            analysed[i].image.save(J.job_dir(job["id"]) / p["image"], optimize=True)
        J.save(job)
        ids.append(job["id"])
        log.info("Vorgang %s: %s", job["id"], ", ".join(f"{p['kind']}→{p['sheet']}" for p in pages))

    archived = _archive(path, dt.date.today().strftime("%Y-%m"))
    index[digest] = str(archived.relative_to(C.ARCHIV))
    (C.ARCHIV / INDEX).write_text(json.dumps(index, indent=1), "utf-8")
    return ids


def poll(recognize: bool) -> list[str]:
    ids = []
    for path in ready_files():
        try:
            ids += ingest(path, recognize)
        except Exception:  # keep the watcher alive; the file moves aside so it is not retried forever
            log.exception("Einlesen fehlgeschlagen: %s", path.name)
            _archive(path, "fehler")
    return ids
