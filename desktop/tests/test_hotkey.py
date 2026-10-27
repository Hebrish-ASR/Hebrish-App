"""The shared hotkey state machine (both OSes feed it key names)."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from hebrish.hotkey import HotkeyMachine, pretty  # noqa: E402
from hebrish.inserter import chord_names  # noqa: E402


class Rig:
    def __init__(self, mode, hotkey="KEY_F13", ptt=""):
        self.events, self.rec = [], False
        # the 0.2.x modes, expressed in the 0.3.0 keys
        cfg = {"hotkey": hotkey, "ptt_hotkey": ptt, "hold_to_talk": mode == "hybrid",
               "hybrid_hold_ms": 50}
        if mode == "hold":
            cfg["hotkey"], cfg["ptt_hotkey"] = "", hotkey
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


def test_separate_toggle_and_ptt_keys():
    r = Rig("toggle", hotkey="KEY_F13", ptt="KEY_F14")
    r.tap("KEY_F14", hold=0.01)
    assert r.events == ["start", "stop"]            # PTT: release stops
    r.tap("KEY_F13")
    assert r.events[-1] == "start" and r.rec        # toggle latches
    r.tap("KEY_F14")
    assert r.rec and r.events[-1] == "start"        # PTT doesn't stop a toggled take
    r.tap("KEY_F13")
    assert r.events[-1] == "stop"


def test_other_hotkey_ignored_while_one_is_held():
    r = Rig("toggle", hotkey="KEY_F13", ptt="KEY_F14")
    r.m.key("KEY_F14", True); r.m.key("KEY_F13", True); r.m.key("KEY_F13", False)
    r.m.key("KEY_F14", False)
    assert r.events == ["start", "stop"]


def test_unset_keys_do_nothing():
    r = Rig("toggle", hotkey="", ptt="")
    r.tap(""); r.tap("KEY_F13")
    assert r.events == []


V05 = {"feedback": "beeps", "keep_history": True, "live_insert_s": 6}    # what upgrade() gives a pre-0.5.0 config (0.7.0: 10 -> 7, history on; 0.7.1: 7 -> 5; R-2026-10-25-3: 5 -> 6)


def test_upgrade_old_modes():
    from hebrish.config import upgrade
    assert upgrade({"mode": "hold", "hotkey": "KEY_F9"}) == {"hotkey": "", "ptt_hotkey": "KEY_F9", **V05}
    assert upgrade({"mode": "toggle"}) == {"hold_to_talk": False, **V05}
    assert upgrade({"mode": "hybrid", "hotkey": "KEY_F9"}) == {"hotkey": "KEY_F9", **V05}


def test_upgrade_to_0_5_0_defaults():
    """Daniel, 2026-10-21: insert as you go every ~10 s and no history by default, for existing
    installs too; `beeps` became `feedback`. A config that already has `feedback` is left alone."""
    from hebrish.config import upgrade
    assert upgrade({"beeps": False, "live_insert_s": 0, "keep_history": True}) == \
        {"feedback": "off", "live_insert_s": 6, "keep_history": True}    # 0.5.0 off, 0.7.0 on again; 10, 7, 5, then 6
    assert upgrade({"beeps": True, "live_insert_s": 20})["live_insert_s"] == 20
    kept = {"feedback": "voice", "live_insert_s": 0, "keep_history": True}
    assert upgrade(dict(kept)) == kept
    assert upgrade({}) == {}


def test_upgrade_to_0_7_0_turns_history_on_once():
    """Daniel, 2026-10-22 (D-2026-10-22-13): history on by default. A config without
    `clear_each_take` predates 0.7.0, so its keep_history False was the forced 0.5.0 default.
    One saved by 0.7.0 keeps whatever the user chose."""
    from hebrish.config import upgrade
    assert upgrade({"feedback": "beeps", "send_chord": "enter", "keep_history": False})["keep_history"] is True
    chosen = {"feedback": "beeps", "send_chord": "enter", "clear_each_take": True, "keep_history": False}
    assert upgrade(dict(chosen)) == chosen


def test_vad_skips_silence_and_shortens_long_pauses():
    import numpy as np
    from hebrish.engine import has_speech, shorten_silences
    sr = 16000
    rng = np.random.default_rng(0)
    hiss = lambda s: rng.normal(0, 0.001, int(s * sr)).astype(np.float32)
    tone = lambda s: (0.1 * np.sin(np.arange(int(s * sr)) / 3)).astype(np.float32)
    assert not has_speech(hiss(3))
    x = np.concatenate([hiss(0.5), tone(1), hiss(3), tone(1), hiss(0.7), tone(1)])
    assert has_speech(x)
    y = shorten_silences(x)
    assert abs(len(y) / sr - (0.5 + 1 + 0.8 + 1 + 0.7 + 1)) < 0.05      # only the 3 s pause shrank


def test_capture_takes_next_key():
    r = Rig("hold"); got = []
    r.m.capture_next_key(got.append); r.tap("KEY_F20")
    assert got == ["KEY_F20"] and r.events == []


def test_names():
    assert pretty("KEY_RIGHTCTRL") == "Right Ctrl" and pretty("KEY_F13") == "F13"
    assert chord_names("Ctrl+Shift+V") == ["KEY_LEFTCTRL", "KEY_LEFTSHIFT", "KEY_V"]


def test_stretch_pauses_only_inner_short_ones():
    import numpy as np
    from hebrish.engine import stretch_pauses
    sr = 16000
    tone = lambda s: (0.3 * np.sin(np.arange(int(s * sr)) / 3)).astype(np.float32)
    z = lambda s: np.zeros(int(s * sr), np.float32)
    x = np.concatenate([z(0.3), tone(1), z(0.2), tone(1), z(1.0), tone(1), z(0.3)])
    y = stretch_pauses(x)
    # only the inner 0.2 s gap grows (to 0.6 s); leading/trailing and the 1 s gap stay
    assert abs((len(y) - len(x)) / sr - 0.4) < 0.03


def test_action_keys_fire_on_press_only():
    r = Rig("toggle")
    acts = []
    r.m._action = acts.append
    r.m._cfg.update({"key_pause": "KEY_F15", "key_retake": "KEY_F16"})
    r.tap("KEY_F15")
    r.tap("KEY_F16")
    assert acts == ["pause", "retake"] and r.events == []


def test_stop_and_send_key_is_an_action():
    r = Rig("toggle")
    acts = []
    r.m._action = acts.append
    r.m._cfg["key_send"] = "KEY_F17"
    r.tap("KEY_F17")
    assert acts == ["send"] and r.events == []


def test_action_key_does_not_cancel_a_modifier_take():
    r = Rig("toggle", hotkey="KEY_RIGHTCTRL")
    r.m._action = lambda a: None
    r.m._cfg["key_stop"] = "KEY_F15"
    r.m.key("KEY_RIGHTCTRL", True)
    r.tap("KEY_F15")
    assert r.events == ["start"]


def _rig05():
    """A toggle key with the 0.5.0 built-ins on (double tap = retake, Esc = discard)."""
    r = Rig("hybrid")
    r.m._cfg.update(double_tap_retake=True, double_tap_ms=80, escape_discards=True)
    r.m._action = lambda a: r.events.append(a)
    return r


def test_double_tap_while_recording_is_retake():
    r = _rig05()
    r.tap()                                   # start
    r.tap(); time.sleep(0.02); r.tap()        # double tap
    time.sleep(0.15)
    assert r.events == ["start", "retake"] and r.rec


def test_single_tap_stops_after_the_double_tap_window():
    r = _rig05()
    r.tap(); r.tap()
    assert r.events == ["start"]              # waiting for a possible second tap
    time.sleep(0.15)
    assert r.events == ["start", "stop"]


def test_escape_discards_only_while_recording():
    r = _rig05()
    r.tap("KEY_ESC")
    assert r.events == []
    r.tap(); r.tap("KEY_ESC")
    assert r.events == ["start", "cancel"]
    r.m._cfg["escape_discards"] = False
    r.tap(); r.tap("KEY_ESC")
    assert r.events == ["start", "cancel", "start"]


def _sender(chord="enter"):
    m = HotkeyMachine({"hotkey": "KEY_F13", "ptt_hotkey": "", "hold_to_talk": False, "hybrid_hold_ms": 50,
                       "send_chord": chord}, lambda: None, lambda: None, lambda: None, lambda: False)
    seen = []
    m.on_send = seen.append

    def press(name, down=True):
        swallow = m.send_key(name, down)
        m.key(name, down)
        return swallow
    return m, seen, press


def test_send_key_is_reported_not_swallowed():
    # Enter guard (1.007): every Enter, main or keypad, is reported; nothing is swallowed by default
    m, seen, press = _sender()
    assert press("KEY_ENTER") is False and press("KEY_ENTER", False) is False
    assert press("KEY_KPENTER") is False
    assert seen == [False, False]


def test_send_key_matches_the_chord_modifiers():
    m, seen, press = _sender("ctrl+enter")
    press("KEY_ENTER"); press("KEY_ENTER", False)            # a plain Enter: a new line there
    press("KEY_RIGHTCTRL"); press("KEY_ENTER")                 # either Ctrl counts
    assert seen == [False]
    m, seen, press = _sender()
    press("KEY_LEFTSHIFT"); press("KEY_ENTER")                 # Shift+Enter is not a plain Enter
    assert seen == []


def test_held_send_key_is_swallowed_with_its_release():
    m, seen, press = _sender()
    m.hold_send(True)
    assert press("KEY_ENTER") is True and press("KEY_ENTER") is True   # autorepeat too
    m.hold_send(False)
    assert press("KEY_ENTER", False) is True                   # its release, even after the hold ends
    assert press("KEY_ENTER") is False                         # the next Enter goes through
    assert seen == [True, False]
    assert m.send_key("KEY_ENTER", True, can_hold=False) is False   # an ungrabbed keyboard's Enter
