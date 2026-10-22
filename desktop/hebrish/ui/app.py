"""Controller: ties hotkey, mic, model and paste together; owns the tray and window.

Threads: the hotkey source and all slow work (model load, decode, HF check, download)
run off the Qt thread. They talk back only through the Signals object, whose
cross-thread emits Qt queues onto the GUI thread.
"""

import argparse
import getpass
import logging
import os
import queue
import sys
from collections import deque
import threading
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import __version__, app_update, audio, autostart, model_store
from ..config import (APP_NAME, HISTORY_DB, HISTORY_PATH, STATE_PATH, Config, in_quiet_hours, load_json,
                      migrate_legacy, import_parlance, models_root, save_json, threads)
from ..engine import Engine, after_held_stop, hold_stop, live_split
from ..history import History
from ..hotkey import make_listener
from ..inserter import make_inserter
from . import about
from .overlay import OverlayHost

log = logging.getLogger("hebrish")
ICONS = Path(__file__).resolve().parent.parent / "data" / "icons"
NO_SPEECH = "no speech"        # _worker -> _done: the take had audio but no speech (engine VAD)
# The beeps mode: start, stop, a falling "doo-doo" for discard, a rising pair for retake
APP_CHECK_S = 24 * 3600       # app update check while running: about daily (at start too)
# Cues play through the speakers while the mic is open (start, resume): the recorder drops
# input for the cue's length plus this, for output latency (0.7.0, Daniel 2026-10-22: spoken
# prompts were ending up in the transcript).
CUE_MARGIN_S = 0.15
BEEPS = {"recording": 880, "transcribing": 620, "discarded": (660, 440), "retake": (523, 880)}


def icon(name: str) -> QIcon:
    return QIcon(str(ICONS / f"{name}.svg"))


# State flag: the one-time move of pre-0.7.0 installs to the desktop default (Shakshuka).
STREAMING_DEFAULT_FLAG = "streaming_default_0_7"   # set by 0.7.0 once it moved dictation to Shakshuka
PARAKEET_DEFAULT_FLAG = "parakeet_default_0_7_1"   # 0.7.1 moved it back (_parakeet_default)

class Signals(QObject):
    start = Signal()
    stop = Signal()
    cancel = Signal()
    action = Signal(str)
    captured = Signal(str)
    transcribed = Signal(str, object, object)   # text, error, the take's samples (for history)
    piece = Signal(str)             # each decoded piece of a take, for the Dictate tab's text box
    fetched = Signal(object, object)    # manifest or None, error: download_model()
    moved = Signal(object)          # error or None: move_models()
    loaded = Signal(object)
    checked = Signal(object, object, bool)
    progress = Signal(float, str)
    downloaded = Signal(object, object)
    app_checked = Signal(object, object, bool)  # app_update.Release or None, error, manual
    app_updated = Signal(bool, str)             # ok, message: the pkexec apt upgrade


class Controller(QObject):
    def __init__(self, hidden: bool, splash=None):
        super().__init__()
        from .window import MainWindow
        self.cfg = Config()
        model_store.set_root(models_root(self.cfg))
        self.engine = Engine()
        self.recorder = audio.Recorder()                       # every take: hotkey or Dictate tab
        self.monitor = audio.Recorder(max_s=0)                 # Test mic: level only, keeps nothing
        self.state = "idle"             # idle | recording | busy
        self.latest: model_store.Manifest | None = None
        self.downloading: threading.Event | None = None
        self.downloading_id: str | None = None     # the model being downloaded
        self.reload_pending = False
        self.loading = False
        self._stopped_at = 0.0
        self.latencies: deque[float] = deque(maxlen=200)   # stop -> text inserted, seconds
        self.splash = splash
        self._overlay_done = False
        # Every transcript (0.7.0): SQLite with a full-text index, hebrish.history. The 0.6.x
        # history.json (last 50) is imported once.
        self.history = History(HISTORY_DB)
        if HISTORY_PATH.is_file():
            log.info("imported %d transcripts from history.json", self.history.import_json(HISTORY_PATH))

        self.sig = Signals()
        self.sig.start.connect(self.start)
        self.sig.stop.connect(self.stop)
        self.sig.cancel.connect(self.cancel)
        self.sig.action.connect(self.do_action)
        self.sig.transcribed.connect(self._done)
        self.sig.loaded.connect(self._loaded)
        self.sig.checked.connect(self._checked)
        self.sig.downloaded.connect(self._downloaded)
        self.sig.fetched.connect(self._fetched)
        self.sig.moved.connect(self._moved)
        self.sig.app_checked.connect(self._app_checked)
        self.sig.app_updated.connect(self._app_updated)
        self.app_release: app_update.Release | None = None    # newer than this app, else None
        self.app_method = app_update.install_method()         # apt | deb-manual | windows | source
        self.app_updating = False
        self.app_installed = ""          # version apt installed this session: waits for a restart

        self.inserter = make_inserter()
        self.hotkeys = make_listener(self.cfg, self.sig.start.emit, self.sig.stop.emit,
                                     self.sig.cancel.emit, lambda: self.state == "recording",
                                     self.sig.action.emit)
        self.hotkeys.start()

        # Decoding runs on one worker, in order: (take, samples, final). Live insertion queues
        # pieces of the take while it is still recording; stop() queues the rest as final.
        # A discarded take bumps self._take, so its queued pieces are dropped.
        self._take = 0
        self._send_take = 0             # Stop and send: the take whose last text gets send_chord
        self._jobs: queue.Queue = queue.Queue()
        threading.Thread(target=self._worker, daemon=True, name="decode").start()
        self._live_timer = QTimer(self, interval=500, timeout=self._live_tick)

        self.overlay = OverlayHost(self)
        self.overlay.action.connect(self.do_action)
        self.overlay.moved.connect(lambda x, y: self.cfg.set("overlay_pos", [x, y]))
        self._level_timer = QTimer(self, interval=66, timeout=self._overlay_push)

        self.win = MainWindow(self)
        self.sig.progress.connect(self.win.progress)
        self._build_tray()
        self.pending_download: str | None = None   # model the user asked to download
        # (model, model it replaces): the one-time switch to the streaming default (0.7.0)
        self.switch_after_download: tuple[str, str] | None = None
        if model_store.active() is None:
            self._close_splash()
            self.win.show()                      # first run: straight to the Model tab
        elif not hidden and splash is None:
            self.win.show()
        elif not hidden:
            QTimer.singleShot(15_000, lambda: self._close_splash(show=True))   # if loading hangs
        self.load_model()
        self._overlay_push()
        try:
            freed = model_store.prune_all()       # older versions kept by 0.5.0 and earlier
            if freed:
                log.info("deleted old model versions: %d MB", freed >> 20)
        except OSError:
            log.exception("pruning old model versions failed")
        QTimer.singleShot(10_000, self._first_check)
        self._timer = QTimer(self, interval=600_000, timeout=self._periodic_check)
        self._timer.start()
        QTimer.singleShot(4000, self._startup_warnings)
        try:
            autostart.refresh()                  # follow this copy if the app moved
        except OSError:
            log.exception("refreshing start at login failed")
        # After the model check, so start-up stays quiet; one small GET, off the GUI thread.
        QTimer.singleShot(30_000, lambda: self.cfg["app_update_check"] and self.check_app_update())

    def _startup_warnings(self):
        msg = self.hotkeys.problem or self.inserter.error
        if msg:
            self.win.banner(msg)

    def _close_splash(self, show=False):
        if self.splash:
            splash, self.splash = self.splash, None
            splash.finish(then=self.win.show if show else None)

    def notify(self, title, body=""):
        self.tray.showMessage(title, body, icon("hebrish"), 6000)

    # -- dictation -----------------------------------------------------------------
    def toggle(self):
        self.stop() if self.state == "recording" else self.start()

    def start(self, cue="recording"):
        if self.state != "idle":
            return
        if self.engine.loaded_dir is None and not model_store.active():
            self.win.present_tab("model")
            self.win.banner("The model isn't downloaded yet. Hold tight, or click Download.")
            return
        self.stop_monitor()
        try:
            self.recorder.start(self.cfg["audio_device"])
        except Exception as e:
            self.notify("Microphone error", str(e))
            return
        self._take += 1
        if self.cfg["clear_each_take"]:
            self.win.new_take()
        self.recorder.mute(self.cue(cue) + CUE_MARGIN_S)
        self.set_state("recording")

    def cue(self, event: str) -> float:
        """Audible feedback (config `feedback`): beeps for start and stop, or a spoken prompt
        for each event (audio.VOICE_PROMPTS) in the chosen `voice`. Nothing when the text
        arrives: it is visible. Returns how long it plays (seconds), for Recorder.mute."""
        mode, vol = self.cfg["feedback"], self.cfg["beep_volume"] / 100
        if mode == "off" or not vol or in_quiet_hours(self.cfg):
            return 0.0
        if mode == "voice":
            return audio.say(event, self.cfg["voice"], volume=0.5 * vol)
        if event in BEEPS:
            return audio.beep(BEEPS[event], volume=0.5 * vol)
        return 0.0

    def cancel(self, quiet=False):
        """Discard the take. With live insertion, text already inserted stays."""
        if self.state == "recording":
            self._take += 1
            self.recorder.stop()
            if not quiet:
                self.cue("discarded")
            self.set_state("idle")

    def pause(self):
        if self.state == "recording":
            self.recorder.resume() if self.recorder.paused else self.recorder.pause()
            played = self.cue("paused" if self.recorder.paused else "resumed")
            if not self.recorder.paused:
                self.recorder.mute(played + CUE_MARGIN_S)
            self._overlay_push()
            self.win.update_state()

    def start_monitor(self):
        """Test mic: open the mic for the level meter only (nothing is recorded or decoded)."""
        if self.state == "idle" and not self.monitor.active:
            self.monitor.start(self.cfg["audio_device"])

    def stop_monitor(self):
        if self.monitor.active:
            self.monitor.stop()

    @property
    def meter_source(self) -> audio.Recorder | None:
        return self.recorder if self.recorder.active else self.monitor if self.monitor.active else None

    # -- actions: overlay buttons and action keys -------------------------------------
    def do_action(self, action):
        if action == "toggle":
            self.toggle()
        elif action == "start":
            self.pause() if self.recorder.paused else self.start()   # a paused take resumes
        elif action == "stop":
            self.stop()
        elif action == "pause":
            self.pause()
        elif action == "discard":
            self.cancel()
        elif action == "retake":
            self.cancel(quiet=True)
            self.start(cue="retake")
        elif action == "send":
            # While recording: stop, and send once the last text is in. Already stopped and
            # still transcribing (_stopped_at is set): send this take when it lands.
            if self.state == "recording" or (self.state == "busy" and self._stopped_at):
                self._send_take = self._take
                self.stop()

    def overlay_changed(self):
        self._overlay_push()

    def _overlay_push(self):
        st = "done" if self._overlay_done else ("idle" if self.loading else self.state)
        show = self.cfg["overlay"]
        self.overlay.send({
            "visible": show == "always" or (show == "active" and st != "idle"),
            "state": st, "paused": self.recorder.paused,
            "seconds": round(self.recorder.seconds, 1), "level": round(self.recorder.level, 3),
            "opacity": self.cfg["overlay_opacity"], "pos": self.cfg["overlay_pos"]})

    def _overlay_clear_done(self):
        self._overlay_done = False
        self._overlay_push()

    def stop(self):
        if self.state != "recording":
            return
        samples = self.recorder.stop()
        self._stopped_at = time.monotonic()
        self.cue("transcribing")
        self.set_state("busy")
        self._jobs.put((self._take, samples, True, None))

    def _live_tick(self):
        """Live insertion: hand the take to the decoder in pieces, cut at a pause."""
        if self.state == "recording" and self.recorder.full:
            self.stop()
            self.notify("Dictation stopped", f"Reached the {audio.DICTATION_MAX_S // 60}-minute limit.")
            return
        interval = self.cfg["live_insert_s"]
        if not interval or self.state != "recording" or self.recorder.paused:
            return
        if self.engine.streaming:
            # Shakshuka: everything recorded so far goes to the stream; whole words come back.
            new = self.recorder.peek()
            if len(new):
                self._jobs.put((self._take, self.recorder.consume(len(new)), False, None))
            return
        cut = live_split(self.recorder.peek(), interval)
        if cut:
            self._jobs.put((self._take, self.recorder.consume(cut[0]), False, cut[1]))

    def _worker(self):
        take, parts, stream, heard_audio, held = None, [], None, [], False
        out = str             # how text leaves the app: as is, or ALL CAPS (read once per take)
        while True:
            job, samples, final, pause = self._jobs.get()
            if job != take:
                take, parts, stream, heard_audio, held = job, [], None, [], False
                # ALL CAPS (0.7.2, Daniel 2026-10-22, "just for fun"): applied only to what is pasted
                # and shown in the text box, so the seam and release rules still see case, and
                # History (which can become training data) keeps the normal case.
                out = str.upper if self.cfg["all_caps"] else str
            heard_audio.append(samples)
            whole_take = (lambda: np.concatenate(heard_audio)) if final else None
            try:
                live = job == self._take
                if live and self.engine.streaming and (stream or not final):
                    # Shakshuka with live insertion: pieces are whole words that continue the
                    # text exactly (they carry their own spaces), so nothing is added between them.
                    stream = stream or self.engine.live(self.cfg["stream_release"])
                    text = stream.finish(samples) if final else stream.feed(samples)
                    space = " " if final and self.cfg["trailing_space"] else ""
                    if text:
                        parts.append(text)
                        self.sig.piece.emit(out(text))
                        if self.cfg["insert"] != "app":
                            self.inserter.insert(out(text + space), self.cfg["insert"], self.cfg["paste_chord"])
                    elif space and parts and not stream.sent.endswith(" ") and self.cfg["insert"] == "paste":
                        # the last words went out at a pause, without the space after them
                        self.inserter.insert(out(space), "paste", self.cfg["paste_chord"])
                    if final and live and parts and job == self._send_take and self.cfg["insert"] == "paste":
                        self._send()
                    if final:
                        whole = "".join(parts).strip()
                        heard = whole or len(samples) < audio.SAMPLE_RATE // 2
                        self.sig.transcribed.emit(whole, None if heard else NO_SPEECH, whole_take())
                    continue
                text = self.engine.transcribe(samples, vad=self.cfg["vad"]) if live else ""
                end = " " if self.cfg["trailing_space"] else ""
                lead = ""
                if text and held:
                    # the previous piece's full stop and space were held back (engine.hold_stop)
                    seam = after_held_stop(text)
                    text = seam.lstrip(". ")
                    lead = seam[: len(seam) - len(text)]
                    if lead.startswith("."):
                        parts[-1] += "."
                elif held and final:
                    lead, parts[-1] = "." + end, parts[-1] + "."
                    self.sig.piece.emit(out(lead))
                    if self.cfg["insert"] != "app":
                        self.inserter.insert(out(lead), self.cfg["insert"], self.cfg["paste_chord"])
                if text:
                    held = not final and hold_stop(text, pause)
                    text = text[:-1] if held else text
                    parts.append(text)
                    self.sig.piece.emit(out(lead + text))
                    space = "" if held else " " if not final else end
                    if self.cfg["insert"] != "app":
                        self.inserter.insert(out(lead + text + space), self.cfg["insert"], self.cfg["paste_chord"])
                if final and live and parts and job == self._send_take and self.cfg["insert"] == "paste":
                    self._send()
                if final:
                    heard = parts or len(samples) < audio.SAMPLE_RATE // 2 or not live
                    self.sig.transcribed.emit(" ".join(parts), None if heard else NO_SPEECH, whole_take())
            except Exception as e:
                if final:
                    self.sig.transcribed.emit("".join(parts).strip() if stream else " ".join(parts), e, None)
                else:
                    log.exception("live piece failed")

    def _send(self):
        """Stop and send: press send_chord after the take's last paste (decode thread)."""
        time.sleep(0.15)          # let the target app take the paste before the Enter
        try:
            self.inserter.press(self.cfg["send_chord"])
        except Exception:
            log.exception("send chord %r failed", self.cfg["send_chord"])

    def _done(self, text, err, samples=None):
        log.info("transcript %r err=%r", text, err)
        if err == NO_SPEECH:
            self.cue("no_speech")
            self.win.status("No speech heard, so nothing was inserted. (Voice detection is on the Dictate tab.)")
        elif err:
            self.cue("failed")
            self.notify("Transcription failed", str(err))
        elif text:
            if self._stopped_at:
                self.latencies.append(time.monotonic() - self._stopped_at)
            self._overlay_done = True              # "Inserted" for a moment
            QTimer.singleShot(1100, self._overlay_clear_done)
            if self.cfg["insert"] == "clipboard":
                self.cue("copied")
            self.remember(text, samples)
        self._stopped_at = 0.0
        self.set_state("idle")
        if self.reload_pending:
            self.load_model()

    def _decode_info(self, source: str) -> dict:
        """What produced a transcript, for History's `decode` column (schema 2, 0.7.3): enough to
        tell two takes of the same weights apart when the app's cut and release rules change."""
        m = model_store.current()
        d = {"app": __version__, "engine": m.engine if m else "", "device": getattr(self.engine, "device", "CPU"),
             "threads": self.engine.threads, "vad": self.cfg["vad"], "all_caps": self.cfg["all_caps"]}
        if source == "dictate":
            d["live_insert_s"] = self.cfg["live_insert_s"]
            if self.engine.streaming:
                d["stream_release"] = self.cfg["stream_release"]
        return d

    def remember(self, text, samples=None, source="dictate", seconds=None):
        """Add a transcript to the history (when `keep_history`): text only, never audio (0.7.3,
        D-2026-10-22-20); samples only give the take's length. The File tab calls this too, with
        source="file" and no samples."""
        if not self.cfg["keep_history"] or not text.strip():
            return
        cur = model_store.active()
        model = f"{cur[1].model} {cur[1].version}" if cur else ""
        if samples is not None:
            seconds = len(samples) / audio.SAMPLE_RATE
        try:
            self.history.add(text, seconds=seconds, model=model, source=source,
                             model_rev=cur[1].revision if cur else None, decode=self._decode_info(source))
        except Exception:
            log.exception("couldn't save the transcript to history")
            return
        self.win.show_history()

    def clear_history(self):
        self.history.clear()
        self.win.show_history()

    def set_state(self, state):
        log.info("state %s -> %s", self.state, state)
        self.state = state
        self._update_tray()
        self.win.update_state()
        for t in (self._level_timer, self._live_timer):
            t.start() if state == "recording" else t.stop()
        self._overlay_push()

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
        self.loading = True
        self.set_state("busy")
        self.win.status(f"Loading {cur[1].full_label}…")
        if self.splash:
            self.splash.set_message(f"Loading {cur[1].full_label}…")

        def work():
            try:
                m = model_store.current()
                self.engine.load(cur[0], threads(self.cfg), m.feature_dim,
                                 streaming=m.engine == "sherpa_online_transducer")
                self.sig.loaded.emit(None)
            except Exception as e:
                self.sig.loaded.emit(e)
        threading.Thread(target=work, daemon=True).start()

    def _loaded(self, err):
        self.loading = False
        self._close_splash(show=True)
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
        self.win.status("Checking for a newer model…")
        mid = model_store.current_id()

        def work():
            try:
                model_store.refresh_catalogue()
                self.sig.checked.emit(model_store.fetch_latest(mid), None, manual)
            except Exception as e:
                self.sig.checked.emit(None, e, manual)
        threading.Thread(target=work, daemon=True).start()

    def _checked(self, latest, err, manual):
        log.info("update check: latest=%s err=%r", latest and latest.debug_label, err)
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
            self._parakeet_default()
            self._periodic_check()

    def _parakeet_default(self):
        """Once: undo 0.7.0's move of dictation to Shakshuka. Daniel, 2026-10-22, after a day of
        use: Parakeet "gave better performance for the dictation use case" and the default
        "should remain parakeet". Only an install that 0.7.0 ran on (its flag is set) and that
        dictates with a streaming model is moved, to the recommended model (Sabich): downloaded
        in the background first if needed, the current model dictating meanwhile. 0.7.0 didn't
        record whether Shakshuka was its switch or the user's pick, so both move; the
        notification says how to go back. A failed download leaves the flag unset (retried)."""
        state = load_json(STATE_PATH)
        if state.get(PARAKEET_DEFAULT_FLAG):
            return
        rec, cur = model_store.recommended_id(), model_store.current_id()
        m, now = model_store.get_model(rec), model_store.get_model(cur)
        streaming = now is not None and now.engine == "sherpa_online_transducer"
        if not state.get(STREAMING_DEFAULT_FLAG) or not streaming or rec == cur or not m or not m.available:
            state[PARAKEET_DEFAULT_FLAG] = True
            save_json(STATE_PATH, state)
            return
        if model_store.active(rec):
            self._switch_to_default(rec)
        elif not self.downloading:
            self.switch_after_download = (rec, cur)
            self.download_model(rec)

    def _switch_to_default(self, mid: str):
        was = model_store.get_model(model_store.current_id())
        self.use_model(mid)
        state = load_json(STATE_PATH)
        state[PARAKEET_DEFAULT_FLAG] = True
        save_json(STATE_PATH, state)
        name = model_store.get_model(mid).name
        self.notify(f"Dictation is back on {name}",
                    f"{name} is the default for dictation again. {was.name if was else 'The streaming model'} "
                    "stays downloaded: switch back to it in Models if you prefer it.")

    def _periodic_check(self):
        hours = self.cfg["update_check_hours"]
        last = load_json(STATE_PATH).get("last_check", 0)
        if hours and not self.downloading and time.time() - last >= hours * 3600:
            self.check_updates()
        last_app = load_json(STATE_PATH).get("app_last_check", 0)
        if self.cfg["app_update_check"] and time.time() - last_app >= APP_CHECK_S:
            self.check_app_update()

    def download(self, manifest):
        if self.downloading:
            return
        self.downloading = cancel = threading.Event()
        self.downloading_id = manifest.model
        self.win.update_model()

        def progress(done, total, name):
            self.sig.progress.emit(done / total, f"{name}: {done >> 20} / {total >> 20} MB")

        def work():
            try:
                model_store.download(manifest, progress, cancel, keep_old=False)
                self.sig.downloaded.emit(manifest, None)
            except Exception as e:
                self.sig.downloaded.emit(manifest, e)
        threading.Thread(target=work, daemon=True).start()

    def _downloaded(self, manifest, err):
        self.downloading = self.downloading_id = None
        if err:
            self.switch_after_download = None      # retried at the next start (flag still unset)
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
            elif self.switch_after_download and self.switch_after_download[0] == manifest.model:
                mid, was = self.switch_after_download
                self.switch_after_download = None
                if model_store.current_id() == was:     # the user hasn't picked another meanwhile
                    self._switch_to_default(mid)
        self.win.progress(-1, "")
        self.win.update_model()
        self._update_tray()

    def download_model(self, mid: str):
        """Download a catalogue model without switching to it (the Models tab's buttons)."""
        if self.downloading:
            return
        self.downloading_id = mid
        self.win.status(f"Looking up {model_store.get_model(mid).name}…")

        def work():
            try:
                self.sig.fetched.emit(model_store.fetch_latest(mid), None)
            except Exception as e:
                self.sig.fetched.emit(None, e)
        threading.Thread(target=work, daemon=True).start()

    def _fetched(self, manifest, err):
        if err:
            self.downloading_id = None
            self.win.status(f"Couldn't look up the model: {err}")
            self.notify("Model download failed", str(err))
            self.win.update_model()
        elif model_store.needs_update(manifest):
            self.download(manifest)
        else:
            self.downloading_id = None
            self.win.status(f"{manifest.full_label} is already downloaded.")
            self.win.update_model()

    def use_model(self, mid: str):
        """Switch to a model that is already downloaded."""
        if mid != model_store.current_id() and model_store.active(mid):
            model_store.select(mid)
            self.latest = None
            self.load_model()
            self.win.update_model()

    def set_models_dir(self, path: str, move: bool):
        """Point the app at another model folder ("" = default), moving the models there first
        when asked. The move runs off the GUI thread: across disks it copies ~660 MB per model."""
        old, new = model_store.ROOT, models_root({"models_dir": path})
        if move and old.is_dir() and old.resolve() != new.resolve():
            self.engine.unload()
            self.set_state("busy")
            self.win.status(f"Moving models to {new}…")

            def work():
                import shutil
                try:
                    new.mkdir(parents=True, exist_ok=True)
                    for d in old.iterdir():
                        if d.is_dir() and not (new / d.name).exists():
                            shutil.move(str(d), new / d.name)
                    self.sig.moved.emit(None)
                except Exception as e:
                    self.sig.moved.emit(e)
            self._moving_to = path
            threading.Thread(target=work, daemon=True).start()
            return
        self.cfg.set("models_dir", path)
        model_store.set_root(new)
        self.latest = None
        self.load_model()
        self.win.update_model()

    def _moved(self, err):
        self.set_state("idle")
        if err:
            self.win.banner(f"Couldn't move the models: {err}. Still using {model_store.ROOT}.")
            self.load_model()
            return
        self.set_models_dir(self._moving_to, move=False)
        self.win.status(f"Models moved to {model_store.ROOT}.")

    # -- app updates (0.6.2, app_update) ---------------------------------------------
    def check_app_update(self, manual=False):
        def work():
            try:
                self.sig.app_checked.emit(app_update.fetch(), None, manual)
            except Exception as e:
                self.sig.app_checked.emit(None, e, manual)
        threading.Thread(target=work, daemon=True, name="app-update").start()

    def _app_checked(self, rel, err, manual):
        log.info("app update check: latest=%s method=%s err=%r", rel and rel.version, self.app_method, err)
        state = load_json(STATE_PATH)
        if err:
            if manual:
                self._app_said(f"Couldn't check for a new {APP_NAME}: {err}")
            return
        state["app_last_check"] = time.time()
        if not app_update.is_newer(rel.version):
            self.app_release = None
            self.win.hide_app_update()
            save_json(STATE_PATH, state)
            self._app_said(f"Up to date: {APP_NAME} {__version__} is the latest.", manual)
            return
        if self.app_installed and not app_update.is_newer(rel.version, self.app_installed):
            save_json(STATE_PATH, state)       # already installed by apt, this copy is the old one
            self._app_said(f"{APP_NAME} {self.app_installed} is installed. Restart {APP_NAME} to use it.", manual)
            return
        self.app_release = rel
        self.win.app_update_status(f"{APP_NAME} {rel.version} is available (you have {__version__}).")
        # Not nagging: a version the user dismissed stays hidden until a newer one (or a manual
        # check), and the tray notification comes once per version.
        if manual or state.get("app_dismissed") != rel.version:
            self.win.show_app_update(rel, self.app_method)
        if manual:
            self.win.present_tab()
        if not manual and state.get("app_notified") != rel.version and state.get("app_dismissed") != rel.version:
            state["app_notified"] = rel.version
            self.notify(f"{APP_NAME} {rel.version} is available", "Open the window to update."
                        if self.app_method == "apt" else f"See the {APP_NAME} window for how to get it.")
        save_json(STATE_PATH, state)

    def _app_said(self, text, manual=True):
        """A check's result: in Settings → App updates, and as a notification when the check was
        asked for from the tray (window hidden)."""
        self.win.app_update_status(text)
        if manual and not self.win.isVisible():
            self.notify(APP_NAME, text)

    def dismiss_app_update(self):
        if self.app_release:
            state = load_json(STATE_PATH)
            state["app_dismissed"] = self.app_release.version
            save_json(STATE_PATH, state)
        self.win.hide_app_update()

    def app_update_action(self):
        """The update bar's button: apt upgrades in place, else the download page."""
        rel = self.app_release
        if rel is None or self.app_updating:
            return
        if self.app_method != "apt":
            QDesktopServices.openUrl(QUrl(app_update.download_page(self.app_method)))
            return
        self.app_updating = True
        self.win.show_app_update(rel, self.app_method, busy=True)

        def work():
            try:
                self.sig.app_updated.emit(*app_update.run_apt_upgrade(rel.version))
            except Exception as e:
                self.sig.app_updated.emit(False, str(e))
        threading.Thread(target=work, daemon=True, name="apt-upgrade").start()

    def _app_updated(self, ok, msg):
        log.info("app update: ok=%s %s", ok, msg)
        self.app_updating = False
        if not ok:
            self.win.show_app_update(self.app_release, self.app_method, error=msg)
            return
        self.app_installed = self.app_release.version if self.app_release else __version__
        self.app_release = None
        self.win.hide_app_update()
        self.win.app_update_status(msg + f" Restart {APP_NAME} to use it.")
        self._update_tray()
        if self.state != "idle":
            self.notify(f"{APP_NAME} updated", msg + " Restart it from the tray menu when you've finished.")
            self._update_tray()
            return
        if self.win.ask_restart(msg):
            self.restart()

    def restart(self):
        app_update.relaunch()
        self.quit()

    def update_available(self) -> bool:
        return bool(self.latest and model_store.active() and model_store.needs_update(self.latest))

    # -- tray ----------------------------------------------------------------------
    def _build_tray(self):
        self.tray = QSystemTrayIcon(icon("tray-idle"), self)
        self.tray.setToolTip(APP_NAME)
        m = QMenu()
        # Checkable actions connect triggered() themselves: PySide's addAction(text, slot) calls
        # the slot without the checked state, so a slot that takes it raised TypeError.
        self.act_toggle = m.addAction("Start dictation", self.toggle)
        self.act_overlay = m.addAction("Show overlay")
        self.act_overlay.setCheckable(True)
        self.act_overlay.triggered.connect(self._tray_overlay)
        m.addAction("Show window", self.win.present_tab)
        self.act_autostart = m.addAction("Start at login")
        self.act_autostart.setCheckable(True)
        self.act_autostart.triggered.connect(self.set_autostart)
        self.act_autostart.setChecked(autostart.enabled())
        m.addSeparator()
        self.act_update = m.addAction("Install update", lambda: self.latest and self.download(self.latest))
        m.addAction("Check for model update", lambda: self.check_updates(manual=True))
        m.addAction("Check for app update", lambda: self.check_app_update(manual=True))
        self.act_restart = m.addAction(f"Restart {APP_NAME} to finish updating", self.restart)
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

    def _tray_overlay(self, on):
        self.cfg.set("overlay", "always" if on else "off")
        self._overlay_push()
        self._update_tray()

    def set_autostart(self, on: bool):
        """Tray menu and Settings both land here, so the two stay in step."""
        try:
            autostart.set_enabled(on)
        except OSError as e:
            log.exception("start at login")
            self.win.banner(f"Couldn't change start at login: {e}")
        on = autostart.enabled()
        self.act_autostart.setChecked(on)
        self.win.sync_autostart(on)

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
        self.act_overlay.setVisible(self.overlay.available)
        self.act_overlay.setChecked(self.cfg["overlay"] != "off")
        self.act_update.setVisible(self.update_available() and not self.downloading)
        self.act_restart.setVisible(bool(self.app_installed))
        if self.latest:
            self.act_update.setText(f"Install update ({self.latest.version})")

    def quit(self):
        self.overlay.close()
        self.win.quitting = True
        self.tray.hide()
        QApplication.quit()


def _selftest() -> int:
    """Used by the Windows CI build: prove the frozen bundle has every native piece.
    A --windowed exe has no stdout, so results go to $HEBRISH_SELFTEST_OUT when set."""
    import os
    out = open(os.environ["HEBRISH_SELFTEST_OUT"], "w") if os.environ.get("HEBRISH_SELFTEST_OUT") else sys.stdout
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
        print("latest model:", model_store.fetch_latest().debug_label, file=out)
        print("latest app:", app_update.fetch().version, "| install:", app_update.install_method(), file=out)
        if not sizes or any(sizes.values()):
            raise RuntimeError("an icon failed to load (missing Qt SVG plugin?)")
        voice = [f"{v}/{k}" for v, _ in audio.VOICES for k in audio.VOICE_PROMPTS
                 if not (audio.VOICE_DIR / v / f"{k}.wav").is_file()]
        print("voice prompts missing:", voice, file=out)
        if voice:
            raise RuntimeError("voice prompts not bundled (package-data data/voice/*.wav)")
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
    # Before anything touches the config/data dirs (the Windows log below creates DATA_DIR).
    import_parlance()
    p = argparse.ArgumentParser(prog="hebrish")
    p.add_argument("--toggle", action="store_true", help="start or stop dictation in the running app")
    p.add_argument("--hidden", action="store_true", help="start in the tray")
    p.add_argument("--selftest", action="store_true", help=argparse.SUPPRESS)
    args, qt_args = p.parse_known_args()
    if sys.stderr is None:                    # Windows --windowed build: log to a file
        from ..config import DATA_DIR
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=DATA_DIR / "hebrish.log", level=logging.INFO,
                            format="%(asctime)s %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if args.selftest:
        sys.exit(_selftest())

    migrate_legacy()
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("hebrish")
    app.setWindowIcon(icon("hebrish"))
    app.setQuitOnLastWindowClosed(False)

    # single instance: a second launch hands its command to the first and exits
    name = f"hebrish-{getpass.getuser()}"
    sock = QLocalSocket()
    sock.connectToServer(name)
    if sock.waitForConnected(500):
        # On Wayland only a fresh xdg-activation token lets the first instance raise its
        # window; the launcher hands one to this process, so pass it along.
        token = os.environ.get("XDG_ACTIVATION_TOKEN", "")
        sock.write(b"toggle" if args.toggle else f"show {token}".strip().encode())
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
    splash = None
    if not args.hidden:
        from .splash import Splash
        splash = Splash(icon("hebrish"))
        splash.show()
        splash.set_message("Starting…")
    ctl = Controller(hidden=args.hidden, splash=splash)

    def on_conn():
        conn = server.nextPendingConnection()
        conn.waitForReadyRead(1000)
        cmd, _, token = bytes(conn.readAll()).decode().partition(" ")
        if token:
            os.environ["XDG_ACTIVATION_TOKEN"] = token   # Qt's Wayland plugin uses it once
        ctl.toggle() if cmd == "toggle" else ctl.win.present_tab()
        conn.disconnectFromServer()
    server.newConnection.connect(on_conn)
    sys.exit(app.exec())
