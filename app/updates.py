"""Notice about a newer release: asks GitHub's releases API once a day (in the background, no
data of the user is sent - only the request itself). UPDATE_CHECK=0 switches it off."""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

import httpx

from . import config as C

log = logging.getLogger("dotationslisten.updates")
INTERVAL = 24 * 3600
state: dict[str, Any] = {"latest": None, "url": None, "checked": None}


def parse(version: str) -> tuple[int, ...] | None:
    m = re.fullmatch(r"v?(\d+(?:\.\d+)*)", (version or "").strip())
    return tuple(int(x) for x in m[1].split(".")) if m else None


def is_newer(latest: str | None, current: str = C.VERSION) -> bool:
    a, b = parse(latest or ""), parse(current)
    if a is None or b is None:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def check() -> None:
    try:
        r = httpx.get(C.UPDATE_URL, timeout=10, follow_redirects=True,
                      headers={"Accept": "application/vnd.github+json", "User-Agent": f"Dotationslisten/{C.VERSION}"})
        if r.status_code == 404:  # no release yet (or not reachable without login)
            state.update(latest=None, url=None)
        else:
            r.raise_for_status()
            rel = r.json()
            if not rel.get("draft") and not rel.get("prerelease"):
                state.update(latest=str(rel.get("tag_name", "")).lstrip("v"), url=rel.get("html_url"))
        state["checked"] = time.time()
    except Exception as e:  # offline, rate limit ... - try again next time, never bother the user
        log.info("Update-Prüfung nicht möglich: %s", e)


def info() -> dict[str, Any] | None:
    """{'version', 'url'} if a newer release exists, else None."""
    if is_newer(state["latest"]):
        return {"version": state["latest"], "url": state["url"] or C.UPDATE_PAGE}
    return None


def _loop() -> None:
    time.sleep(5)
    while True:
        check()
        time.sleep(INTERVAL)


def start() -> None:
    if C.UPDATE_CHECK:
        threading.Thread(target=_loop, daemon=True, name="updates").start()
