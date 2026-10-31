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
from PySide6.QtGui import QActionGroup, QColor, QDesktopServices, QIcon, QPalette
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import __version__, app_update, audio, auto_enter, autostart, dictionary, disfluency, engine, local_api, mics, model_store, vad
from ..config import (APP_NAME, HISTORY_DB, HISTORY_PATH, STATE_PATH, Config, in_quiet_hours, load_json,
                      migrate_legacy, import_parlance, models_root, save_json, threads)
from ..engine import REF_S, Engine, after_held_stop, hold_stop, live_split
from ..history import History, maintain
from ..hotkey import make_listener
from ..inserter import copy_to_clipboard, make_inserter
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
# With both the cursor and the clipboard on, the whole take is copied this long after the take's
# last paste chord, so the target app has read the clipboard (the last piece) before it changes.
CLIPBOARD_AFTER_PASTE_MS = 600
# Two pastes are at least this far apart (R-2026-10-25-3: the last piece of a take, pasted soon
# after the one before it, sometimes never showed up). Apps that read the clipboard themselves on
# Ctrl+V (Claude Code runs wl-paste twice) need a moment before the clipboard changes again.
PASTE_GAP_S = 0.4
# How long the overlay offers "No text field · Paste" before it goes back to normal.
NO_FIELD_S = 30
# Enter guard "hold" (1.007): the longest the keyboard is held after Stop. Past it the held Enter
# goes through, and words still to come are kept for Paste, as in "late".
ENTER_HOLD_S = 4.0
BEEPS = {"recording": 880, "transcribing": 620, "discarded": (660, 440), "retake": (523, 880)}


def _in_tm_box(win) -> bool:
    """The Transcription tab's text box has focus (a bool, safe from the decode thread)."""
    return getattr(getattr(win, "transcribe", None), "box_focused", False) is True


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
    take_began = Signal()           # the decoder reached a new take: the Dictate tab's box starts a block
    piece = Signal(str)             # each decoded piece of a take, for the Dictate tab's text box
    no_field = Signal()             # focus.text_target() said False after a take (detect_no_field)
    late = Signal(str)              # words kept out of the next message by the Enter guard
    fetched = Signal(object, object)    # manifest or None, error: download_model()
    moved = Signal(object)          # error or None: move_models()
    loaded = Signal(object)
    checked = Signal(object, object, bool)
    progress = Signal(float, str)
    downloaded = Signal(object, object)
    app_checked = Signal(object, object, bool)  # app_update.Release or None, error, manual
    app_updated = Signal(bool, str)             # ok, message: the pkexec apt upgrade
    maintained = Signal(object, object)         # history upkeep: result dict or None, error
    addon = Signal(str, object)                 # an add-on download finished: add-on id, error or None
    addon_progress = Signal(str, object, object)  # add-on id, bytes done, total


def _before(pieces: list, n: int):
    """The last n samples of a take before its newest piece (engine REF_S), or None."""
    out, have = [], 0
    for p in reversed(pieces[:-1]):
        out.append(p)
        have += len(p)
        if have >= n:
            break
    return np.concatenate(out[::-1])[-n:] if out else None


class Controller(QObject):
    _kept_out_of_tm = False    # a take wasn't pasted: the Transcription box had focus (1.012)

    def __init__(self, hidden: bool, splash=None):
        super().__init__()
        from .window import MainWindow
        self.cfg = Config()
        model_store.set_root(models_root(self.cfg))
        self.engine = Engine()
        self.addon_busy: dict[str, threading.Event] = {}     # add-on id -> cancel, while downloading
        self.addon_done: dict[str, float] = {}               # add-on id -> fraction downloaded
        self.apply_vad()
        self.recorder = audio.Recorder()                       # every take: hotkey or Dictate tab
        self.monitor = audio.Recorder(max_s=0)                 # Test mic: level only, keeps nothing
        self.state = "idle"             # idle | recording | busy
        self.latest: model_store.Manifest | None = None
        self.downloading: threading.Event | None = None
        self.downloading_id: str | None = None     # the model being downloaded
        self.reload_pending = False
        self.loading = False
        self.latencies: deque[float] = deque(maxlen=200)   # stop -> text inserted, seconds
        self.splash = splash
        self._overlay_done = False
        # The last transcription as it went out (ALL CAPS applied), for Paste last (1.000, Daniel
        # 2026-10-24: pasted into the wrong window, "I'm not going to have a way to retrieve that
        # text"). In memory; after a restart Paste last falls back to History's newest entry.
        self.last_text = ""
        self._no_field = False           # the overlay shows "No text field" with Paste
        self._late_text = ""             # the overlay shows "Late words" with Paste (Enter guard)
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
        self.sig.take_began.connect(lambda: self.win.new_take(self.cfg["clear_each_take"]))
        self.sig.no_field.connect(self._show_no_field)
        self.sig.late.connect(self._show_late)
        self.sig.loaded.connect(self._loaded)
        self.sig.checked.connect(self._checked)
        self.sig.downloaded.connect(self._downloaded)
        self.sig.fetched.connect(self._fetched)
        self.sig.moved.connect(self._moved)
        self.sig.app_checked.connect(self._app_checked)
        self.sig.app_updated.connect(self._app_updated)
        self.sig.maintained.connect(self._history_maintained)
        self.sig.addon.connect(self._addon_done)
        self.sig.addon_progress.connect(self._addon_progress)
        self.maintaining = False
        self.app_release: app_update.Release | None = None    # newer than this app, else None
        self.app_method = app_update.install_method()         # apt | deb-manual | windows | source
        self.app_updating = False
        self.app_installed = ""          # version apt installed this session: waits for a restart

        self.inserter = make_inserter()
        self.hotkeys = make_listener(self.cfg, self.sig.start.emit, self.sig.stop.emit,
                                     self.sig.cancel.emit, lambda: self.state == "recording",
                                     self.sig.action.emit)
        self.hotkeys.on_send = self._send_pressed
        self.hotkeys.start()
        if self.cfg["detect_no_field"]:
            from .. import focus
            focus.enable_bus(True)        # apps register with AT-SPI only while it is on
        self.api: local_api.LocalApi | None = None
        self.api_error: str | None = None     # why the local API couldn't start (port in use)
        self.apply_local_api()

        # Decoding runs on one worker, in order: (take, samples, final). Live insertion queues
        # pieces of the take while it is still recording; stop() queues the rest as final.
        # A discarded take's id goes in self._dropped, so its queued pieces are skipped.
        # Takes can overlap (1.001, R-2026-10-24-6): a new take may start while earlier ones are
        # still being decoded; self.pending counts those, and their text arrives in order.
        self._take = 0
        self._dropped: set[int] = set()
        self.pending = 0               # stopped takes whose final text hasn't come back yet
        self._stops: deque[float] = deque()   # when each pending take was stopped, oldest first
        self._send_take = 0             # Stop and send: the take whose last text gets send_chord
        # Enter guard (1.007, R-2026-10-22-2). Takes stopped whose last piece isn't decoded yet;
        # the user's send key pressed meanwhile moves them to _diverted, whose remaining pieces
        # are kept in _late (not pasted) and offered with Paste. In "hold" mode the key source
        # swallows that Enter (_enter_held) and it is replayed after the last paste.
        self._guard = threading.Lock()
        self._unfinished: set[int] = set()
        self._diverted: set[int] = set()
        self._late: dict[int, list[str]] = {}
        self._enter_held = False
        self._hold_timer: threading.Timer | None = None
        self._jobs: queue.Queue = queue.Queue()
        self._pasted_at = 0.0           # time.monotonic() of the last paste chord (PASTE_GAP_S)
        # Press Enter after silence (R-2026-10-31-1, auto_enter.py): text of the recording take
        # pasted since the last Enter (ours or the user's send key), and the take's silence so far.
        self._typed = False
        self._silence = auto_enter.SilenceClock()
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
        # Busy only because earlier takes are still transcribing: start anyway (R-2026-10-24-6).
        # Up to 1.000 the press was ignored while the last take decoded, so the user believed
        # they were recording, and their next press started a take when they meant to stop one.
        if self.state == "recording" or (self.state == "busy" and not self.queued_ok):
            return
        if self.engine.loaded_dir is None and not model_store.active():
            self.win.present_tab("model")
            self.win.banner("The model isn't downloaded yet. Hold tight, or click Download.")
            return
        if self.win.transcribe.tape.active:
            self.notify("Transcription Mode is recording", "Stop that recording before dictating.")
            return
        self.stop_monitor()
        try:
            self.recorder.start(mics.resolve(self.cfg)[0])
        except Exception as e:
            self.notify("Microphone error", str(e))
            return
        self._take += 1
        self._typed = False
        self._silence.reset(0)
        self.recorder.mute(self.cue(cue) + CUE_MARGIN_S)
        self.set_state("recording")

    @property
    def queued_ok(self) -> bool:
        """A take can start now: idle, or busy only with earlier takes still transcribing
        (not loading or moving a model)."""
        return self.state == "idle" or (self.state == "busy" and self.pending > 0 and not self.loading)

    def cue(self, event: str) -> float:
        """Audible feedback (config `feedback`): beeps (in `beep_style`) for start and stop, or a
        spoken prompt for each event (audio.VOICE_PROMPTS) in the chosen `voice`. In quiet hours,
        nothing, or soft beeps with `quiet_sound` "soft". Nothing when the text
        arrives: it is visible. Returns how long it plays (seconds), for Recorder.mute."""
        mode, vol, style = self.cfg["feedback"], self.cfg["beep_volume"] / 100, self.cfg.get("beep_style", "soft")
        if mode == "off" or not vol:
            return 0.0
        if in_quiet_hours(self.cfg):
            if self.cfg.get("quiet_sound") != "soft":
                return 0.0
            mode, style = "beeps", "soft"
        if mode == "voice":
            return audio.say(event, self.cfg["voice"], volume=0.5 * vol)
        if event in BEEPS:
            return audio.beep(BEEPS[event], volume=0.5 * vol, style=style)
        return 0.0

    def cancel(self, quiet=False):
        """Discard the take. With live insertion, text already inserted stays."""
        if self.state == "recording":
            self._dropped.add(self._take)
            self.recorder.stop()
            if not quiet:
                self.cue("discarded")
            self.set_state("busy" if self.pending else "idle")

    def pause(self):
        if self.state == "recording":
            self.recorder.resume() if self.recorder.paused else self.recorder.pause()
            played = self.cue("paused" if self.recorder.paused else "resumed")
            if not self.recorder.paused:
                self.recorder.mute(played + CUE_MARGIN_S)
                self._silence.reset(self.recorder.tail()[1])    # the silence timer starts again
            self._overlay_push()
            self.win.update_state()

    def start_monitor(self):
        """Test mic: open the mic for the level meter only (nothing is recorded or decoded)."""
        if self.state == "idle" and not self.monitor.active:
            self.monitor.start(mics.resolve(self.cfg)[0])

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
        elif action == "paste_last":
            self.paste_last()
        elif action == "paste_late":
            self.paste_last(self._late_text)
        elif action == "dismiss_no_field":
            self._clear_no_field()
            self._clear_late()
        elif action == "send":
            # While recording: stop, and send once the last text is in. Already stopped and
            # still transcribing (pending): send this take when it lands.
            if self.state == "recording" or (self.state == "busy" and self.pending):
                self._send_take = self._take
                self.stop()

    def paste_last(self, text=""):
        """Paste the last transcription at the cursor (action key, tray, the overlay's Paste), or
        `text` (the overlay's Paste for late words). Not during a take: its own pieces are being
        pasted."""
        if self.state != "idle":
            return
        text = text or self.last_text
        if not text and self.cfg["keep_history"]:
            rows = self.history.recent(1)
            text = rows[0]["text"] if rows else ""
        if not text:
            self._said("No transcription to paste yet.")
            return
        if _in_tm_box(getattr(self, "win", None)):
            self.win.status("Paste last doesn't paste into the Transcription box.")
            return
        self._clear_no_field()
        self._clear_late()
        end = " " if self.cfg["trailing_space"] else ""

        def go():
            # Let the action key (or the click on the overlay) finish first: a paste chord
            # pressed while another key is still down can come out as a different shortcut.
            time.sleep(0.25)
            try:
                self.inserter.insert(text + end, "paste", self.cfg["paste_chord"])
            except Exception:
                log.exception("paste last failed")
        threading.Thread(target=go, daemon=True).start()

    def _check_field(self, take_text):
        """detect_no_field: after a pasted take, ask AT-SPI (off the GUI thread) whether a text
        field had focus; hebrish.focus says why only a definite "no" prompts."""
        from .. import focus

        def ask():
            if focus.text_target() is False:
                self.sig.no_field.emit()
        threading.Thread(target=ask, daemon=True).start()

    def _show_no_field(self):
        if self.state != "idle" or not self.last_text or self._late_text:
            return
        # The whole take on the clipboard too, so Ctrl+V works wherever the user clicks next.
        self._copy_take(self.last_text)
        self._no_field = True
        self._overlay_push()
        QTimer.singleShot(NO_FIELD_S * 1000, self._clear_no_field)

    def _clear_no_field(self):
        if self._no_field:
            self._no_field = False
            self._overlay_push()

    # -- Enter guard (1.007) ----------------------------------------------------------
    def _send_pressed(self, held: bool):
        """The user's send key (key thread). Takes still to finish keep their remaining words
        out of whatever the Enter just sent; held (hold mode), the Enter waits for them."""
        self._typed = False               # Press Enter after silence: this Enter sent what was typed
        if self.cfg["enter_guard"] == "off" or not self.cfg["out_cursor"]:
            return
        with self._guard:
            if held:
                self._enter_held = True
                log.info("send key held until the last words are in")
            elif self._unfinished:
                self._diverted |= self._unfinished
                log.info("send key before the last words: keeping take(s) %s", sorted(self._unfinished))

    def _hold_send(self):
        """After Stop, in hold mode: the key source holds the send key until _finish_take."""
        if self.cfg["enter_guard"] != "hold" or not self.cfg["out_cursor"]:
            return
        if self.hotkeys.hold_send(True) and not self._hold_timer:
            self._hold_timer = threading.Timer(ENTER_HOLD_S, self._hold_timeout)
            self._hold_timer.daemon = True
            self._hold_timer.start()

    def _release_hold(self, replay: bool):
        """End the hold (call with self._guard held); replay a held Enter now if asked."""
        if self._hold_timer:
            self._hold_timer.cancel()
            self._hold_timer = None
        self.hotkeys.hold_send(False)
        held, self._enter_held = self._enter_held, False
        if held and replay:
            threading.Thread(target=self._replay_enter, daemon=True).start()

    def _replay_enter(self):
        time.sleep(0.15)          # let the target app take the paste before the Enter
        try:
            self.inserter.press("enter")
        except Exception:
            log.exception("replaying the held Enter failed")

    def _hold_timeout(self):
        """ENTER_HOLD_S passed with words still to come: the held Enter goes now, and those
        words are kept for Paste."""
        with self._guard:
            self._hold_timer = None
            if self._enter_held:
                self._diverted |= self._unfinished
                log.info("Enter hold timed out: sending, keeping take(s) %s", sorted(self._unfinished))
            self._release_hold(replay=True)

    def _out(self, job, text):
        """A piece leaving the app (decode thread): kept back if the Enter guard diverted its take."""
        with self._guard:
            if job in self._diverted:
                self._late.setdefault(job, []).append(text)
                return
        if self._insert(text) and job == self._take and text.strip():
            self._typed = True

    def _auto_enter(self, job, heard):
        """Press Enter after silence (decode thread, after the pieces queued before it are pasted).
        heard: the silence clock's last speech when the Enter was queued; speech since then (or a
        pause, a stop, an Enter already sent) cancels it."""
        with self._guard:
            if (not self.cfg["auto_enter"] or not self._typed or job != self._take
                    or self.state != "recording" or self.recorder.paused or self._silence.heard != heard
                    or job in self._diverted or self._enter_held or _in_tm_box(getattr(self, "win", None))):
                return
            self._typed = False
        time.sleep(0.15)          # let the target app take the paste before the Enter
        try:
            self.inserter.press(self.cfg["send_chord"] or "enter")
            log.info("pressed %r after silence", self.cfg["send_chord"] or "enter")
        except Exception:
            log.exception("Enter after silence failed")

    def _auto_enter_tick(self, buf, total) -> bool:
        """Press Enter after silence, from _live_tick (GUI thread). Once the take has been silent
        for auto_enter_s with text to send: hand any speech not yet decoded to the worker, then
        an Enter marker that runs after it. Returns True when it took the unconsumed audio."""
        silence = self._silence.update(buf, total, auto_enter.speech_frames)
        delay = min(auto_enter.MAX_S, max(auto_enter.MIN_S, self.cfg["auto_enter_s"] or auto_enter.DEFAULT_S))
        untyped = self._silence.untyped(buf, total)
        if not self._silence.due(delay, silence, self._typed or untyped):
            return False
        log.info("%.1f s of silence: Enter after the text so far", silence)
        if untyped:
            self._jobs.put((self._take, self.recorder.consume(len(buf)), False, silence))
        self._jobs.put((self._take, None, False, self._silence.heard))
        return untyped

    def _finish_take(self, job):
        """The decoder is done with a stopped take (decode thread)."""
        with self._guard:
            self._unfinished.discard(job)
            late = "".join(self._late.pop(job, [])).strip() if job in self._diverted else ""
            self._diverted.discard(job)
            if not self._unfinished and (self.hotkeys.holding or self._enter_held):
                self._release_hold(replay=True)
        if late:
            self.sig.late.emit(late)

    def _show_late(self, text):
        log.info("kept %d chars after an early Enter", len(text))
        self._clear_no_field()
        self._late_text = text
        self._copy_take(text)
        self.win.status("Enter was pressed before the last words were in, so they weren't pasted. "
                        "They're on the clipboard, and Paste on the overlay puts them where the cursor is.")
        self._overlay_push()
        QTimer.singleShot(NO_FIELD_S * 1000, lambda t=text: self._late_text == t and self._clear_late())

    def _clear_late(self):
        if self._late_text:
            self._late_text = ""
            self._overlay_push()

    def overlay_changed(self):
        self._overlay_push()

    def _overlay_push(self):
        st = "done" if self._overlay_done else ("idle" if self.loading else self.state)
        if self._late_text and st == "idle":
            st = "late"
        elif self._no_field and st == "idle":
            st = "nofield"
        show = self.cfg["overlay"]
        self.overlay.send({
            # "No text field" shows even with the overlay off: it is the only place for Paste
            # that doesn't take the keyboard focus from the field the user clicks into.
            "visible": show == "always" or (show != "off" and st != "idle") or st in ("nofield", "late"),
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
        self._stops.append(time.monotonic())
        self.pending += 1
        with self._guard:
            self._unfinished.add(self._take)
        self._hold_send()
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
        buf, total = self.recorder.tail()
        if self.cfg["auto_enter"] and self.cfg["out_cursor"] and self._auto_enter_tick(buf, total):
            return
        if self.engine.streaming:
            # Shakshuka: everything recorded so far goes to the stream; whole words come back.
            if len(buf):
                self._jobs.put((self._take, self.recorder.consume(len(buf)), False, None))
            return
        cut = live_split(buf, interval)
        if cut:
            self._jobs.put((self._take, self.recorder.consume(cut[0]), False, cut[1]))

    def _worker(self):
        take, parts, stream, heard_audio, held, ctx = None, [], None, [], False, None
        fresh = False         # an Enter after silence was just pressed: the next text starts a new message
        out = str             # how text leaves the app: as is, or ALL CAPS (read once per take)
        fix = str             # the personal dictionary (read once per take)
        while True:
            job, samples, final, pause = self._jobs.get()
            if samples is None:
                # Press Enter after silence (_auto_enter_tick): the take's pieces before it are in.
                # A full stop held back at the last seam goes out first, and what follows is
                # decoded without that piece as context: it starts the next message.
                if job == take and job not in self._dropped:
                    if held and parts:
                        parts[-1] += "."
                        self._show(out("."))
                        if self._typed:       # not after the user's own Enter: "." alone would be sent
                            self._out(job, out("."))
                    held, ctx, fresh = False, None, True
                    self._auto_enter(job, pause)
                continue
            if job != take:
                take, parts, stream, heard_audio, held, ctx = job, [], None, [], False, None
                fresh = False
                if job not in self._dropped:
                    self.sig.take_began.emit()
                # ALL CAPS (0.7.2, Daniel 2026-10-22, "just for fun"): applied only to what is pasted
                # and shown in the text box, so the seam and release rules still see case, and
                # History (which can become training data) keeps the normal case.
                out = str.upper if self.cfg["all_caps"] else str
                # Personal dictionary (0.8.0; ../shared/personal-dictionary.md): applied to each piece
                # after the seam rules, before ALL CAPS. Unlike ALL CAPS it reaches History, which
                # holds what was meant.
                try:
                    fix = dictionary.compile(dictionary.load())
                except Exception:
                    log.exception("couldn't read the personal dictionary")
                    fix = str
            heard_audio.append(samples)
            whole_take = (lambda: np.concatenate(heard_audio)) if final else None
            try:
                live = job not in self._dropped
                if live and self.engine.streaming and (stream or not final):
                    # Shakshuka with live insertion: pieces are whole words that continue the
                    # text exactly (they carry their own spaces), so nothing is added between them.
                    stream = stream or self.engine.live(self.cfg["stream_release"])
                    text = stream.finish(samples) if final else stream.feed(samples)
                    space = " " if final and self.cfg["trailing_space"] else ""
                    if text:
                        text = fix(disfluency.chop(text, "".join(parts[-1:])))   # whole words with their own spaces; stream.sent keeps the raw text
                        parts.append(text)
                        typed = text.lstrip() if fresh else text   # no leading space in a new message
                        fresh = False
                        self._show(out(typed))
                        self._out(job, out(typed + space))
                    elif space and parts and not stream.sent.endswith(" ") and self.cfg["out_cursor"]:
                        # the last words went out at a pause, without the space after them
                        self._out(job, out(space))
                    if final and live and parts and job == self._send_take and self._sends(job):
                        self._send()
                    if final:
                        whole = "".join(parts).strip()
                        heard = whole or len(samples) < audio.SAMPLE_RATE // 2
                        self.sig.transcribed.emit(whole, None if heard else NO_SPEECH, whole_take())
                    continue
                # 0.7.6: each piece is decoded after the end of the one before it (engine.CONTEXT_S),
                # unless that one was cut without a pause (a forced cut may split a word)
                ref = _before(heard_audio, REF_S * audio.SAMPLE_RATE)
                text, stop = (self.engine.transcribe_after(samples, ctx, vad=self.cfg["vad"], ref=ref)
                              if live else ("", None))
                if final:
                    log.info("last piece: %.1f s of audio, %d words", len(samples) / audio.SAMPLE_RATE,
                             len(text.split()))
                # 1.001: fillers out first, 1.007 repeats too (../shared/disfluencies.md); the piece
                # before (its held full stop back on) catches a repeat across the seam
                text = disfluency.chop(text, parts[-1] + ("." if held else "") if parts else "")
                ctx = samples if pause else None
                end = " " if self.cfg["trailing_space"] else ""
                lead = ""
                if text and held:
                    # the previous piece's full stop and space were held back (engine.hold_stop)
                    seam = after_held_stop(text, stop)
                    text = seam.lstrip(". ")
                    lead = seam[: len(seam) - len(text)]
                    if lead.startswith("."):
                        parts[-1] += "."
                elif held and final:
                    lead, parts[-1] = "." + end, parts[-1] + "."
                    self._show(out(lead))
                    self._out(job, out(lead))
                if text:
                    fresh = False
                    held = not final and hold_stop(text, pause)
                    text = fix(text[:-1] if held else text)
                    parts.append(text)
                    self._show(out(lead + text))
                    space = "" if held else " " if not final else end
                    self._out(job, out(lead + text + space))
                if final and live and parts and job == self._send_take and self._sends(job):
                    self._send()
                if final:
                    heard = parts or len(samples) < audio.SAMPLE_RATE // 2 or not live
                    self.sig.transcribed.emit(" ".join(parts), None if heard else NO_SPEECH, whole_take())
            except Exception as e:
                if final:
                    self.sig.transcribed.emit("".join(parts).strip() if stream else " ".join(parts), e, None)
                else:
                    log.exception("live piece failed")
            finally:
                if final:
                    self._finish_take(job)

    def _show(self, text):
        """A piece for the Dictate tab's text box, when that output is on (decode thread)."""
        if self.cfg["out_window"]:
            self.sig.piece.emit(text)

    def _insert(self, text) -> bool:
        """A piece out of the app (decode thread): pasted at the cursor, or, with only the
        clipboard on, copied. The window is [_show]'s; the whole take's copy is [_done]'s.
        True when it was pasted at the cursor."""
        if self.cfg["out_cursor"] and _in_tm_box(getattr(self, "win", None)):
            # Voice Typing never types into the Transcription box (1.012, Daniel): that box is
            # Transcription Mode's alone. The take goes to History and the clipboard instead.
            self._kept_out_of_tm = True
            log.info("not pasted: the Transcription box has focus")
        elif self.cfg["out_cursor"]:
            wait = PASTE_GAP_S - (time.monotonic() - self._pasted_at)
            if wait > 0:
                time.sleep(wait)
            self.inserter.insert(text, "paste", self.cfg["paste_chord"])
            self._pasted_at = time.monotonic()
            log.info("pasted %d chars", len(text))
            return True
        elif self.cfg["out_clipboard"]:
            self.inserter.insert(text, "clipboard", self.cfg["paste_chord"])
        return False

    def _copy_take(self, text):
        try:
            copy_to_clipboard(text)
        except Exception:
            log.exception("couldn't copy the take")

    def _sends(self, job) -> bool:
        """Stop and send presses send_chord after this take: not if the user already sent."""
        with self._guard:
            return (self.cfg["out_cursor"] and job not in self._diverted and not self._enter_held
                    and not _in_tm_box(getattr(self, "win", None)))

    def _send(self):
        """Stop and send: press send_chord after the take's last paste (decode thread)."""
        time.sleep(0.15)          # let the target app take the paste before the Enter
        try:
            self.inserter.press(self.cfg["send_chord"])
        except Exception:
            log.exception("send chord %r failed", self.cfg["send_chord"])

    def _feedback(self, event):
        """A cue after a take, which may play while the next take records: keep it off that take."""
        played = self.cue(event)
        if self.state == "recording":
            self.recorder.mute(played + CUE_MARGIN_S)

    def _done(self, text, err, samples=None):
        log.info("transcript %r err=%r", text, err)
        stopped_at = self._stops.popleft() if self._stops else 0.0
        self.pending = max(0, self.pending - 1)
        if err == NO_SPEECH:
            self._feedback("no_speech")
            self.win.status("No speech heard, so nothing was inserted. (Voice detection is on the Voice Typing tab.)")
        elif err:
            self._feedback("failed")
            self.notify("Transcription failed", str(err))
        elif text:
            if stopped_at:
                self.latencies.append(time.monotonic() - stopped_at)
            if self.state != "recording":          # "Inserted" for a moment, unless the next take is on
                self._overlay_done = True
                QTimer.singleShot(1100, self._overlay_clear_done)
            if self._kept_out_of_tm:
                self._kept_out_of_tm = False
                if not self.cfg["out_clipboard"]:
                    self._copy_take(text.upper() if self.cfg["all_caps"] else text)
                self.win.status("Voice Typing doesn't type into the Transcription box. "
                                "The take is on the clipboard and in History.")
            if self.cfg["out_clipboard"]:
                # The whole take, not just its last piece (1.000). After a paste, wait for the
                # target app to read the clipboard first, or it would paste the whole take.
                whole = text.upper() if self.cfg["all_caps"] else text
                QTimer.singleShot(CLIPBOARD_AFTER_PASTE_MS if self.cfg["out_cursor"] else 0,
                                  lambda: self._copy_take(whole))
                if not self.cfg["out_cursor"]:
                    self._feedback("copied")
            self.last_text = text.upper() if self.cfg["all_caps"] else text
            if self.cfg["out_cursor"] and self.cfg["detect_no_field"]:
                self._check_field(self.last_text)
            self.remember(text, samples)
        if self.state != "recording":
            self.set_state("busy" if self.pending else "idle")
        if self.reload_pending and self.state == "idle":
            self.load_model()

    def _decode_info(self, source: str) -> dict:
        """What produced a transcript, for History's `decode` column (schema 2, 0.7.3): enough to
        tell two takes of the same weights apart when the app's cut and release rules change."""
        m = model_store.current()
        d = {"app": __version__, "engine": m.engine if m else "", "device": getattr(self.engine, "device", "CPU"),
             "threads": self.engine.threads, "vad": self.cfg["vad"], "all_caps": self.cfg["all_caps"]}
        if self.cfg["vad"]:
            d["vad_model"] = "silero" if engine.silero else "energy"
        if source == "dictate":
            d["live_insert_s"] = self.cfg["live_insert_s"]
            if self.engine.streaming:
                d["stream_release"] = self.cfg["stream_release"]
        return d

    def remember(self, text, samples=None, source="dictate", seconds=None, extra=None):
        """Add a transcript to the history (when `keep_history`): text only, never audio (0.7.3,
        D-2026-10-22-20); samples only give the take's length. The Transcription tab calls this too, with
        source="file" or "record" (Transcription Mode) and no samples; `extra` is added to the row's
        decode info (the clean-up model, B-40). Returns the row id, or None."""
        if not self.cfg["keep_history"] or not text.strip():
            return None
        cur = model_store.active()
        model = f"{cur[1].model} {cur[1].version}" if cur else ""
        if samples is not None:
            seconds = len(samples) / audio.SAMPLE_RATE
        try:
            rid = self.history.add(text, seconds=seconds, model=model, source=source,
                                   model_rev=cur[1].revision if cur else None,
                                   decode={**self._decode_info(source), **(extra or {})})
        except Exception:
            log.exception("couldn't save the transcript to history")
            return None
        self.win.show_history()
        return rid

    def relayout_history(self, rid: int, text: str):
        """The Transcription tab re-flowed a transcript's paragraphs (B-44): same words, new
        layout, so History shows what the tab shows."""
        try:
            self.history.relayout(rid, text)
        except Exception:
            log.exception("couldn't update the transcript in history")
            return
        self.win.show_history()

    def clear_history(self):
        try:
            self.history.clear()
        except Exception as e:
            log.exception("clearing the history failed")
            self.win.banner(f"Couldn't clear the history: {e}")
        self.win.show_history()

    def maintain_history(self, manual=False):
        """History upkeep (1.009, B-69: hebrish.history.maintain) in a background thread, about
        daily from the 10-minute check, or from Diagnostics → Tidy now. Only while idle: the first
        run on an older file is a full VACUUM, and a transcript saved meanwhile waits for it."""
        if self.maintaining or (self.state != "idle" or self.pending) and not manual:
            return
        self.maintaining = True

        def go():
            try:
                self.sig.maintained.emit(maintain(self.history.path), None)
            except Exception as e:
                log.exception("history upkeep failed")
                self.sig.maintained.emit(None, e)
        threading.Thread(target=go, daemon=True, name="history-upkeep").start()

    def _history_maintained(self, out, err):
        self.maintaining = False
        if out:
            log.info("history upkeep: %d -> %d bytes in %.2f s%s", out["before"], out["after"],
                     out["seconds"], " (converted to incremental vacuum)" if out["vacuumed"] else "")
        self.win.history_maintained(out, err)

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
            self._said(f"Up to date ({latest.full_label}).", manual)
        elif self.pending_download == latest.model or (self.cfg["auto_update"] and not missing):
            self.pending_download = None
            self.download(latest)
        elif missing:
            self._said(f"Ready to download {latest.full_label} ({latest.total_size >> 20} MB).", manual)
        else:
            self.win.status(f"Update available: {latest.full_label}")
            if not manual or not self.win.isVisible():
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
        hours, state = self.cfg["update_check_hours"], load_json(STATE_PATH)
        if hours and not self.downloading and time.time() - state.get("last_check", 0) >= hours * 3600:
            self.check_updates()
        if self.cfg["app_update_check"] and time.time() - state.get("app_last_check", 0) >= APP_CHECK_S:
            self.check_app_update()
        if self.history.due():
            self.maintain_history()

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
        self.apply_vad()
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

    # -- add-ons (Models > Utilities, 2026-10-29) --------------------------------------
    def apply_vad(self):
        """Voice detection uses Silero (bundled) unless `vad_silero` is off (vad.py)."""
        path = vad.installed() if self.cfg["vad_silero"] else None
        if path is None:
            engine.silero = None
        elif engine.silero is None or engine.silero.path != path:
            engine.silero = vad.Silero(path)
        log.info("voice detection: %s", "silero" if engine.silero else "energy")

    @staticmethod
    def addon_fetchers() -> dict:
        """Add-on id -> download(on_progress, cancel). Silero VAD is bundled, so it has none; each
        offered clean-up model has its own (they share one llama.cpp runtime)."""
        from .. import cleanup, paragraphs
        out = {paragraphs.MODEL_ID: paragraphs.download}
        for e in cleanup.entries():
            out[e["id"]] = lambda p, c, a=e["id"]: cleanup.download(a, p, c)
        return out

    def download_addon(self, aid: str):
        """Fetch an add-on (the paragraph model, the clean-up model) off the GUI thread."""
        if aid in self.addon_busy:
            return
        fetch = self.addon_fetchers()[aid]
        cancel = self.addon_busy[aid] = threading.Event()
        self.addon_done[aid] = 0.0

        def work():
            try:
                fetch(lambda d, t, _n: self.sig.addon_progress.emit(aid, d, t), cancel)
                self.sig.addon.emit(aid, None)
            except Exception as e:
                self.sig.addon.emit(aid, e)
        threading.Thread(target=work, daemon=True).start()
        self.win.update_model()

    def _addon_progress(self, aid: str, done, total):
        if aid in self.addon_busy:
            self.addon_done[aid] = done / max(1, total)
            self.win.addon_progress(aid)

    def _addon_done(self, aid: str, err):
        cancelled = self.addon_busy.pop(aid, threading.Event()).is_set()
        self.addon_done.pop(aid, None)
        if err and not cancelled:
            self.win.banner(f"Couldn't download the utility: {err}")
        elif not err:
            self.win.status("Utility downloaded.")
        self.win.transcribe.sync_cleanup()
        self.win.update_model()

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

    def _said(self, text, manual=True):
        """A result the user asked for: in the window's status line, and as a notification when
        the window is hidden (asked from the tray or an action key), where the status can't be seen."""
        self.win.status(text)
        if manual and not self.win.isVisible():
            self.notify(APP_NAME, text)

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
        m.addAction("Paste last transcription", self.paste_last)
        self.act_overlay = m.addAction("Show overlay")
        self.act_overlay.setCheckable(True)
        self.act_overlay.triggered.connect(self._tray_overlay)
        m.addAction("Show window", self.win.present_tab)
        self._build_output_menu(m.addMenu("Output"))
        self.act_tm_vad = m.addAction("Voice detection (Transcription)")
        self.act_tm_vad.setCheckable(True)
        self.act_tm_vad.setToolTip("Transcription Mode's voice detection: skip silence and trim long pauses")
        self.act_tm_vad.triggered.connect(lambda on: self.win.transcribe.set_vad(on))
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

    def _build_output_menu(self, menu):
        """Output switches and paste shortcut, so switching to a terminal (ctrl+shift+v) or to
        clipboard-only doesn't mean opening Settings. The outputs (1.000) are independent checks,
        the shortcuts a radio group. Checks are re-read from the config each time the menu opens,
        so changes made in the window show here too."""
        from .window import OUTPUT, PASTE_CHORDS
        self._output_acts, self._chord_acts = {}, {}
        for acts, options, slot in ((self._output_acts, OUTPUT, self._tray_output),
                                    (self._chord_acts, PASTE_CHORDS, self._tray_chord)):
            group = QActionGroup(menu) if acts is self._chord_acts else None
            for val, label in options:
                a = menu.addAction(label)
                a.setCheckable(True)
                if group:
                    group.addAction(a)
                a.triggered.connect(lambda _on, v=val, f=slot: f(v))
                acts[val] = a
            if acts is self._output_acts:
                menu.addSeparator()
        menu.aboutToShow.connect(self._sync_output_menu)

    def _sync_output_menu(self):
        for val, a in self._output_acts.items():
            a.setChecked(bool(self.cfg[val]))
        for val, a in self._chord_acts.items():   # a custom chord leaves both unchecked
            a.setChecked(self.cfg["paste_chord"] == val)
            a.setEnabled(bool(self.cfg["out_cursor"]))

    def _tray_output(self, key):
        """Flip one output; the last one on stays on (nothing would go anywhere but History)."""
        from .window import OUTPUT
        on = not self.cfg[key]
        if on or any(self.cfg[k] for k, _ in OUTPUT if k != key):
            self.cfg.set(key, on)
        self.win.sync_output()

    def _tray_chord(self, value):
        self.cfg.set("paste_chord", value)
        self.win.sync_output()

    def sync_tray_vad(self):
        if hasattr(self, "act_tm_vad"):
            self.act_tm_vad.setChecked(bool(self.cfg["tm_vad"]))

    def sync_tray_tape(self):
        """The Transcription recorder started, paused or stopped: the tray shows it too, so a long
        session is visible with the window hidden."""
        if hasattr(self, "tray"):
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
        # "finishing" (R-2026-10-25-3): Stop was pressed and the take's last words are still being
        # decoded and pasted. Amber with three dots, so it doesn't read as done.
        state = "finishing" if self.state == "busy" and self.pending and not self.loading else self.state
        name = "nomodel" if model_store.active() is None else state
        tip = dict(idle="ready", recording="listening", busy="working",
                   finishing="finishing, the last words are on the way")[state]
        tape = getattr(getattr(self.win, "transcribe", None), "tape", None)
        if tape is not None and tape.active and state == "idle":
            # Transcription Mode recording (2026-10-29): the listening icon, unless paused
            name = name if tape.paused or name == "nomodel" else "recording"
            tip = "Transcription Mode " + ("paused" if tape.paused else "recording") + \
                  (", voice detection on" if self.cfg["tm_vad"] else ", voice detection off")
        self.tray.setIcon(icon(f"tray-{name}"))
        self.tray.setToolTip(f"{APP_NAME}: {tip}")
        self.act_toggle.setText("Stop dictation" if self.state == "recording" else "Start dictation")
        self.act_toggle.setEnabled(self.state != "busy" or self.queued_ok)
        self.act_overlay.setVisible(self.overlay.available)
        self.act_overlay.setChecked(self.cfg["overlay"] != "off")
        self.act_tm_vad.setChecked(bool(self.cfg["tm_vad"]))
        self.act_update.setVisible(self.update_available() and not self.downloading)
        self.act_restart.setVisible(bool(self.app_installed))
        if self.latest:
            self.act_update.setText(f"Install update ({self.latest.version})")

    def api_info(self) -> dict | None:
        """The loaded model, for the local API; None while nothing is loaded."""
        if self.engine.loaded_dir is None:
            return None
        cur, m = model_store.active(), model_store.current()
        return {"id": m.id if m else model_store.current_id(),
                "name": cur[1].full_label if cur else (m.name if m else ""),
                "version": cur[1].version if cur else None,
                "streaming": self.engine.streaming}

    def api_transcribe(self, samples) -> str:
        """A file sent to the local API (HTTP thread): Transcription Mode's text before paragraphs."""
        fix = dictionary.compile(dictionary.load())
        return " ".join(fix(disfluency.chop(t))
                        for t in self.engine.transcribe_chunks(samples, vad=self.cfg["tm_vad"])).strip()

    def apply_local_api(self) -> str | None:
        """Start, stop or move the local API to match the config; returns why it couldn't start."""
        want, port = self.cfg["local_api"], int(self.cfg["local_api_port"])
        if self.api and (not want or self.api.port != port):
            self.api.stop()
            self.api = None
        if want and self.api is None:
            api = local_api.LocalApi(self.api_transcribe, self.api_info, port)
            if not api.start():
                self.api_error = api.error
                return api.error
            self.api = api
        self.api_error = None
        return None

    def quit(self):
        from .. import cleanup
        if self.api:
            self.api.stop()
        cleanup.stop()                       # the clean-up model's llama-server, if it runs
        self.hotkeys.hold_send(False)
        self.win.transcribe.tape.stop()      # closed cleanly; offered again on the next start
        self.stop_monitor()
        if self.recorder.active:             # the take is lost either way; close the stream
            self.recorder.stop()
        self.overlay.close()
        self.history.close()                 # last WAL checkpoint, so no -wal file is left
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
        # Paragraph model (B-44): the onnxruntime package beside sherpa-onnx's own onnxruntime
        # library, in one process. Downloaded into a temp folder, not the user's models.
        import tempfile
        import onnxruntime
        from .. import paragraphs
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            old = model_store.ROOT
            model_store.set_root(Path(tmp))
            try:
                got = paragraphs.Breaker(paragraphs.download()).apply("Call me back when you can. Thanks.")
            finally:
                model_store.set_root(old)
        print("onnxruntime", onnxruntime.__version__, "| paragraph model:", repr(got), file=out)
        if got != "Call me back when you can.\n\nThanks.":
            raise RuntimeError("the paragraph model gave the wrong breaks")
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
    from .style import colours
    pal = app.palette()                    # links (About, Models) in the brand accent, not Qt's blue
    pal.setColor(QPalette.Link, QColor(colours()["accent"]))
    app.setPalette(pal)

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
