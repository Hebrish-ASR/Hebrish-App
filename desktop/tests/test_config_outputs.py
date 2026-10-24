"""1.000: the single `insert` choice became three output switches (config.upgrade)."""

import pytest

from hebrish.config import DEFAULTS, upgrade


@pytest.mark.parametrize("mode,cursor,clip,window", [
    ("paste", True, False, False), ("clipboard", False, True, False), ("app", False, False, True)])
def test_insert_becomes_switches(mode, cursor, clip, window):
    s = upgrade({"insert": mode, "clear_each_take": True, "feedback": "beeps", "send_chord": "enter"})
    assert "insert" not in s
    assert (s["out_cursor"], s["out_clipboard"], s["out_window"]) == (cursor, clip, window)
    assert s["clear_each_take"] is False          # takes collect, a blank line between them


def test_new_defaults_paste_only():
    assert (DEFAULTS["out_cursor"], DEFAULTS["out_clipboard"], DEFAULTS["out_window"]) == (True, False, False)
    assert "insert" not in DEFAULTS


def test_switches_left_alone_once_upgraded():
    s = upgrade({"out_cursor": False, "out_clipboard": True, "out_window": True, "clear_each_take": True,
                 "feedback": "beeps", "send_chord": "enter"})
    assert (s["out_cursor"], s["out_clipboard"], s["out_window"], s["clear_each_take"]) == (False, True, True, True)
