"""Entry point of the desktop app (Dotationslisten.app on macOS, Dotationslisten.exe on Windows).

- data folder: Dokumente/Dotationslisten (changeable in the menu, e.g. to a NAS share)
- server on 127.0.0.1 only (no login, the data holds IBANs), browser opens automatically
- menu bar (macOS) / tray icon (Windows): open, show data folder, change data folder, support, quit
- a second start just opens the browser for the running instance
- handwriting: an Ollama the user installed (port 11434) is used if it runs, otherwise the
  bundled one is started on its own port (11435) and stopped again on quit
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import platform
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
BUGS = "https://github.com/rvalley98/dotationslisten/issues/new"
WINDOWS = sys.platform == "win32"

if WINDOWS:
    SUPPORT = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME
    LOGS = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP_NAME / "Logs"
else:
    SUPPORT = Path.home() / "Library" / "Application Support" / APP_NAME
    LOGS = Path.home() / "Library" / "Logs" / APP_NAME
CONFIG = SUPPORT / "config.json"
OLLAMA_EXTERNAL = "http://127.0.0.1:11434"  # Ollama installed by the user
OLLAMA_PORT = int(os.environ.get("DOTATIONSLISTEN_OLLAMA_PORT", "11435"))  # the bundled one
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
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")  # tesseract: one page at a time is enough
    choose_ollama()


# --- Ollama (handwriting recognition) -------------------------------------------------------

ollama_proc: subprocess.Popen | None = None
_ollama_job = None  # Windows job object: the server and its runners end with the app


def ollama_dir() -> Path:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        return exe.parent / "ollama" if WINDOWS else exe.parent.parent / "Resources" / "ollama"
    return resources().parent / "build" / "ollama"


def ollama_up(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/version", timeout=1) as r:
            return "version" in json.load(r)
    except Exception:
        return False


def bundled_ollama_supported() -> bool:
    if WINDOWS:
        return True
    try:  # the Ollama binaries need macOS 14
        return int(platform.mac_ver()[0].split(".")[0]) >= 14
    except ValueError:
        return True


def choose_ollama() -> None:
    """Sets OLLAMA_URL (read by app.config) and DOTATIONSLISTEN_OLLAMA (shown in the app):
    "extern" (the user's own Ollama), "mitgeliefert" or "fehlt". DOTATIONSLISTEN_OLLAMA=
    mitgeliefert forces the bundled one, an explicit OLLAMA_URL is left alone."""
    if os.environ.get("OLLAMA_URL"):
        os.environ.setdefault("DOTATIONSLISTEN_OLLAMA", "extern")
        return
    forced = os.environ.get("DOTATIONSLISTEN_OLLAMA") == "mitgeliefert"
    if not forced and ollama_up(OLLAMA_EXTERNAL):
        os.environ.update(OLLAMA_URL=OLLAMA_EXTERNAL, DOTATIONSLISTEN_OLLAMA="extern")
        return
    exe = ollama_dir() / ("ollama.exe" if WINDOWS else "ollama")
    if exe.exists() and bundled_ollama_supported():
        os.environ.update(OLLAMA_URL=f"http://127.0.0.1:{OLLAMA_PORT}", DOTATIONSLISTEN_OLLAMA="mitgeliefert")
    else:
        os.environ.update(OLLAMA_URL=OLLAMA_EXTERNAL, DOTATIONSLISTEN_OLLAMA="fehlt")


def _windows_job(proc: subprocess.Popen) -> None:
    """Puts the process into a job object that is killed when the app ends - also when the
    app is killed (uninstaller, task manager), so no ollama.exe is left holding files."""
    global _ollama_job
    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class BASIC(ctypes.Structure):
        _fields_ = [("a", ctypes.c_longlong), ("b", ctypes.c_longlong), ("LimitFlags", wintypes.DWORD),
                    ("c", ctypes.c_size_t), ("d", ctypes.c_size_t), ("e", wintypes.DWORD),
                    ("f", ctypes.c_size_t), ("g", wintypes.DWORD), ("h", wintypes.DWORD)]

    class EXTENDED(ctypes.Structure):
        _fields_ = [("Basic", BASIC), ("Io", IO_COUNTERS), ("p", ctypes.c_size_t), ("j", ctypes.c_size_t),
                    ("pu", ctypes.c_size_t), ("ju", ctypes.c_size_t)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    job = k32.CreateJobObjectW(None, None)
    info = EXTENDED()
    info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    k32.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info))
    if not k32.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(int(proc._handle))):  # type: ignore[attr-defined]
        log.warning("Ollama: Job-Objekt nicht zugewiesen (%s)", ctypes.get_last_error())
    _ollama_job = job  # keep the handle open for the lifetime of the app


def start_ollama() -> None:
    global ollama_proc
    if os.environ.get("DOTATIONSLISTEN_OLLAMA") != "mitgeliefert":
        return
    url = os.environ["OLLAMA_URL"]
    if ollama_up(url):  # left over from a crashed start: use it
        log.info("Ollama läuft schon unter %s", url)
        return
    exe = ollama_dir() / ("ollama.exe" if WINDOWS else "ollama")
    env = dict(os.environ, OLLAMA_HOST=f"127.0.0.1:{OLLAMA_PORT}", OLLAMA_NO_CLOUD="1",
               OLLAMA_NUM_PARALLEL="1")  # models stay in the default place (~/.ollama), shared with an own install
    out = open(LOGS / "ollama.log", "ab")
    if WINDOWS:
        args, flags = [str(exe), "serve"], subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    else:
        # macOS has no "end with the parent": a small shell watches the app and stops Ollama when
        # the app is gone (also after a crash, kill or logout)
        watch = ('trap \'kill $c 2>/dev/null; wait $c; exit 0\' TERM INT; "$0" serve & c=$!; '
                 f'while kill -0 {os.getpid()} 2>/dev/null && kill -0 $c 2>/dev/null; do sleep 2; done; '
                 'kill $c 2>/dev/null; wait $c')
        args, flags = ["/bin/sh", "-c", watch, str(exe)], 0
    try:
        ollama_proc = subprocess.Popen(args, cwd=exe.parent, env=env, stdin=subprocess.DEVNULL,
                                       stdout=out, stderr=subprocess.STDOUT, creationflags=flags)
    except OSError:
        log.exception("Ollama konnte nicht gestartet werden")
        return
    if WINDOWS:
        try:
            _windows_job(ollama_proc)
        except Exception:
            log.exception("Ollama: Job-Objekt")
    log.info("Ollama gestartet: %s (pid %s)", url, ollama_proc.pid)


def stop_ollama() -> None:
    global ollama_proc
    if ollama_proc is None:
        return
    if _ollama_job is not None:  # Windows: the server and the model runners it started
        import ctypes
        ctypes.windll.kernel32.TerminateJobObject(ctypes.c_void_p(_ollama_job), 0)
    ollama_proc.terminate()
    try:
        ollama_proc.wait(8)
    except subprocess.TimeoutExpired:
        ollama_proc.kill()
    ollama_proc = None


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
    stop_ollama()
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
                         "🐞 Fehler melden", "☕ Unterstützen", "Protokoll anzeigen", None, "Beenden"]

        @rumps.clicked("Öffnen")
        def _open(self, _):
            webbrowser.open(URL)

        @rumps.clicked("Datenordner im Finder zeigen")
        def _data(self, _):
            show_data()

        @rumps.clicked("Datenordner ändern …")
        def _change(self, _):
            change_data(rumps.quit_application)

        @rumps.clicked("🐞 Fehler melden")
        def _bugs(self, _):
            webbrowser.open(BUGS)

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
        pystray.MenuItem("🐞 Fehler melden", lambda *_: webbrowser.open(BUGS)),
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
    start_ollama()
    start_server()
    threading.Thread(target=wait_and_open, daemon=True).start()
    try:
        run_menu_windows() if WINDOWS else run_menu_mac()
    except Exception:
        # no menu bar / tray (e.g. a build server without a desktop): keep serving
        log.exception("Menü konnte nicht angezeigt werden – die App läuft weiter unter %s", URL)
        while server is not None and not server.should_exit:
            time.sleep(1)
    stop_ollama()
    os._exit(0)


if __name__ == "__main__":
    main()
