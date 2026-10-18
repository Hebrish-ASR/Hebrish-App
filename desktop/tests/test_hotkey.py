"""The shared hotkey state machine (both OSes feed it key names)."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from voice_to_hebrish.hotkey import HotkeyMachine, pretty  # noqa: E402
from voice_to_hebrish.inserter import chord_names  # noqa: E402


class Rig:
    def __init__(self, mode, hotkey="KEY_F13"):
        self.events, self.rec = [], False
        cfg = {"hotkey": hotkey, "mode": mode, "hybrid_hold_ms": 50}
        self.m = HotkeyMachine(cfg, self.start, self.stop, self.cancel, lambda: self.rec)

    def start(self):
        self.events.append("start"); self.rec = True

    def stop(self):
        self.events.append("stop"); self.rec = False

    def cancel(self):
        self.events.append("cancel"); self.rec = False

    def tap(self, key="KEY_F13", hold=0.0):
        self.m.key(key, True); time.sleep(hold); self.m.key(key, False)


def test_hold():
    r = Rig("hold"); r.tap(hold=0.01)
    assert r.events == ["start", "stop"]


def test_toggle_needs_two_taps():
    r = Rig("toggle"); r.tap()
    assert r.events == ["start"]
    r.tap()
    assert r.events == ["start", "stop"]


def test_hybrid_tap_latches_and_hold_is_ptt():
    r = Rig("hybrid"); r.tap()
    assert r.events == ["start"]
    r.tap()
    assert r.events == ["start", "stop"]
    r.tap(hold=0.08)
    assert r.events == ["start", "stop", "start", "stop"]


def test_windows_autorepeat_downs_are_ignored():
    r = Rig("toggle")
    for _ in range(5):
        r.m.key("KEY_F13", True)
    r.m.key("KEY_F13", False)
    assert r.events == ["start"]


def test_modifier_chord_cancels():
    r = Rig("hold", hotkey="KEY_RIGHTCTRL")
    r.m.key("KEY_RIGHTCTRL", True); r.m.key("KEY_C", True); r.m.key("KEY_RIGHTCTRL", False)
    assert r.events == ["start", "cancel"]


def test_capture_takes_next_key():
    r = Rig("hold"); got = []
    r.m.capture_next_key(got.append); r.tap("KEY_F20")
    assert got == ["KEY_F20"] and r.events == []


def test_names():
    assert pretty("KEY_RIGHTCTRL") == "Right Ctrl" and pretty("KEY_F13") == "F13"
    assert chord_names("Ctrl+Shift+V") == ["KEY_LEFTCTRL", "KEY_LEFTSHIFT", "KEY_V"]


def test_stretch_pauses_only_inner_short_ones():
    import numpy as np
    from voice_to_hebrish.engine import stretch_pauses
    sr = 16000
    tone = lambda s: (0.3 * np.sin(np.arange(int(s * sr)) / 3)).astype(np.float32)
    z = lambda s: np.zeros(int(s * sr), np.float32)
    x = np.concatenate([z(0.3), tone(1), z(0.2), tone(1), z(1.0), tone(1), z(0.3)])
    y = stretch_pauses(x)
    # only the inner 0.2 s gap grows (to 0.6 s); leading/trailing and the 1 s gap stay
    assert abs((len(y) - len(x)) / sr - 0.4) < 0.03
