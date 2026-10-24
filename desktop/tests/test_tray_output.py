"""Tray menu's Output submenu: output checks (independent since 1.000) and the paste shortcut
radio follow the config, picks write it and resync the window. Off-screen, with a stub controller; skipped where PySide6 isn't installed (Linux CI)."""

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

    def __init__(self, cursor=True, clipboard=False, window=False, chord="ctrl+v"):
        self.cfg = Cfg(out_cursor=cursor, out_clipboard=clipboard, out_window=window, paste_chord=chord)
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
    ctl = Ctl(cursor=False, clipboard=True, chord="ctrl+shift+v")
    menu_for(ctl)
    assert checked(ctl._output_acts) == ["out_clipboard"]
    assert checked(ctl._chord_acts) == ["ctrl+shift+v"]
    assert not ctl._chord_acts["ctrl+v"].isEnabled()      # no paste, so no paste shortcut


def test_custom_chord_checks_neither():
    ctl = Ctl(chord="shift+insert")
    menu_for(ctl)
    assert checked(ctl._chord_acts) == []


def test_outputs_combine():
    ctl = Ctl()
    menu_for(ctl)
    ctl._output_acts["out_window"].trigger()
    ctl._chord_acts["ctrl+shift+v"].trigger()
    assert ctl.cfg["out_cursor"] and ctl.cfg["out_window"] and ctl.cfg["paste_chord"] == "ctrl+shift+v"
    assert ctl.win.synced == 2
    ctl._sync_output_menu()
    assert checked(ctl._output_acts) == ["out_cursor", "out_window"]     # not exclusive


def test_last_output_stays_on():
    ctl = Ctl()
    menu_for(ctl)
    ctl._output_acts["out_cursor"].trigger()
    assert ctl.cfg["out_cursor"]
    ctl._sync_output_menu()
    assert checked(ctl._output_acts) == ["out_cursor"]
