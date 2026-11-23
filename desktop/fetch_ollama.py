"""Download the pinned Ollama release and prepare it for bundling.

    python desktop/fetch_ollama.py mac|windows <build dir>

Result: <build dir>/ollama (the server) and <build dir>/ollama-licenses/ (its licenses).
The download is cached in <build dir>/ollama-src and checked against the pinned SHA-256.

- mac: arm64 only (the app is Apple Silicon only) - x86 libraries dropped, universal binaries
  thinned; the MLX engine and the quantizer are not needed for the vision model (llama.cpp on
  Metal), which keeps it at ~56 MB instead of ~580 MB.
- windows: CPU, Vulkan and Nvidia CUDA 12. CUDA 13 is left out: it needs newer drivers and
  GPUs, CUDA 12 covers both, and it would add another 900 MB.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

VERSION = "0.40.17"
ASSETS = {
    "mac": ("ollama-darwin.tgz", "4b9db20d077c5a1e52fb4a6f2e6791f76ae945fd07c9b1a5647c82e927826653"),
    "windows": ("ollama-windows-amd64.zip", "3dd80f6e3a9699f2eadf4ac418f00529cee594df9557541806eda1f1f3f5588a"),
}
BASE = f"https://github.com/ollama/ollama/releases/download/v{VERSION}/"
LICENSE_URL = f"https://raw.githubusercontent.com/ollama/ollama/v{VERSION}/LICENSE"


def download(url: str, dst: Path) -> None:
    tmp = dst.with_suffix(dst.suffix + ".part")
    for attempt in range(1, 6):  # GitHub answers 503 now and then
        try:
            with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            tmp.replace(dst)
            return
        except OSError as e:
            if attempt == 5:
                raise
            print(f"Download fehlgeschlagen ({attempt}/5): {e} - neuer Versuch")
            time.sleep(10 * attempt)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def archs(path: Path) -> set[str]:
    r = subprocess.run(["lipo", "-archs", str(path)], capture_output=True, text=True)
    return set(r.stdout.split()) if r.returncode == 0 else set()


def prepare_mac(archive: Path, out: Path, licenses: Path) -> None:
    raw = out.with_name("ollama-raw")
    shutil.rmtree(raw, ignore_errors=True)
    raw.mkdir()
    with tarfile.open(archive) as t:
        t.extractall(raw, filter="data")
    for name in ("ollama", "llama-server"):
        src = raw / name
        if archs(src) == {"arm64"}:
            shutil.copy2(src, out / name)
        else:
            subprocess.run(["lipo", "-thin", "arm64", str(src), "-o", str(out / name)], check=True)
    for f in raw.glob("*LICENSE*"):
        shutil.copy2(f, licenses / f.name)
    for f in raw.glob("*NOTICE*"):
        shutil.copy2(f, licenses / f.name)
    shutil.rmtree(raw)


def prepare_windows(archive: Path, out: Path, licenses: Path) -> None:
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            name = info.filename
            if name.startswith("lib/ollama/cuda_v13/") or name.startswith("lib/ollama/mlx"):
                continue
            z.extract(info, out)
    for f in out.rglob("*LICENSE*"):
        shutil.copy2(f, licenses / f.name)
    (licenses / "NVIDIA_CUDA_NOTICE").write_text(
        "lib/ollama/cuda_v12 enthält Laufzeitbibliotheken des NVIDIA CUDA Toolkit (cudart, cuBLAS, cuBLASLt),\n"
        "wie sie Ollama ausliefert. Sie sind Eigentum der NVIDIA Corporation und werden nach den\n"
        "Weitergabebedingungen des NVIDIA CUDA Toolkit End User License Agreement verteilt:\n"
        "https://docs.nvidia.com/cuda/eula/index.html\n\n"
        "Die mitgelieferten Microsoft Visual C++-Laufzeitbibliotheken (msvcp140*, vcruntime140*, concrt140,\n"
        "vccorlib140) sind Eigentum der Microsoft Corporation und werden als weitergabefähige Dateien des\n"
        "Visual Studio verteilt.\n", encoding="utf-8")


def main() -> None:
    platform, build = sys.argv[1], Path(sys.argv[2]).resolve()
    name, digest = ASSETS[platform]
    src = build / "ollama-src"
    src.mkdir(parents=True, exist_ok=True)
    archive = src / f"{VERSION}-{name}"
    if not archive.exists() or sha256(archive) != digest:
        print(f"Lade Ollama {VERSION} ({name}) ...")
        download(BASE + name, archive)
    if sha256(archive) != digest:
        archive.unlink()
        sys.exit(f"Prüfsumme von {name} stimmt nicht")
    lic_src = src / f"ollama-{VERSION}-LICENSE"
    if not lic_src.exists():
        download(LICENSE_URL, lic_src)

    out, licenses = build / "ollama", build / "ollama-licenses"
    stamp = out / ".version"
    if stamp.exists() and stamp.read_text() == f"{VERSION} {digest}":
        print(f"Ollama {VERSION} ist schon vorbereitet")
        return
    for d in (out, licenses):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    (prepare_mac if platform == "mac" else prepare_windows)(archive, out, licenses)
    shutil.copy2(lic_src, licenses / "OLLAMA_LICENSE")
    stamp.write_text(f"{VERSION} {digest}")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"Ollama {VERSION} vorbereitet: {out} ({size / 1048576:.0f} MB)")


if __name__ == "__main__":
    main()
