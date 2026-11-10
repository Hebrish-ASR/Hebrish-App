"""1.000: Paste last transcription, and the "No text field" check (hebrish.focus)."""

import threading
import time
from types import SimpleNamespace

import pytest

from hebrish import focus
from hebrish.config import DEFAULTS
from hebrish.hotkey import ACTIONS, SLOTS


def test_classify_text_targets():
    assert focus.classify("gedit", "text", False)
    assert focus.classify("firefox", "section", True)               # contenteditable: EDITABLE state
    assert focus.classify("konsole", "filler", False)               # seen 2026-10-24: a terminal is a target
    assert not focus.classify("dolphin", "list item", False)
    assert not focus.classify("plasmashell", "push button", False)


def test_action_key_slot_exists():
    assert ("paste_last", "Paste last transcription") in ACTIONS
    assert "key_paste_last" in SLOTS and DEFAULTS["key_paste_last"] == ""
    assert DEFAULTS["detect_no_field"] is False


def _ctl(last="", history=(), state="idle", keep_history=True, visible=True, late=""):
    pytest.importorskip("PySide6")
    from hebrish.ui.app import Controller
    pasted, done = [], threading.Event()
    ctl = SimpleNamespace(
        state=state, last_text=last, _late_last=late, _no_field=False,
        cfg={"keep_history": keep_history, "trailing_space": True, "paste_chord": "ctrl+v"},
        history=SimpleNamespace(recent=lambda n: [{"text": t} for t in history][:n]),
        inserter=SimpleNamespace(insert=lambda t, how, chord: (pasted.append((t, how)), done.set())),
        win=SimpleNamespace(status=lambda m: (pasted.append(("STATUS", m)), done.set()),
                            isVisible=lambda: visible))
    ctl.notify = lambda title, body="": pasted.append(("NOTIFY", body))
    ctl._said = lambda text, manual=True: Controller._said(ctl, text, manual)
    ctl._clear_no_field = lambda: None
    ctl._clear_late = lambda: None
    Controller.paste_last(ctl)
    done.wait(2)
    return pasted


def test_paste_last_uses_memory():
    assert _ctl(last="Shalom, see you Motzei Shabbat.") == [("Shalom, see you Motzei Shabbat. ", "paste")]


def test_paste_last_after_early_enter_is_only_the_late_words():
    """B-88: the start of the take went in before Enter, so it must not be pasted a second time."""
    assert _ctl(last="Whole take, already sent, and the end.", late="and the end.") == [("and the end. ", "paste")]


def test_paste_last_falls_back_to_history():
    assert _ctl(history=["From before the restart."]) == [("From before the restart. ", "paste")]


def test_paste_last_nothing_yet():
    assert [k for k, _ in _ctl(keep_history=False)] == ["STATUS"]


def test_paste_last_nothing_yet_window_hidden_notifies():
    """From the tray or an action key the window is hidden: its status line can't be seen."""
    assert [k for k, _ in _ctl(keep_history=False, visible=False)] == ["STATUS", "NOTIFY"]


def test_paste_last_not_during_a_take():
    pytest.importorskip("PySide6")
    from hebrish.ui.app import Controller
    ctl = SimpleNamespace(state="recording", last_text="x")
    assert Controller.paste_last(ctl) is None          # returns before touching anything else


def _copied(whole, late):
    pytest.importorskip("PySide6")
    from hebrish.ui.app import Controller
    copied = []
    ctl = SimpleNamespace(_late_last=late, _copy_take=copied.append)
    Controller._copy_whole(ctl, whole)
    return copied


def test_whole_take_does_not_overwrite_late_words_on_the_clipboard():
    """1.029: with "whole take on the clipboard" on, the delayed copy of the whole take replaced the
    late words _show_late had just copied, so Ctrl+V pasted the whole take again."""
    assert _copied("Whole take, already sent, and the end.", "and the end.") == []


def test_whole_take_still_copied_without_late_words():
    assert _copied("Whole take.", "") == ["Whole take."]
    # late words from another (overlapping) take don't stop this one's copy
    assert _copied("The next take.", "and the end.") == ["The next take."]
