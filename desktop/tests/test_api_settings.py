"""GET/POST /v1/app/settings (hebrish.ui.api_control): checked values, all-or-nothing, outputs."""

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")
from hebrish.ui import api_control  # noqa: E402


class Cfg(dict):
    def set(self, k, v):
        self[k] = v


def _control():
    cfg = Cfg({k: False for k in api_control.SETTINGS})
    cfg.update(out_cursor=True, paste_chord="ctrl+v", send_chord="enter", auto_enter_s=8,
               enter_guard="hold", live_insert_s=6, stream_release="phrase", feedback="beeps", beep_volume=50)
    calls = []
    ctl = SimpleNamespace(cfg=cfg, win=SimpleNamespace(sync_output=lambda: calls.append("sync")),
                          apply_vad=lambda: calls.append("vad"), sync_tray_vad=lambda: calls.append("tray"))
    c = api_control.Control.__new__(api_control.Control)
    c.ctl = ctl
    c._main = lambda fn: fn()
    return c, cfg, calls


def test_get_lists_values_and_help():
    c, cfg, _ = _control()
    code, out = c.settings({})
    assert code == 200 and out["settings"]["paste_chord"] == "ctrl+v" and set(out["help"]) == set(api_control.SETTINGS)


def test_set_applies_and_syncs():
    c, cfg, calls = _control()
    code, out = c.set_settings({"out_clipboard": True, "paste_chord": "Ctrl+Shift+V", "vad": True})
    assert sorted(out["changed"]) == ["out_clipboard", "paste_chord", "vad"]
    assert cfg["paste_chord"] == "ctrl+shift+v" and calls == ["sync", "vad", "tray"]


@pytest.mark.parametrize("body", [
    {"out_clipboard": "no"}, {"live_insert_s": 2}, {"beep_volume": 101}, {"feedback": "loud"},
    {"paste_chord": "ctrl+nope"}, {"local_api": False}, {}, {"out_cursor": False},
])
def test_bad_bodies_change_nothing(body):
    c, cfg, _ = _control()
    before = dict(cfg)
    with pytest.raises(ValueError):
        c.set_settings(body)
    assert cfg == before


def test_live_insert_zero_and_output_swap():
    c, cfg, _ = _control()
    c.set_settings({"live_insert_s": 0, "out_cursor": False, "out_window": True})
    assert cfg["live_insert_s"] == 0 and cfg["out_window"] and not cfg["out_cursor"]
