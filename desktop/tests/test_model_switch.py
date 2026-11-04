"""The tray's Active model and the model action keys (Daniel, 2026-11-05)."""

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from hebrish import model_store  # noqa: E402
from hebrish.config import DEFAULTS  # noqa: E402
from hebrish.hotkey import ACTIONS, SLOTS  # noqa: E402
from hebrish.ui.app import QUICK_MODELS, Controller  # noqa: E402


def _ctl(monkeypatch, cur, installed):
    monkeypatch.setattr(model_store, "current_id", lambda: cur[0])
    monkeypatch.setattr(model_store, "active", lambda mid=None: ("x", "y") if mid in installed else None)
    said, used = [], []
    ctl = SimpleNamespace(notify=lambda title, body="": said.append(title),
                          use_model=lambda mid: (used.append(mid), cur.__setitem__(0, mid)))
    ctl.switch_model = lambda mid: Controller.switch_model(ctl, mid)
    return ctl, said, used


def test_action_keys_exist_and_default_to_unset():
    for a, label in (("model_sabich", "Select Sabich"), ("model_shakshuka", "Select Shakshuka"),
                     ("model_toggle", "Toggle model")):
        assert (a, label) in ACTIONS and f"key_{a}" in SLOTS and DEFAULTS[f"key_{a}"] == ""


def test_quick_models_are_in_the_catalogue():
    assert all(model_store.get_model(m) for m in QUICK_MODELS)
    assert model_store.get_model(QUICK_MODELS[0]).name == "Sabich"


def test_switch_says_what_happened(monkeypatch):
    ctl, said, used = _ctl(monkeypatch, ["sabich-rolling"], set(QUICK_MODELS))
    ctl.switch_model("shakshuka")
    assert used == ["shakshuka"] and said == ["Now using Shakshuka"]


def test_switch_to_the_current_model_changes_nothing(monkeypatch):
    ctl, said, used = _ctl(monkeypatch, ["shakshuka"], set(QUICK_MODELS))
    ctl.switch_model("shakshuka")
    assert not used and said == ["Already using Shakshuka"]


def test_a_model_not_downloaded_is_not_selected(monkeypatch):
    ctl, said, used = _ctl(monkeypatch, ["sabich-rolling"], {"sabich-rolling"})
    ctl.switch_model("shakshuka")
    assert not used and said == ["Shakshuka isn't downloaded"]


def test_toggle_goes_both_ways_and_home_from_anything_else(monkeypatch):
    cur = ["sabich-rolling"]
    ctl, _, used = _ctl(monkeypatch, cur, set(QUICK_MODELS) | {"stock"})
    Controller.toggle_model(ctl)
    Controller.toggle_model(ctl)
    assert used == ["shakshuka", "sabich-rolling"]
    cur[0] = "stock"
    Controller.toggle_model(ctl)
    assert used[-1] == "shakshuka"


def test_tray_menu_ticks_the_active_model_and_greys_a_missing_one(monkeypatch):
    from PySide6.QtWidgets import QApplication, QMenu
    app = QApplication.instance() or QApplication([])  # noqa: F841
    ctl, said, used = _ctl(monkeypatch, ["sabich-rolling"], {"sabich-rolling"})
    menu = QMenu()
    Controller._build_model_menu(ctl, menu)
    sabich, shakshuka = menu.actions()
    assert sabich.text() == "Sabich" and sabich.isChecked() and sabich.isEnabled()
    assert shakshuka.text() == "Shakshuka (not downloaded)" and not shakshuka.isEnabled()
    monkeypatch.setattr(model_store, "active", lambda mid=None: ("x", "y"))
    menu.aboutToShow.emit()
    assert shakshuka.text() == "Shakshuka" and shakshuka.isEnabled()
    shakshuka.trigger()
    assert used == ["shakshuka"]
    menu.aboutToShow.emit()
    assert shakshuka.isChecked() and not sabich.isChecked()


def test_tray_menu_shows_the_running_version():
    from PySide6.QtWidgets import QApplication, QMenu
    from hebrish import __version__
    app = QApplication.instance() or QApplication([])  # noqa: F841
    menu = QMenu()
    Controller._add_version_item(None, menu)
    (item,) = menu.actions()
    assert item.text() == f"Hebrish {__version__}" and not item.isEnabled()
