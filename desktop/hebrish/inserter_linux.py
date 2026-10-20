"""Linux paste: wl-copy (xclip on X11), then the chord through a uinput device."""

import os
import shutil
import subprocess
import time

from evdev import UInput, ecodes

from .hotkey_evdev import OWN_DEVICE_NAME
from .inserter import chord_names


def parse_chord(chord: str) -> list[int]:
    codes = []
    for name in chord_names(chord):
        code = ecodes.ecodes.get(name)
        if not isinstance(code, int):
            raise ValueError(f"Unknown key in paste shortcut: {name.removeprefix('KEY_').lower()!r}")
        codes.append(code)
    return codes


def clipboard_command() -> list[str]:
    """The tool that sets the clipboard while Hebrish is NOT the focused app (the dictation
    path: the text is pasted into another window).

    wl-copy needs the compositor's data-control protocol (wlr or ext) to do that. KWin,
    wlroots compositors and Hyprland have it; GNOME's Mutter does not, and there wl-copy
    falls back to mapping a surface to get keyboard focus, which can pull focus away from the
    window the Ctrl+V is meant for. So on GNOME Wayland the X11 CLIPBOARD selection is set with
    xclip instead (XWayland), and Mutter's selection bridge makes it the Wayland clipboard."""
    wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
    gnome = "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper().split(":")
    xclip = ["xclip", "-selection", "clipboard"] if shutil.which("xclip") and os.environ.get("DISPLAY") else None
    wl = ["wl-copy"] if wayland and shutil.which("wl-copy") else None
    for cmd in ((xclip, wl) if gnome else (wl, xclip)):
        if cmd:
            return cmd
    raise RuntimeError("Install wl-clipboard and xclip")


def copy_to_clipboard(text: str):
    subprocess.run(clipboard_command(), input=text.encode(), check=True, timeout=5)


class LinuxInserter:
    def __init__(self):
        self._ui = None
        self.error = ""
        try:
            keys = [c for c in ecodes.KEY.keys() if c < ecodes.BTN_MISC]
            self._ui = UInput({ecodes.EV_KEY: keys}, name=OWN_DEVICE_NAME)
        except OSError as e:
            self.error = f"Cannot open /dev/uinput ({e.strerror}); transcripts go to the clipboard only"

    def insert(self, text: str, method: str, chord: str):
        copy_to_clipboard(text)
        if method != "paste" or self._ui is None:
            return
        time.sleep(0.12)          # let the compositor see the new clipboard owner
        codes = parse_chord(chord)
        for c in codes:
            self._ui.write(ecodes.EV_KEY, c, 1)
        self._ui.syn()
        time.sleep(0.02)
        for c in reversed(codes):
            self._ui.write(ecodes.EV_KEY, c, 0)
        self._ui.syn()
