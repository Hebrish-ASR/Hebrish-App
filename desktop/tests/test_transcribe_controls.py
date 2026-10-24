"""B-45 (Daniel, 2026-10-24): the Transcription tab's Record card has a dedicated Pause button,
and the Levels panel (gain + level meter) is docked (hidden) by default, can be shown in the
card or float in its own tool window, and the choice is remembered in `tm_levels`.

Off-screen Qt with a fake recorder: nothing opens the mic."""

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402

from hebrish import audio, config  # noqa: E402
from hebrish.ui import transcribe  # noqa: E402
from hebrish.ui.window import card, muted  # noqa: E402

app = QApplication.instance() or QApplication([])


class FakeTape:
    """The parts of longform.TapeRecorder the page uses; never touches a mic."""

    def __init__(self):
        self.gain_db = 0.0
        self.rms = self.peak = 0.0
        self.clipped_at = 0.0
        self.paused = False
        self.active = False
        self.full = False
        self.seconds = 0.0
        self.path = None
        self.started = 0

    def start(self, device=""):
        self.active, self.paused = True, False
        self.started += 1

    def pause(self):
        if self.active:
            self.paused = True

    def resume(self):
        if self.active:
            self.paused = False

    def stop(self):
        self.active = self.paused = False
        return None

    def discard(self):
        self.stop()

    def switch_device(self, device):
        pass


class FakeWin:
    def status(self, _text):
        pass


class FakeCtl:
    state = "idle"

    def __init__(self, cfg):
        self.cfg, self.win = cfg, FakeWin()

    def stop_monitor(self):
        pass

    def notify(self, *_a):
        pass


@pytest.fixture
def make(monkeypatch):
    monkeypatch.setattr(audio, "input_devices", lambda: [])
    made = []

    def _make(stored=None):
        if config.CONFIG_PATH.exists():
            config.CONFIG_PATH.unlink()
        if stored is not None:
            config.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            config.CONFIG_PATH.write_text(json.dumps(stored))
        cfg = config.Config()
        host = QWidget()
        page = transcribe.TranscribePage(FakeCtl(cfg), card, muted)
        page.tape = FakeTape()
        QVBoxLayout(host).addWidget(page)
        host.show()
        app.processEvents()
        page._sync()
        made.append(host)
        return host, page, cfg

    yield _make
    for h in made:
        h.close()
        h.deleteLater()
    app.processEvents()


def _stored() -> dict:
    return json.loads(Path(config.CONFIG_PATH).read_text())


# -- Record and Pause ---------------------------------------------------------------------
def test_idle_record_on_pause_off(make):
    _, page, _ = make()
    assert page.btn_rec.isEnabled() and page.btn_rec.text() == "Record"
    assert not page.btn_pause.isEnabled() and page.btn_pause.text() == "Pause"
    assert not page.btn_stop.isEnabled()


def test_record_then_pause_resume(make):
    _, page, _ = make()
    page.btn_rec.click()
    assert page.tape.active and page.tape.started == 1
    assert not page.btn_rec.isEnabled()          # Record never turns into Pause
    assert page.btn_rec.text() == "Record"
    assert page.btn_pause.isEnabled() and page.btn_pause.text() == "Pause"
    assert page.btn_stop.isEnabled()

    page.btn_pause.click()
    assert page.tape.paused
    assert page.btn_pause.text() == "Resume" and page.btn_pause.isEnabled()
    assert "Carry on" in page.btn_pause.toolTip()
    assert not page.btn_rec.isEnabled()

    page.btn_pause.click()
    assert not page.tape.paused and page.btn_pause.text() == "Pause"

    page._record()                               # a second Record does nothing
    assert page.tape.started == 1


def test_stop_disables_pause(make):
    _, page, _ = make()
    page.btn_rec.click()
    page.btn_pause.click()
    page.btn_stop.click()
    assert not page.tape.active
    assert not page.btn_pause.isEnabled() and page.btn_pause.text() == "Pause"
    assert page.btn_rec.isEnabled()


def test_record_refused_while_dictating(make):
    _, page, _ = make()
    page.ctl.state = "recording"
    page.btn_rec.click()
    assert not page.tape.active and not page.btn_pause.isEnabled()


# -- Levels panel -------------------------------------------------------------------------
def test_levels_docked_by_default(make):
    _, page, cfg = make()
    assert cfg["tm_levels"] == "docked"
    assert not page.levels.isVisible() and not page.meter_box.isVisible()
    assert not page.btn_levels.isChecked()
    assert page._float is None


def test_old_show_meter_is_dropped_and_docked(make):
    _, page, cfg = make({"tm_show_meter": True, "feedback": "off", "send_chord": "enter",
                         "clear_each_take": False})
    assert cfg["tm_levels"] == "docked" and "tm_show_meter" not in cfg
    assert "tm_show_meter" not in _stored()
    assert not page.levels.isVisible()


def test_docked_keeps_the_gain(make):
    _, page, cfg = make({"tm_gain_db": 6, "feedback": "off", "send_chord": "enter",
                         "clear_each_take": False})
    assert not page.levels.isVisible()
    assert page.gain.value() == 6
    page.tape = FakeTape()
    page._on_gain(page.gain.value())
    assert page.tape.gain_db == 6.0


def test_shown_then_floating_then_closed(make):
    host, page, cfg = make()
    page.btn_levels.click()
    assert cfg["tm_levels"] == "shown" and _stored()["tm_levels"] == "shown"
    assert page.levels.isVisible() and page.levels.window() is host
    assert page.btn_undock.text() == "Undock"

    page.btn_undock.click()                      # pop out
    app.processEvents()
    assert cfg["tm_levels"] == "floating"
    assert page._float is not None and page._float.isVisible()
    assert page.levels.window() is page._float and page.levels.isVisible()
    assert page.btn_undock.text() == "Dock" and page.btn_levels.isChecked()
    gain = page.gain                             # the same widgets, moved, not copied
    page.gain.setValue(3)
    assert cfg["tm_gain_db"] == 3

    page.btn_undock.click()                      # Dock: back in the card
    assert cfg["tm_levels"] == "shown" and page.levels.window() is host
    assert not page._float.isVisible() and page.gain is gain

    page.btn_undock.click()
    page._float.close()                          # closing the window docks (hides) it
    app.processEvents()
    assert cfg["tm_levels"] == "docked" and _stored()["tm_levels"] == "docked"
    assert page.levels.window() is host and not page.levels.isVisible()
    assert not page.btn_levels.isChecked()


def test_levels_button_hides_a_floating_panel(make):
    _, page, cfg = make()
    page._set_levels("floating")
    assert page._float.isVisible()
    page.btn_levels.click()
    assert cfg["tm_levels"] == "docked" and not page._float.isVisible()
    assert not page.levels.isVisible()


def test_floating_is_restored_on_start(make):
    host, page, _ = make({"tm_levels": "floating", "feedback": "off", "send_chord": "enter",
                          "clear_each_take": False})
    app.processEvents()
    assert page._float is not None and page._float.isVisible()
    host.hide()                                  # main window to the tray: the panel goes too
    app.processEvents()
    app.processEvents()
    assert not page._float.isVisible()
    host.show()
    app.processEvents()
    app.processEvents()
    assert page._float.isVisible()


def test_unknown_levels_value_docks(make):
    _, page, _ = make({"tm_levels": "sideways", "feedback": "off", "send_chord": "enter",
                       "clear_each_take": False})
    assert page._levels_state == "docked" and not page.levels.isVisible()


def test_meter_polls_only_while_visible(make):
    _, page, _ = make()
    calls = []
    page.meter.set_source = lambda rec: calls.append(rec)
    page.btn_rec.click()
    page._tick()
    assert calls == []                           # docked: the recorder is not read
    page._set_levels("shown")
    page._tick()
    assert calls and calls[-1] is page.tape
