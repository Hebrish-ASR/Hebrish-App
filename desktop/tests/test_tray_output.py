"""Tray menu's Output submenu: radio checks follow the config, picks write it and resync the
window. Off-screen, with a stub controller; skipped where PySide6 isn't installed (Linux CI)."""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from hebrish.ui.app import Controller  # noqa: E402

app = QApplication.instance() or QApplication([])


class Win:
    synced = 0

    def sync_output(self):
        self.synced += 1


class Ctl:
    _build_output_menu = Controller._build_output_menu
    _sync_output_menu = Controller._sync_output_menu
    _tray_output = Controller._tray_output
    _tray_chord = Controller._tray_chord

    def __init__(self, insert="paste", chord="ctrl+v"):
        self.cfg = Cfg(insert=insert, paste_chord=chord)
        self.win = Win()


class Cfg(dict):
    def set(self, k, v):
        self[k] = v


def menu_for(ctl):
    m = ctl.menu = QMenu()          # the tray menu owns it in the app; keep it alive here
    ctl._build_output_menu(m)
    ctl._sync_output_menu()
    return m


def checked(acts):
    return [v for v, a in acts.items() if a.isChecked()]


def test_checks_follow_config():
    ctl = Ctl("clipboard", "ctrl+shift+v")
    menu_for(ctl)
    assert checked(ctl._output_acts) == ["clipboard"]
    assert checked(ctl._chord_acts) == ["ctrl+shift+v"]
    assert not ctl._chord_acts["ctrl+v"].isEnabled()      # no paste, so no paste shortcut


def test_custom_chord_checks_neither():
    ctl = Ctl(chord="shift+insert")
    menu_for(ctl)
    assert checked(ctl._chord_acts) == []


def test_pick_writes_config_and_syncs_window():
    ctl = Ctl()
    menu_for(ctl)
    ctl._output_acts["app"].trigger()
    ctl._chord_acts["ctrl+shift+v"].trigger()
    assert ctl.cfg["insert"] == "app" and ctl.cfg["paste_chord"] == "ctrl+shift+v"
    assert ctl.win.synced == 2
    assert checked(ctl._output_acts) == ["app"]          # exclusive group
