"""Handwriting recognition behind one interface.

- NoneRecognizer: manual entry only (also the fallback when the model reads badly)
- OllamaRecognizer: local vision model, whole page -> JSON matching the field map.
  Unreachable server (e.g. the Mac is switched off) raises Unavailable: pages stay queued.
"""

from __future__ import annotations

import base64
import io
import json
from typing import Any, Protocol

import httpx
from PIL import Image

from . import config as C
from . import fields as F


class Unavailable(Exception):
    pass


class Recognizer(Protocol):
    enabled: bool

    def status(self) -> tuple[bool, str]: ...

    def recognize(self, image: Image.Image, sheet: F.Sheet) -> dict[str, Any]: ...


class NoneRecognizer:
    enabled = False

    def state(self) -> str:
        return "aus"

    def status(self) -> tuple[bool, str]:
        return False, "Erkennung aus – Werte werden von Hand eingetragen"

    def recognize(self, image, sheet):
        raise Unavailable("Erkennung aus")


TYPE_HINTS = {
    F.DATE: "Datum TT.MM.JJJJ",
    F.TIME: "Uhrzeit HH:MM",
    F.INT: "ganze Zahl",
    F.MONEY: "Betrag in Euro, z. B. 12,50",
    F.PERCENT: "Prozent, nur die Zahl",
    F.JA_NEIN_UPPER: "JA oder NEIN",
    F.JA_NEIN_LOWER: "ja oder nein",
    F.IBAN: "IBAN, Buchstaben und Ziffern genau wie geschrieben",
}


def _hint(label: str, typ: str, options: tuple[str, ...] = ()) -> str:
    hint = " / ".join(options) if options else TYPE_HINTS.get(typ)
    return f"{label} ({hint})" if hint else label


def schema(sheet: F.Sheet) -> dict[str, Any]:
    props: dict[str, Any] = {}
    if sheet.fields:
        props["fields"] = {
            "type": "object",
            "properties": {f.key: {"type": "string", "description": _hint(f.label, f.type, f.options)} for f in sheet.fields},
            "required": [f.key for f in sheet.fields],
        }
    if sheet.tables:
        props["tables"] = {
            "type": "object",
            "properties": {
                t.key: {
                    "type": "array",
                    "maxItems": t.rows,
                    "items": {
                        "type": "object",
                        "properties": {k: {"type": "string", "description": _hint(lbl, typ)} for k, lbl, _c, typ in t.columns},
                        "required": [k for k, *_ in t.columns],
                    },
                }
                for t in sheet.tables
            },
            "required": [t.key for t in sheet.tables],
        }
    return {"type": "object", "properties": props, "required": list(props)}


def prompt(sheet: F.Sheet) -> str:
    lines = [
        f"Das Bild ist ein Scan des Formulars „{sheet.title}“ ({sheet.name}). Gedruckte Beschriftungen,",
        "handschriftlich ausgefüllte Werte. Lies NUR die handschriftlichen Einträge aus.",
        "Regeln:",
        "- Schreibe jeden Wert genau so ab, wie er dasteht. Nichts ergänzen, nichts raten, nichts berechnen.",
        "- Leeres oder unleserliches Feld: leerer String \"\".",
        "- Ankreuzfelder: angekreuzte Option als Text.",
        "- Tabellen: eine Zeile pro ausgefüllter Formularzeile, von oben nach unten; leere Zeilen weglassen.",
        "",
    ]
    if sheet.fields:
        lines.append("Felder:")
        lines += [f"- {f.key}: {_hint(f.label, f.type, f.options)}" for f in sheet.fields]
    for t in sheet.tables:
        cols = ", ".join(f"{k} = {_hint(lbl, typ)}" for k, lbl, _c, typ in t.columns)
        lines.append(f"Tabelle {t.key} „{t.label}“ (max. {t.rows} Zeilen): {cols}")
    lines.append("\nAntworte nur mit JSON nach dem vorgegebenen Schema.")
    return "\n".join(lines)


def _image_b64(image: Image.Image, max_side: int = 1600) -> str:
    im = image.convert("L")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


def clean(sheet: F.Sheet, raw: dict[str, Any]) -> dict[str, Any]:
    """Keep only known keys, all values as stripped strings, tables cut to the template size."""
    out: dict[str, Any] = {"fields": {}, "tables": {}}
    fields_in = raw.get("fields") or {}
    for f in sheet.fields:
        v = fields_in.get(f.key)
        out["fields"][f.key] = "" if v is None else str(v).strip()
    tables_in = raw.get("tables") or {}
    for t in sheet.tables:
        rows = []
        for row in tables_in.get(t.key) or []:
            if not isinstance(row, dict):
                continue
            r = {k: ("" if row.get(k) is None else str(row.get(k)).strip()) for k, *_ in t.columns}
            if any(r.values()):
                rows.append(r)
        out["tables"][t.key] = rows[: t.rows]
    return out


class OllamaRecognizer:
    enabled = True

    def __init__(self, url: str = C.OLLAMA_URL, model: str = C.OLLAMA_MODEL, timeout: float = C.OLLAMA_TIMEOUT):
        self.url, self.model, self.timeout = url, model, timeout

    def state(self) -> str:
        """"ok", "offline" (Ollama not running/installed) or "modell" (model not downloaded)."""
        try:
            r = httpx.get(f"{self.url}/api/tags", timeout=5)
            r.raise_for_status()
        except httpx.HTTPError:
            return "offline"
        names = {m.get("name") for m in r.json().get("models", [])}
        return "ok" if self.model in names or f"{self.model}:latest" in names else "modell"

    def status(self) -> tuple[bool, str]:
        st = self.state()
        if st == "offline":
            return False, f"Ollama unter {self.url} nicht erreichbar – Seiten warten"
        if st == "modell":
            return False, f"Modell {self.model} fehlt auf {self.url} (ollama pull {self.model})"
        return True, f"{self.model} auf {self.url}"

    def recognize(self, image: Image.Image, sheet: F.Sheet) -> dict[str, Any]:
        ok, msg = self.status()
        if not ok:
            raise Unavailable(msg)
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt(sheet), "images": [_image_b64(image)]}],
            "format": schema(sheet),
            "stream": False,
            "options": {"temperature": 0},
        }
        try:
            r = httpx.post(f"{self.url}/api/chat", json=body, timeout=httpx.Timeout(self.timeout, connect=10))
            r.raise_for_status()
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            raise Unavailable(str(e)) from e
        content = r.json()["message"]["content"]
        return clean(sheet, json.loads(content))


def from_config() -> Recognizer:
    return OllamaRecognizer() if C.RECOGNIZER == "ollama" else NoneRecognizer()
