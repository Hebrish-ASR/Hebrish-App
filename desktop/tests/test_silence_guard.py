"""Silence guard (2026-11-15): a take that has recorded SILENCE_GUARD_S of input with no block
peaking above SILENCE_GUARD_DB warns once (tray warning + status line); a take with sound, a
shorter one or a paused one doesn't."""

from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QObject  # noqa: E402

from hebrish import audio  # noqa: E402
from hebrish.ui.app import SILENCE_GUARD_S, Controller  # noqa: E402


class Ctl(Controller):
    def __init__(self, seconds, loudest, paused=False):
        QObject.__init__(self)
        self.state, self._silence_warned, self.notes, self.statuses = "recording", False, [], []
        self.recorder = SimpleNamespace(seconds=seconds, loudest=loudest, paused=paused)
        self.win = SimpleNamespace(status=self.statuses.append)

    def notify(self, title, body="", warn=False):
        self.notes.append((title, warn))


def test_warns_once_after_ten_silent_seconds():
    c = Ctl(SILENCE_GUARD_S, 0.0)
    c._silence_guard()
    c._silence_guard()
    assert c.notes == [("No sound from the microphone", True)] and len(c.statuses) == 1


@pytest.mark.parametrize("seconds,loudest,paused", [
    (SILENCE_GUARD_S - 0.5, 0.0, False),     # not yet 10 s
    (SILENCE_GUARD_S, 10 ** (-60 / 20), False),   # a quiet room's noise floor: the mic works
    (SILENCE_GUARD_S, 0.0, True),             # paused
])
def test_no_warning(seconds, loudest, paused):
    c = Ctl(seconds, loudest, paused)
    c._silence_guard()
    assert c.notes == []


def test_recorder_loudest_skips_muted_cue_and_resets():
    r = audio.Recorder()
    r._open = lambda d: None
    r.start()
    r.mute(60)
    r._cb(np.full((160, 1), 0.5, np.float32), 160, None, None)   # our own beep: muted
    assert r.loudest == 0.0
    r._mute_until = 0.0
    r._cb(np.full((160, 1), 0.01, np.float32), 160, None, None)
    assert r.loudest == pytest.approx(0.01)
    r.start()
    assert r.loudest == 0.0
