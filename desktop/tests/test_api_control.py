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


# -- history writes ------------------------------------------------------------------------

@pytest.fixture
def hist_ctl(tmp_path):
    from hebrish.history import History
    h = History(tmp_path / "history.db")
    h.add("I listen to my word prompts", at=100.0, source="file")
    h.add("Nothing to see here", at=200.0)
    ctl = FakeCtl()
    ctl.history, ctl.redrawn = h, []
    ctl.win = SimpleNamespace(show_history=lambda keep_limit=False: ctl.redrawn.append(keep_limit))
    yield ctl
    h.close()


def test_edit_keeps_the_original_and_redraws(hist_ctl):
    c = _control(hist_ctl)
    out = c.edit_history(1, "I listen to My Weird Prompts ")
    assert out["changed"] and out["text"] == "I listen to My Weird Prompts"
    assert out["original"] == "I listen to my word prompts" and hist_ctl.redrawn == [True]
    out = c.edit_history(1, "I listen to My Weird Prompts, daily")
    assert out["original"] == "I listen to my word prompts"         # the model's text, not the first fix
    assert c.edit_history(2, "Nothing to see here")["changed"] is False
    assert hist_ctl.history.get(2)["original"] is None and len(hist_ctl.redrawn) == 2
    with pytest.raises(LookupError):
        c.edit_history(9, "x")


def test_delete_and_relayout_leave_corrections(hist_ctl):
    c = _control(hist_ctl)
    assert c.delete_history(2) == {"id": 2, "deleted": True}
    assert hist_ctl.history.get(2) is None
    with pytest.raises(LookupError):
        c.delete_history(2)
    c.edit_history(1, "I listen to My Weird Prompts")
    hist_ctl.history.relayout(1, "I listen to\n\nmy word prompts")   # the Transcription tab re-flowing
    assert hist_ctl.history.get(1)["text"] == "I listen to My Weird Prompts"


# -- microphones -----------------------------------------------------------------------------

@pytest.fixture
def mic_ctl(monkeypatch):
    from hebrish import mics
    from hebrish.ui import mics as ui_mics
    found = [mics.Mic("usb:046d:0a44:1", "Headset USB", "Logitech Headset", "046d", "0a44", "1", "usb", "headset"),
             mics.Mic("pci:8086:a0c8:", "alsa_input.pci", "Built-in Audio", bus="pci", type_guess="internal"),
             mics.Mic("name:ghost", "", "Can't be opened")]
    monkeypatch.setattr(mics, "list_mics", lambda: found)
    monkeypatch.setattr(ui_mics, "in_use", lambda cfg, k="audio_device": f"in use: {cfg[k] or 'default'}")
    ctl = FakeCtl()
    ctl.cfg.update(audio_device="", tm_audio_device="", mics={}, mic_order=[])
    ctl.calls = []
    ctl.monitor = SimpleNamespace(active=False)
    ctl.win = SimpleNamespace(mics_changed=lambda: ctl.calls.append("refill"),
                              transcribe=SimpleNamespace(tape=SimpleNamespace(active=False)),
                              _on_test=lambda on: ctl.calls.append("test"))
    ctl.stop_monitor = lambda: ctl.calls.append("stop-test")
    return ctl


def test_mics_lists_connected_and_remembers_them(mic_ctl):
    code, out = _control(mic_ctl).mics({})
    assert code == 200 and [m["value"] for m in out["choices"]] == ["", "@preferred", "Headset USB", "alsa_input.pci"]
    assert out["choices"][2]["type"] == "headset" and out["audio_device"]["in_use"] == "in use: default"
    assert set(mic_ctl.cfg["mics"]) == {"usb:046d:0a44:1", "pci:8086:a0c8:", "name:ghost"}


def test_set_mics_by_value_or_key(mic_ctl):
    c = _control(mic_ctl)
    out = c.set_mics({"audio_device": "usb:046d:0a44:1", "tm_audio_device": "@preferred"})[1]
    assert out["changed"] == ["audio_device", "tm_audio_device"] and mic_ctl.cfg["audio_device"] == "Headset USB"
    assert mic_ctl.calls == ["refill"]
    mic_ctl.monitor.active = True
    assert c.set_mics({"audio_device": "alsa_input.pci"})[1]["changed"] == ["audio_device"]
    assert mic_ctl.calls[1:] == ["refill", "stop-test", "test"]          # Test mic follows
    assert c.set_mics({"audio_device": "alsa_input.pci"})[1]["changed"] == []


@pytest.mark.parametrize("body", [{}, {"mic": ""}, {"audio_device": "nope"}, {"audio_device": "name:ghost"},
                                  {"audio_device": 3}])
def test_set_mics_refuses_unknown(mic_ctl, body):
    with pytest.raises(ValueError):
        _control(mic_ctl).set_mics(body)
    assert mic_ctl.cfg["audio_device"] == ""


def test_tm_mic_not_switched_under_a_recording(mic_ctl):
    mic_ctl.win.transcribe.tape.active = True
    with pytest.raises(RuntimeError):
        _control(mic_ctl).set_mics({"tm_audio_device": "Headset USB", "audio_device": "Headset USB"})
    assert mic_ctl.cfg["audio_device"] == ""                            # nothing applied
    assert _control(mic_ctl).set_mics({"tm_audio_device": ""})[1]["changed"] == []
