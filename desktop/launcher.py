"""Entry point of the desktop app (Dotationslisten.app on macOS, Dotationslisten.exe on Windows).

- data folder: Dokumente/Dotationslisten (changeable in the menu, e.g. to a NAS share)
- server on 127.0.0.1 only (no login, the data holds IBANs), browser opens automatically
- menu bar (macOS) / tray icon (Windows): open, show data folder, change data folder, support, quit
- a second start just opens the browser for the running instance
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "Dotationslisten"
PORT = int(os.environ.get("DOTATIONSLISTEN_PORT", "8765"))
URL = f"http://127.0.0.1:{PORT}"
COFFEE = "https://buymeacoffee.com/rvalley98"
WINDOWS = sys.platform == "win32"

if WINDOWS:
    SUPPORT = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME
    LOGS = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP_NAME / "Logs"
else:
    SUPPORT = Path.home() / "Library" / "Application Support" / APP_NAME
    LOGS = Path.home() / "Library" / "Logs" / APP_NAME
CONFIG = SUPPORT / "config.json"
log = logging.getLogger("launcher")


def documents() -> Path:
    """The user's Documents folder. Windows: if it is redirected into OneDrive, use the profile
    folder instead - the data (names, IBANs) must not end up in a cloud sync by default."""
    if WINDOWS:
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

            # FOLDERID_Documents {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
            fid = GUID(0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            buf = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(buf)) == 0:
                path = Path(buf.value)
                ctypes.windll.ole32.CoTaskMemFree(buf)
                return Path.home() if "onedrive" in str(path).casefold() else path
        except Exception:
            pass
    return Path.home() / "Documents"


def resources() -> Path:
    """Folder with the bundled tools (PyInstaller) or the build output (development)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent / ("windows" if WINDOWS else "macos") / "build"


def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(cfg: dict) -> None:
    SUPPORT.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=1), "utf-8")


def data_dir() -> Path:
    return Path(load_config().get("data_dir") or documents() / APP_NAME).expanduser()


def setup_environment() -> None:
    """Must run before the app package is imported (config.py reads the environment)."""
    tess = resources() / "tesseract"
    os.environ.setdefault("DATA_DIR", str(data_dir()))
    os.environ.setdefault("TESSERACT", str(tess / "tesseract.exe") if WINDOWS else str(tess / "bin" / "tesseract"))
    os.environ.setdefault("TESSDATA_PREFIX", str(tess / "tessdata"))
    os.environ.setdefault("OLLAMA_URL", "http://127.0.0.1:11434")
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")  # tesseract: one page at a time is enough


def setup_logging() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(LOGS / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def running_instance() -> bool:
    try:
        with urllib.request.urlopen(f"{URL}/health", timeout=1) as r:
            return json.load(r).get("app") == "dotationslisten"
    except Exception:
        return False


def open_browser() -> None:
    if not os.environ.get("DOTATIONSLISTEN_NO_BROWSER"):
        webbrowser.open(URL)


server = None


def start_server() -> None:
    global server
    import uvicorn

    from app.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_config=None, access_log=False)
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True, name="server").start()


def stop_server() -> None:
    if server is not None:
        server.should_exit = True
        for _ in range(50):  # let the worker finish writing
            if not running_instance():
                break
            time.sleep(0.1)


def wait_and_open() -> None:
    for _ in range(150):
        if running_instance():
            open_browser()
            return
        time.sleep(0.2)
    log.error("Server ist nicht gestartet – siehe %s", LOGS / "app.log")


# --- platform helpers ------------------------------------------------------------------------

def open_path(path: Path) -> None:
    if WINDOWS:
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.run(["open", str(path)])


def choose_folder() -> Path | None:
    prompt = "Ordner für die Dotationslisten-Daten wählen (z. B. auf dem NAS):"
    if WINDOWS:
        script = ("Add-Type -AssemblyName System.Windows.Forms;"
                  "$d = New-Object System.Windows.Forms.FolderBrowserDialog;"
                  f"$d.Description = '{prompt}'; $d.ShowNewFolderButton = $true;"
                  "if ($d.ShowDialog() -eq 'OK') { [Console]::OutputEncoding = [Text.Encoding]::UTF8; $d.SelectedPath }")
        r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", script], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)  # type: ignore[attr-defined]
        out = r.stdout.decode("utf-8", "replace").strip()
    else:
        r = subprocess.run(["osascript", "-e", f'POSIX path of (choose folder with prompt "{prompt}")'],
                           capture_output=True, text=True)
        out = r.stdout.strip()
    return Path(out) if r.returncode == 0 and out else None


def alert(text: str) -> None:
    if WINDOWS:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x40)  # MB_ICONINFORMATION
    else:
        text = text.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.run(["osascript", "-e", f'display dialog "{text}" buttons {{"OK"}} default button 1 with title "{APP_NAME}"'],
                       capture_output=True)


def bundle_path() -> str:
    exe = Path(sys.executable).resolve()
    for parent in exe.parents:
        if parent.suffix == ".app":
            return str(parent)
    return str(exe)


def restart() -> None:
    if WINDOWS:
        subprocess.Popen([sys.executable, "--restart"], creationflags=subprocess.DETACHED_PROCESS)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["open", "-n", bundle_path(), "--args", "--restart"])


# --- menu actions (the same on both platforms) ------------------------------------------------

def show_data() -> None:
    open_path(data_dir())


def show_log() -> None:
    if WINDOWS:
        open_path(LOGS / "app.log")
    else:
        subprocess.run(["open", "-a", "Console", str(LOGS / "app.log")])


def change_data(quit_app) -> None:
    old = data_dir()
    folder = choose_folder()
    if not folder or folder == old:
        return
    cfg = load_config()
    cfg["data_dir"] = str(folder)
    save_config(cfg)
    alert(f"Neuer Datenordner: {folder}\n\nBestehende Vorgänge werden nicht verschoben – dafür den Inhalt "
          f"des alten Ordners ({old}) selbst dorthin kopieren. Die App startet jetzt neu.")
    stop_server()
    restart()
    quit_app()


def run_menu_mac() -> None:
    import rumps

    class MenuApp(rumps.App):
        def __init__(self):
            icon = resources() / "menubar.png"
            super().__init__(APP_NAME, icon=str(icon) if icon.exists() else None, template=True,
                             title=None if icon.exists() else "DL", quit_button=None)
            self.menu = ["Öffnen", "Datenordner im Finder zeigen", "Datenordner ändern …", None,
                         "☕ Unterstützen", "Protokoll anzeigen", None, "Beenden"]

        @rumps.clicked("Öffnen")
        def _open(self, _):
            webbrowser.open(URL)

        @rumps.clicked("Datenordner im Finder zeigen")
        def _data(self, _):
            show_data()

        @rumps.clicked("Datenordner ändern …")
        def _change(self, _):
            change_data(rumps.quit_application)

        @rumps.clicked("☕ Unterstützen")
        def _coffee(self, _):
            webbrowser.open(COFFEE)

        @rumps.clicked("Protokoll anzeigen")
        def _log(self, _):
            show_log()

        @rumps.clicked("Beenden")
        def _quit(self, _):
            stop_server()
            rumps.quit_application()

    MenuApp().run()


def run_menu_windows() -> None:
    import pystray
    from PIL import Image

    image = Image.open(resources() / "tray.png")

    def quit_app():
        icon.stop()

    def on_quit(icon_, _item):
        stop_server()
        icon_.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Öffnen", lambda *_: webbrowser.open(URL), default=True),
        pystray.MenuItem("Datenordner im Explorer zeigen", lambda *_: show_data()),
        pystray.MenuItem("Datenordner ändern …", lambda *_: change_data(quit_app)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("☕ Unterstützen", lambda *_: webbrowser.open(COFFEE)),
        pystray.MenuItem("Protokoll anzeigen", lambda *_: show_log()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Beenden", on_quit),
    )
    icon = pystray.Icon(APP_NAME, image, f"{APP_NAME} – {URL}", menu)
    icon.run()


def main() -> None:
    if "--restart" in sys.argv:  # wait until the previous instance has released the port
        for _ in range(100):
            if not running_instance():
                break
            time.sleep(0.2)
    if running_instance():  # already running: just bring it up
        open_browser()
        return
    setup_environment()
    setup_logging()
    Path(os.environ["DATA_DIR"]).mkdir(parents=True, exist_ok=True)
    start_server()
    threading.Thread(target=wait_and_open, daemon=True).start()
    try:
        run_menu_windows() if WINDOWS else run_menu_mac()
    except Exception:
        # no menu bar / tray (e.g. a build server without a desktop): keep serving
        log.exception("Menü konnte nicht angezeigt werden – die App läuft weiter unter %s", URL)
        while server is not None and not server.should_exit:
            time.sleep(1)
    os._exit(0)


if __name__ == "__main__":
    main()
