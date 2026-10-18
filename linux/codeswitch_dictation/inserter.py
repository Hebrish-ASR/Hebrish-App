"""Put the transcript where the cursor is: clipboard, then a paste chord via uinput.

Paste rather than typing key by key: typed keycodes are turned into characters by the
active layout, so with a Hebrew layout selected "pensia" would come out as Hebrew
letters. A Ctrl+V keycode works regardless of layout.
"""

import os
import shutil
import subprocess
import time

from evdev import UInput, ecodes

from .hotkey import OWN_DEVICE_NAME

_ALIASES = {"ctrl": "KEY_LEFTCTRL", "shift": "KEY_LEFTSHIFT", "alt": "KEY_LEFTALT",
            "super": "KEY_LEFTMETA", "meta": "KEY_LEFTMETA", "insert": "KEY_INSERT"}


def parse_chord(chord: str) -> list[int]:
    codes = []
    for part in chord.lower().replace(" ", "").split("+"):
        name = _ALIASES.get(part, f"KEY_{part.upper()}")
        code = ecodes.ecodes.get(name)
        if not isinstance(code, int):
            raise ValueError(f"Unknown key in chord: {part!r}")
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


class Inserter:
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
