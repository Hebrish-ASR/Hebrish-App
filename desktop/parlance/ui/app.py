"""Controller: ties hotkey, mic, model and paste together; owns the tray and window.

Threads: the hotkey source and all slow work (model load, decode, HF check, download)
run off the Qt thread. They talk back only through the Signals object, whose
cross-thread emits Qt queues onto the GUI thread.
"""

import argparse
import getpass
import logging
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import audio, model_store
from ..config import APP_NAME, HISTORY_PATH, STATE_PATH, Config, load_json, migrate_legacy, save_json
from ..engine import Engine
from ..hotkey import make_listener
from ..inserter import make_inserter
from . import about

log = logging.getLogger("parlance")
ICONS = Path(__file__).resolve().parent.parent / "data" / "icons"
HISTORY_MAX = 50


def icon(name: str) -> QIcon:
    return QIcon(str(ICONS / f"{name}.svg"))


class Signals(QObject):
    start = Signal()
    stop = Signal()
    cancel = Signal()
    captured = Signal(str)
    transcribed = Signal(str, object)
    loaded = Signal(object)
    checked = Signal(object, object, bool)
    progress = Signal(float, str)
    downloaded = Signal(object, object)


class Controller(QObject):
    def __init__(self, hidden: bool):
        super().__init__()
        from .window import MainWindow
        self.cfg = Config()
        self.engine = Engine()
        self.recorder = audio.Recorder()                       # hotkey takes
        self.long_recorder = audio.Recorder(audio.LONGFORM_MAX_S)  # Transcribe tab
        self.state = "idle"             # idle | recording | busy
        self.latest: model_store.Manifest | None = None
        self.downloading: threading.Event | None = None
        self.reload_pending = False
        self.history: list[dict] = (load_json(HISTORY_PATH, []) if self.cfg["keep_history"] else [])

        self.sig = Signals()
        self.sig.start.connect(self.start)
        self.sig.stop.connect(self.stop)
        self.sig.cancel.connect(self.cancel)
        self.sig.transcribed.connect(self._done)
        self.sig.loaded.connect(self._loaded)
        self.sig.checked.connect(self._checked)
        self.sig.downloaded.connect(self._downloaded)

        self.inserter = make_inserter()
        self.hotkeys = make_listener(self.cfg, self.sig.start.emit, self.sig.stop.emit,
                                     self.sig.cancel.emit, lambda: self.state == "recording")
        self.hotkeys.start()

        self.win = MainWindow(self)
        self.sig.progress.connect(self.win.progress)
        self._build_tray()
        self.pending_download: str | None = None   # model the user asked to download
        if not hidden or model_store.active() is None:
            self.win.show()
        self.load_model()
        QTimer.singleShot(10_000, self._first_check)
        self._timer = QTimer(self, interval=600_000, timeout=self._periodic_check)
        self._timer.start()
        QTimer.singleShot(4000, self._startup_warnings)

    def _startup_warnings(self):
        msg = self.hotkeys.problem or self.inserter.error
        if msg:
            self.win.banner(msg)

    def notify(self, title, body=""):
        self.tray.showMessage(title, body, icon("parlance"), 6000)

    # -- dictation -----------------------------------------------------------------
    def toggle(self):
        self.stop() if self.state == "recording" else self.start()

    def start(self):
        if self.state != "idle":
            return
        if self.long_recorder.active:
            self.notify("Microphone busy", "A recording is running in the Transcribe tab.")
            return
        if self.engine.loaded_dir is None and not model_store.active():
            self.win.present_tab("model")
            self.win.banner("The model isn't downloaded yet. Hold tight, or click Download.")
            return
        try:
            self.recorder.start(self.cfg["audio_device"])
        except Exception as e:
            self.notify("Microphone error", str(e))
            return
        if self.cfg["beeps"]:
            audio.beep(880)
        self.set_state("recording")

    def cancel(self):
        if self.state == "recording":
            self.recorder.stop()
            self.set_state("idle")

    def stop(self):
        if self.state != "recording":
            return
        samples = self.recorder.stop()
        if self.cfg["beeps"]:
            audio.beep(620)
        self.set_state("busy")
        threading.Thread(target=self._transcribe, args=(samples,), daemon=True).start()

    def _transcribe(self, samples):
        try:
            text = self.engine.transcribe(samples)
            if text:
                self.inserter.insert(text + (" " if self.cfg["trailing_space"] else ""),
                                     self.cfg["insert"], self.cfg["paste_chord"])
            self.sig.transcribed.emit(text, None)
        except Exception as e:
            self.sig.transcribed.emit("", e)

    def _done(self, text, err):
        log.info("transcript %r err=%r", text, err)
        if err:
            self.notify("Transcription failed", str(err))
        elif text:
            self.history.insert(0, {"text": text, "at": time.time()})
            del self.history[HISTORY_MAX:]
            self._save_history()
            self.win.show_history()
        self.set_state("idle")
        if self.reload_pending:
            self.load_model()

    def clear_history(self):
        self.history.clear()
        self._save_history()
        HISTORY_PATH.unlink(missing_ok=True)
        self.win.show_history()

    def _save_history(self):
        if self.cfg["keep_history"]:
            save_json(HISTORY_PATH, self.history)

    def set_state(self, state):
        log.info("state %s -> %s", self.state, state)
        self.state = state
        self._update_tray()
        self.win.update_state()

    # -- model ---------------------------------------------------------------------
    def load_model(self):
        """(Re)load the active install. Deferred while a take is in flight."""
        if self.state != "idle":
            self.reload_pending = True
            return
        self.reload_pending = False
        cur = model_store.active()
        if cur is None:
            self.engine.unload()
            self.win.update_model()
            self._update_tray()
            return
        self.set_state("busy")
        self.win.status(f"Loading {cur[1].full_label}…")

        def work():
            try:
                self.engine.load(cur[0], self.cfg["num_threads"])
                self.sig.loaded.emit(None)
            except Exception as e:
                self.sig.loaded.emit(e)
        threading.Thread(target=work, daemon=True).start()

    def _loaded(self, err):
        if err:
            self.notify("Couldn't load the model", str(err))
            self.win.banner(f"Couldn't load the model: {err}")
        else:
            cur = model_store.active()
            self.win.status(f"Loaded {cur[1].full_label}." if cur else "")
        self.set_state("idle")

    def select_model(self, mid: str):
        """Switch to another catalogue model. One that isn't on disk yet is downloaded."""
        if self.downloading or mid == model_store.current_id():
            return
        model_store.select(mid)
        self.latest = None
        self.load_model()
        if model_store.active() is None:
            self.pending_download = mid
        self.check_updates(manual=True)
        self.win.update_model()

    def check_updates(self, manual=False):
        self.win.status("Checking Hugging Face for a newer model…")
        mid = model_store.current_id()

        def work():
            try:
                model_store.refresh_catalogue()
                self.sig.checked.emit(model_store.fetch_latest(mid), None, manual)
            except Exception as e:
                self.sig.checked.emit(None, e, manual)
        threading.Thread(target=work, daemon=True).start()

    def _checked(self, latest, err, manual):
        log.info("update check: latest=%s err=%r", latest and latest.label, err)
        if err:
            self.win.status(f"Update check failed: {err}")
            if manual:
                self.notify("Update check failed", str(err))
            return
        state = load_json(STATE_PATH)
        state["last_check"] = time.time()
        save_json(STATE_PATH, state)
        if latest.model != model_store.current_id():     # the user switched model meanwhile
            return
        self.latest = latest
        missing = model_store.active() is None
        if not model_store.needs_update(latest):
            self.win.status(f"Up to date ({latest.full_label}).")
        elif self.pending_download == latest.model or (self.cfg["auto_update"] and not missing):
            self.pending_download = None
            self.download(latest)
        elif missing:
            self.win.status(f"Ready to download {latest.full_label} ({latest.total_size >> 20} MB).")
        else:
            self.win.status(f"Update available: {latest.full_label}")
            if not manual:
                self.notify("Model update available", f"{latest.full_label}. Open {APP_NAME} to install it.")
        self.win.update_model()
        self._update_tray()

    def _first_check(self):
        if model_store.active() is None:
            self.win.present_tab("model")      # first run: pick a model, then Download
            self.check_updates(manual=True)
        else:
            self._periodic_check()

    def _periodic_check(self):
        hours = self.cfg["update_check_hours"]
        last = load_json(STATE_PATH).get("last_check", 0)
        if hours and not self.downloading and time.time() - last >= hours * 3600:
            self.check_updates()

    def download(self, manifest):
        if self.downloading:
            return
        self.downloading = cancel = threading.Event()
        self.win.update_model()

        def progress(done, total, name):
            self.sig.progress.emit(done / total, f"{name}: {done >> 20} / {total >> 20} MB")

        def work():
            try:
                model_store.download(manifest, progress, cancel, keep_old=self.cfg["keep_old_versions"])
                self.sig.downloaded.emit(manifest, None)
            except Exception as e:
                self.sig.downloaded.emit(manifest, e)
        threading.Thread(target=work, daemon=True).start()

    def _downloaded(self, manifest, err):
        self.downloading = None
        if isinstance(err, model_store.Cancelled):
            self.win.status("Download cancelled. It resumes where it stopped next time.")
        elif err:
            self.win.status(f"Download failed: {err}")
            self.notify("Model download failed", str(err))
        else:
            self.notify("Model ready", f"{manifest.full_label}. Ready to dictate.")
            self.win.status(f"Installed {manifest.full_label}.")
            if manifest.model == model_store.current_id():
                self.load_model()
        self.win.progress(-1, "")
        self.win.update_model()
        self._update_tray()

    def update_available(self) -> bool:
        return bool(self.latest and model_store.active() and model_store.needs_update(self.latest))

    # -- tray ----------------------------------------------------------------------
    def _build_tray(self):
        self.tray = QSystemTrayIcon(icon("tray-idle"), self)
        self.tray.setToolTip(APP_NAME)
        m = QMenu()
        self.act_toggle = m.addAction("Start dictation", self.toggle)
        m.addAction("Show window", self.win.present_tab)
        m.addSeparator()
        self.act_update = m.addAction("Install update", lambda: self.latest and self.download(self.latest))
        m.addAction("Check for model update", lambda: self.check_updates(manual=True))
        m.addSeparator()
        hebrish = m.addMenu("Hebrish")
        for label, url in about.HEBRISH_LINKS:
            hebrish.addAction(label, lambda u=url: QDesktopServices.openUrl(QUrl(u)))
        m.addSeparator()
        m.addAction("Quit", self.quit)
        self._menu = m
        self.tray.setContextMenu(m)
        self.tray.activated.connect(self._tray_click)
        self.tray.show()
        self._update_tray()

    def _tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.win.hide() if self.win.isVisible() and self.win.isActiveWindow() else self.win.present_tab()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            self.toggle()

    def _update_tray(self):
        name = "nomodel" if model_store.active() is None else self.state
        self.tray.setIcon(icon(f"tray-{name}"))
        self.tray.setToolTip(f"{APP_NAME}: {dict(idle='ready', recording='listening', busy='working').get(self.state)}")
        self.act_toggle.setText("Stop dictation" if self.state == "recording" else "Start dictation")
        self.act_toggle.setEnabled(self.state != "busy")
        self.act_update.setVisible(self.update_available() and not self.downloading)
        if self.latest:
            self.act_update.setText(f"Install update ({self.latest.version})")

    def quit(self):
        self.win.quitting = True
        self.tray.hide()
        QApplication.quit()


def _selftest() -> int:
    """Used by the Windows CI build: prove the frozen bundle has every native piece.
    A --windowed exe has no stdout, so results go to $PARLANCE_SELFTEST_OUT when set."""
    import os
    out = open(os.environ["PARLANCE_SELFTEST_OUT"], "w") if os.environ.get("PARLANCE_SELFTEST_OUT") else sys.stdout
    try:
        import sherpa_onnx
        import sounddevice
        from .. import hotkey, inserter  # noqa: F401
        if sys.platform == "win32":
            from .. import hotkey_win, inserter_win  # noqa: F401
            import soundfile  # noqa: F401
        from PySide6.QtGui import QGuiApplication
        QGuiApplication([sys.argv[0]])
        sizes = {p.name: icon(p.stem).pixmap(32, 32).isNull() for p in ICONS.glob("*.svg")}
        print("sherpa-onnx", sherpa_onnx.__version__, "| portaudio",
              sounddevice.get_portaudio_version()[1], file=out)
        print("icons (name: failed to render):", sizes, file=out)
        print("latest model:", model_store.fetch_latest().label, file=out)
        if not sizes or any(sizes.values()):
            raise RuntimeError("an icon failed to load (missing Qt SVG plugin?)")
        print("SELFTEST OK", file=out)
        return 0
    except Exception as e:
        import traceback
        traceback.print_exc(file=out)
        print("SELFTEST FAILED:", e, file=out)
        return 1
    finally:
        if out is not sys.stdout:
            out.close()


def main():
    p = argparse.ArgumentParser(prog="parlance")
    p.add_argument("--toggle", action="store_true", help="start or stop dictation in the running app")
    p.add_argument("--hidden", action="store_true", help="start in the tray")
    p.add_argument("--selftest", action="store_true", help=argparse.SUPPRESS)
    args, qt_args = p.parse_known_args()
    if sys.stderr is None:                    # Windows --windowed build: log to a file
        from ..config import DATA_DIR
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=DATA_DIR / "parlance.log", level=logging.INFO,
                            format="%(asctime)s %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if args.selftest:
        sys.exit(_selftest())

    migrate_legacy()
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("parlance")
    app.setWindowIcon(icon("parlance"))
    app.setQuitOnLastWindowClosed(False)

    # single instance: a second launch hands its command to the first and exits
    name = f"parlance-{getpass.getuser()}"
    sock = QLocalSocket()
    sock.connectToServer(name)
    if sock.waitForConnected(500):
        sock.write(b"toggle" if args.toggle else b"show")
        sock.waitForBytesWritten(1000)
        sock.disconnectFromServer()
        return
    if args.toggle:
        print("Hebrish isn't running.", file=sys.stderr)
        sys.exit(1)
    QLocalServer.removeServer(name)            # stale socket from a crash
    server = QLocalServer()
    server.listen(name)

    from .style import QSS
    app.setStyleSheet(QSS)
    ctl = Controller(hidden=args.hidden)

    def on_conn():
        conn = server.nextPendingConnection()
        conn.waitForReadyRead(1000)
        cmd = bytes(conn.readAll()).decode()
        ctl.toggle() if cmd == "toggle" else ctl.win.present_tab()
        conn.disconnectFromServer()
    server.newConnection.connect(on_conn)
    sys.exit(app.exec())
