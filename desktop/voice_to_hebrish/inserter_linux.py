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


def copy_to_clipboard(text: str):
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        cmd = ["wl-copy"]
    elif shutil.which("xclip"):
        cmd = ["xclip", "-selection", "clipboard"]
    else:
        raise RuntimeError("Install wl-clipboard (Wayland) or xclip (X11)")
    subprocess.run(cmd, input=text.encode(), check=True, timeout=5)


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
