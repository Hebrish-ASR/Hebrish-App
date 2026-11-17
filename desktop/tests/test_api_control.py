"""hebrish.ui.api_control beyond settings (B-108, 2026-11-17): dictation actions, history writes,
microphones, model removal, Transcription Mode. Fakes for the Controller; no Qt event loop."""

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from hebrish.ui import api_control  # noqa: E402


class Cfg(dict):
    def set(self, k, v):
        self[k] = v


class FakeCtl:
    """The parts of Controller that Control touches; do_action follows Controller.do_action."""

    def __init__(self, state="idle", paused=False, pending=0):
        self.state, self.pending, self.actions = state, pending, []
        self.recorder = SimpleNamespace(paused=paused)
        self.cfg = Cfg()

    def do_action(self, action):
        self.actions.append(action)
        if action == "pause":
            self.recorder.paused = not self.recorder.paused


def _control(ctl):
    c = api_control.Control.__new__(api_control.Control)
    c.ctl = ctl
    c._main = lambda fn: fn()
    return c


@pytest.mark.parametrize("action", ["start", "stop", "toggle", "retake", "send"])
def test_dictation_runs_the_action_key(action):
    ctl = FakeCtl("recording")
    code, out = _control(ctl).dictation({"action": action})
    assert code == 200 and ctl.actions == [action] and out["action"] == action


def test_pause_and_resume_never_toggle_the_wrong_way():
    ctl = FakeCtl("recording")
    c = _control(ctl)
    assert c.dictation({"action": "pause"})[1]["paused"] is True
    assert c.dictation({"action": "pause"})[1]["paused"] is True       # already paused: nothing
    assert ctl.actions == ["pause"]
    assert c.dictation({"action": "resume"})[1]["paused"] is False
    assert c.dictation({"action": "resume"})[1]["paused"] is False
    assert ctl.actions == ["pause", "pause"]


@pytest.mark.parametrize("action,state", [("pause", "idle"), ("resume", "busy"), ("discard", "idle"),
                                          ("send", "idle"), ("paste_last", "recording")])
def test_nothing_to_act_on_is_409(action, state):
    ctl = FakeCtl(state)
    with pytest.raises(RuntimeError):
        _control(ctl).dictation({"action": action})
    assert ctl.actions == []


def test_send_while_the_last_take_transcribes_and_paste_when_idle():
    ctl = FakeCtl("busy", pending=1)
    _control(ctl).dictation({"action": "send"})
    ctl.state = "idle"
    _control(ctl).dictation({"action": "paste_last"})
    assert ctl.actions == ["send", "paste_last"]


def test_unknown_action_is_400():
    with pytest.raises(ValueError, match="paste_last"):
        _control(FakeCtl()).dictation({"action": "dance"})
