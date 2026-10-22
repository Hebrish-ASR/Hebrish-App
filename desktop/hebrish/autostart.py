"""Start at login: an XDG autostart entry on Linux, the HKCU Run key on Windows.

The entry stores the launch command as it was when it was turned on. refresh() rewrites it at
every start, so it follows the app when that changes: a portable Windows zip unzipped to a new
folder for a new version, or a switch between a source checkout and the .deb."""

import os
import shutil
import sys
from pathlib import Path

from .config import APP_NAME, AUTOSTART_KEY

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_DESKTOP = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "autostart" / "hebrish.desktop"


def _command() -> str:
    if getattr(sys, "frozen", False):                      # PyInstaller build
        return f'"{sys.executable}" --hidden'
    exe = shutil.which("hebrish")
    if exe:
        return f'"{exe}" --hidden'          # quoted: the path may contain a space
    py = sys.executable.replace("python.exe", "pythonw.exe")
    return f'"{py}" -m hebrish --hidden'


def enabled() -> bool:
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
                winreg.QueryValueEx(k, AUTOSTART_KEY)
            return True
        except OSError:
            return False
    return _DESKTOP.exists()


def _entry() -> str:
    return ("[Desktop Entry]\nType=Application\n"
            f"Name={APP_NAME}\nComment=Start {APP_NAME} in the tray\n"
            f"Exec={_command()}\nIcon=hebrish\nTerminal=false\n"
            "X-GNOME-Autostart-enabled=true\n")


def refresh():
    """If start at login is on, point it at this copy of the app."""
    if enabled():
        set_enabled(True)


def set_enabled(on: bool):
    if sys.platform == "win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, AUTOSTART_KEY, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(k, AUTOSTART_KEY)
                except OSError:
                    pass
        return
    if not on:
        _DESKTOP.unlink(missing_ok=True)
        return
    _DESKTOP.parent.mkdir(parents=True, exist_ok=True)
    if not _DESKTOP.exists() or _DESKTOP.read_text() != _entry():
        _DESKTOP.write_text(_entry())

