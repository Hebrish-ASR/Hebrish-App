"""Start at login: an XDG autostart entry on Linux, the HKCU Run key on Windows."""

import os
import shutil
import sys
from pathlib import Path

from .config import APP_NAME

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_DESKTOP = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "autostart" / "parlance.desktop"


def _command() -> str:
    if getattr(sys, "frozen", False):                      # PyInstaller build
        return f'"{sys.executable}" --hidden'
    exe = shutil.which("parlance")
    if exe:
        return f"{exe} --hidden"
    py = sys.executable.replace("python.exe", "pythonw.exe")
    return f'"{py}" -m parlance --hidden'


def enabled() -> bool:
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
                winreg.QueryValueEx(k, APP_NAME)
            return True
        except OSError:
            return False
    return _DESKTOP.exists()


def set_enabled(on: bool):
    if sys.platform == "win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except OSError:
                    pass
        return
    if not on:
        _DESKTOP.unlink(missing_ok=True)
        return
    _DESKTOP.parent.mkdir(parents=True, exist_ok=True)
    _DESKTOP.write_text("[Desktop Entry]\nType=Application\n"
                        f"Name={APP_NAME}\nExec={_command()}\nIcon=parlance\n"
                        "X-GNOME-Autostart-enabled=true\n")
