# PyInstaller spec for Dotationslisten.exe (Windows) - built by windows/build_windows.ps1
# ruff: noqa
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

HERE = Path(SPECPATH)
ROOT = HERE.parent
BUILD = HERE / "build"

a = Analysis(
    [str(ROOT / "desktop" / "launcher.py")],
    pathex=[str(ROOT)],
    datas=[
        (str(ROOT / "app/templates"), "app/templates"),
        (str(BUILD / "tesseract"), "tesseract"),  # tesseract.exe + DLLs + tessdata
        (str(BUILD / "tray.png"), "."),
        (str(ROOT / "VERSION"), "."),
        (str(ROOT / "LICENSE"), "."),
        (str(BUILD / "THIRD_PARTY_LICENSES.txt"), "."),
    ],
    hiddenimports=collect_submodules("app") + collect_submodules("uvicorn") + collect_submodules("pystray"),
    excludes=["pytest", "tkinter", "rumps"],
    # LGPL: pystray stays as plain, replaceable .py files next to the exe
    module_collection_mode={"pystray": "py"},
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Dotationslisten", console=False,
          icon=str(BUILD / "Dotationslisten.ico"), version=str(BUILD / "version_info.txt"))
coll = COLLECT(exe, a.binaries, a.datas, name="Dotationslisten")
