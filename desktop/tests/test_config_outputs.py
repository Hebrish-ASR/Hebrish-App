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


def test_model_check_moves_from_24_to_6_hours_once():
    # R-2026-11-13-4: the old default moves once; a later or chosen value stays
    s = upgrade({"update_check_hours": 24, "send_chord": "enter", "feedback": "beeps"})
    assert s["update_check_hours"] == 6 and s["model_check_6h"]
    assert upgrade({"update_check_hours": 12, "send_chord": "enter", "feedback": "beeps"})["update_check_hours"] == 12
    assert upgrade(dict(s, update_check_hours=24))["update_check_hours"] == 24
    assert DEFAULTS["update_check_hours"] == 6 and DEFAULTS["auto_update"]
