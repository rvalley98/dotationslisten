# PyInstaller spec for Dotationslisten.app - built by macos/build_app.sh
# ruff: noqa
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

HERE = Path(SPECPATH)
ROOT = HERE.parent
BUILD = HERE / "build"
VERSION = (ROOT / "VERSION").read_text().strip()

a = Analysis(
    [str(ROOT / "desktop" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[(str(BUILD / "tesseract/bin/tesseract"), "tesseract/bin")],
    datas=[
        (str(ROOT / "app/templates"), "app/templates"),
        (str(BUILD / "tesseract/tessdata"), "tesseract/tessdata"),
        (str(BUILD / "menubar.png"), "."),
        (str(BUILD / "menubar@2x.png"), "."),
        (str(ROOT / "VERSION"), "."),
        (str(ROOT / "LICENSE"), "."),
        (str(BUILD / "THIRD_PARTY_LICENSES.txt"), "."),
    ],
    hiddenimports=collect_submodules("app") + collect_submodules("uvicorn"),
    excludes=["pytest", "tkinter", "pystray"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Dotationslisten", console=False,
          target_arch="arm64", codesign_identity=None)
coll = COLLECT(exe, a.binaries, a.datas, name="Dotationslisten")
app = BUNDLE(
    coll,
    name="Dotationslisten.app",
    icon=str(BUILD / "Dotationslisten.icns"),
    bundle_identifier="de.rvalley.dotationslisten",
    version=VERSION,
    info_plist={
        "CFBundleDisplayName": "Dotationslisten",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "13.0",
        "LSUIElement": True,  # menu bar app, the UI is the browser
        "NSHumanReadableCopyright": "Robin Valley",
        "NSAppleEventsUsageDescription": "Zum Auswählen des Datenordners.",
    },
)
