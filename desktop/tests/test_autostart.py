"""Start at login on Linux: the XDG entry (conftest.py points XDG_CONFIG_HOME at a temp dir)."""

import sys

import pytest

from hebrish import autostart

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="XDG entry is Linux only")


def test_on_off():
    autostart.set_enabled(True)
    assert autostart.enabled()
    text = autostart._DESKTOP.read_text()
    assert "Exec=" in text and "--hidden" in text and "Terminal=false" in text
    autostart.set_enabled(False)
    assert not autostart.enabled()


def test_refresh_follows_the_app():
    autostart.set_enabled(True)
    autostart._DESKTOP.write_text("[Desktop Entry]\nExec=/old/place/hebrish --hidden\n")
    autostart.refresh()
    assert "/old/place" not in autostart._DESKTOP.read_text()
    autostart.set_enabled(False)


def test_refresh_leaves_it_off():
    autostart.set_enabled(False)
    autostart.refresh()
    assert not autostart.enabled()
