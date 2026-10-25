"""1.001 (R-2026-10-24-6): a take can start while the previous one is still transcribing, and
the texts land in order. Up to 1.000 a press during "busy" was ignored, so the user thought
they were recording and the next press started a take they meant to stop."""

import queue
import threading
import time
from collections import deque
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QObject  # noqa: E402

from hebrish.ui.app import Controller  # noqa: E402


class Ctl(Controller):
    """The Controller's take logic without its window, tray, hotkeys or model."""

    def __init__(self):
        QObject.__init__(self)
        self.state, self.loading, self.pending, self.reload_pending = "idle", False, 0, False
        self._take, self._dropped, self._stops, self._send_take = 0, set(), deque(), 0
        self._jobs, self.latencies, self.states, self.out = queue.Queue(), deque(), [], []
        self._overlay_done, self._no_field, self.last_text = False, False, ""
        self.cfg = {"clear_each_take": False, "audio_device": "", "feedback": "off", "beep_volume": 0,
                    "out_clipboard": False, "out_cursor": True, "detect_no_field": False,
                    "all_caps": False, "keep_history": False, "vad": False, "trailing_space": True,
                    "out_window": False, "paste_chord": "ctrl+v", "live_insert_s": 0}
        self.recorder = SimpleNamespace(start=lambda d: None, stop=lambda: np.ones(16000, np.float32),
                                        mute=lambda s: None, paused=False)
        self.engine = SimpleNamespace(loaded_dir="x", streaming=False,
                                      transcribe_after=lambda s, c, vad, ref=None: (f"take of {len(s)}", None))
        self.win = SimpleNamespace(transcribe=SimpleNamespace(tape=SimpleNamespace(active=False)),
                                   new_take=lambda c: None, status=lambda m: None)
        self.inserter = SimpleNamespace(insert=lambda t, how, chord: self.out.append(t))
        self._pasted_at = 0.0
        self.sig = SimpleNamespace(take_began=SimpleNamespace(emit=lambda: self.out.append("|")),
                                   piece=SimpleNamespace(emit=lambda t: None),
                                   transcribed=SimpleNamespace(emit=lambda *a: self.done.append(a)))
        self.done = []

    def set_state(self, state):
        self.state = state
        self.states.append(state)

    def stop_monitor(self):
        pass


def test_start_while_transcribing_records_at_once():
    c = Ctl()
    c.start()
    c.stop()
    assert c.state == "busy" and c.pending == 1 and c.queued_ok
    c.start()                                   # the press that 1.000 ignored
    assert c.state == "recording" and c._take == 2
    c._done("first take", None)                 # take 1's text lands while take 2 records
    assert c.state == "recording" and c.pending == 0 and not c._overlay_done
    c.stop()
    c._done("second take", None)
    assert c.state == "idle"


def test_two_queued_takes_stay_busy_until_both_land():
    c = Ctl()
    for _ in range(2):
        c.start()
        c.stop()
    assert c.pending == 2
    c._done("one", None)
    assert c.state == "busy"
    c._done("two", None)
    assert c.state == "idle" and len(c.latencies) == 2


def test_no_start_while_a_model_loads():
    c = Ctl()
    c.state, c.loading = "busy", True
    c.start()
    assert c.state == "busy" and c._take == 0


def test_discard_while_earlier_take_transcribes_goes_back_to_busy():
    c = Ctl()
    c.start()
    c.stop()
    c.start()
    c.cancel(quiet=True)
    assert c.state == "busy" and 2 in c._dropped and 1 not in c._dropped


def test_worker_decodes_in_order_and_skips_discarded():
    c = Ctl()
    threading.Thread(target=c._worker, daemon=True).start()
    c._dropped.add(2)
    c._jobs.put((1, np.zeros(100, np.float32), True, None))
    c._jobs.put((2, np.zeros(200, np.float32), False, None))       # discarded take's piece
    c._jobs.put((3, np.zeros(300, np.float32), True, None))
    deadline = time.monotonic() + 3
    while len(c.done) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert [d[0] for d in c.done] == ["take of 100", "take of 300"]
    assert c.out == ["|", "take of 100 ", "|", "take of 300 "]
