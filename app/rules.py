"""Values the app derives itself instead of reading them from the paper.

Teilnehmeranzahl on the Tagegeld sheet: the number of signatures on the Tagegeld page (every
recipient signs), or - if none were counted - the number of names on the Teilnehmerliste.
It goes into the Tagegeld row (außerhalb der Gemeinde = JA) or the Aufwandsvergütung row
(NEIN); the other one is emptied.
"""

from __future__ import annotations

from typing import Any


def _int(raw: Any) -> int:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return 0


def teilnehmeranzahl(data: dict[str, Any]) -> int | None:
    signed = _int(((data.get("tagegeld") or {}).get("fields") or {}).get("unterschriften"))
    if signed > 0:
        return signed
    rows = ((data.get("teilnehmer") or {}).get("tables") or {}).get("teilnehmer") or []
    names = sum(1 for r in rows if isinstance(r, dict) and ((r.get("name") or "").strip() or (r.get("vorname") or "").strip()))
    return names or None


def apply_teilnehmeranzahl(data: dict[str, Any], only_if_empty: bool = False) -> None:
    fields = (data.get("tagegeld") or {}).get("fields")
    if fields is None:
        return
    if only_if_empty and ((fields.get("teilnehmer_tagegeld") or "").strip() or (fields.get("teilnehmer_aufwand") or "").strip()):
        return
    n = teilnehmeranzahl(data)
    if n is None:
        return
    target = {"JA": "teilnehmer_tagegeld", "NEIN": "teilnehmer_aufwand"}.get((fields.get("ausserhalb_gemeinde") or "").strip().upper())
    if target is None:
        return
    for key in ("teilnehmer_tagegeld", "teilnehmer_aufwand"):
        fields[key] = str(n) if key == target else ""
