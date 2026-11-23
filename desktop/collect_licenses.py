"""Collects the license texts of everything the desktop app ships (Python packages, Python
itself, Tesseract, ...) into one file that is bundled with the app.

    python desktop/collect_licenses.py <out file> <extra license files: "Name=path" ...>
"""

from __future__ import annotations

import importlib.metadata as md
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ["rumps"] if sys.platform == "darwin" else ["pystray"] if sys.platform == "win32" else []
SKIP = {"pytest", "pluggy", "iniconfig", "pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "macholib",
        "setuptools", "packaging", "pefile", "pywin32-ctypes"}


def _name(req: str) -> str:
    return re.split(r"[\s\[<>=!~;(]", req, maxsplit=1)[0].lower().replace("_", "-")


def _extras(req: str) -> set[str]:
    m = re.search(r"\[([^\]]+)\]", req.split(";")[0])
    return {e.strip() for e in m[1].split(",")} if m else set()


def shipped() -> list[md.Distribution]:
    from packaging.requirements import Requirement

    lines = [r for r in (ROOT / "requirements.txt").read_text().splitlines() if r.strip() and not r.startswith("#")]
    todo = [(_name(r), _extras(r)) for r in lines] + [(e, set()) for e in ENTRY]
    seen: dict[str, md.Distribution] = {}
    while todo:
        name, extras = todo.pop()
        if name in SKIP:
            continue
        try:
            dist = seen.get(name) or md.distribution(name)
        except md.PackageNotFoundError:
            continue
        first = name not in seen
        seen[name] = dist
        for raw in dist.requires or []:
            req = Requirement(raw)
            if req.marker is not None:
                envs = [{"extra": e} for e in extras] + [{"extra": ""}]
                if not any(req.marker.evaluate(env) for env in envs):
                    continue
                if not first and not any(req.marker.evaluate({"extra": e}) for e in extras):
                    continue
            elif not first:
                continue
            todo.append((_name(req.name), set(req.extras)))
    return sorted(seen.values(), key=lambda d: d.metadata["Name"].lower())


def license_texts(dist: md.Distribution) -> list[str]:
    out = []
    for f in dist.files or []:
        if re.search(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", f.name, re.I) and not f.name.endswith((".py", ".pyc")):
            try:
                out.append(f"--- {f}\n{Path(f.locate()).read_text(encoding='utf-8', errors='replace').strip()}")
            except OSError:
                pass
    return out


def main(out: Path, extras: list[str]) -> None:
    parts = ["Dotationslisten enthält die folgenden Komponenten Dritter. Sie stehen unter ihren eigenen",
             "Lizenzen (Texte unten); die Lizenz von Dotationslisten selbst steht in LICENSE.", ""]
    parts.append(f"=== Python {sys.version.split()[0]} (PSF License)\n"
                 + Path(sys.base_prefix, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "LICENSE.txt")
                 .read_text(encoding="utf-8", errors="replace") if sys.platform != "win32"
                 else f"=== Python {sys.version.split()[0]} (PSF License)\n"
                 + Path(sys.base_prefix, "LICENSE.txt").read_text(encoding="utf-8", errors="replace"))
    for dist in shipped():
        m = dist.metadata
        lic = m.get("License-Expression") or (m.get("License") if len(m.get("License") or "") < 80 else "") or \
            ", ".join(c.split("::")[-1].strip() for c in m.get_all("Classifier") or [] if c.startswith("License"))
        parts.append(f"\n=== {m['Name']} {dist.version} ({lic or 'siehe Text'})\n{m.get('Home-page') or ''}")
        parts += license_texts(dist) or ["(kein Lizenztext im Paket enthalten)"]
    for extra in extras:
        name, _, path = extra.partition("=")
        parts.append(f"\n=== {name}\n{Path(path).read_text(encoding='utf-8', errors='replace').strip()}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"{out}: {len(shipped())} Pakete")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2:])
