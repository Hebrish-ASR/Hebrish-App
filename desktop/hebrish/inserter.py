"""Put the transcript where the cursor is: clipboard, then a paste chord.

Paste rather than typing key by key: typed keys are turned into characters by the
active layout, so with a Hebrew layout selected "pensia" would come out as Hebrew
letters. A Ctrl+V works regardless of layout.
"""

import sys

_ALIASES = {"ctrl": "LEFTCTRL", "control": "LEFTCTRL", "shift": "LEFTSHIFT", "alt": "LEFTALT",
            "super": "LEFTMETA", "meta": "LEFTMETA", "win": "LEFTMETA", "cmd": "LEFTMETA"}


def chord_names(chord: str) -> list[str]:
    """'ctrl+shift+v' -> ['KEY_LEFTCTRL', 'KEY_LEFTSHIFT', 'KEY_V'] (evdev-style names)."""
    parts = [p for p in chord.lower().replace(" ", "").split("+") if p]
    if not parts:
        raise ValueError("Empty paste shortcut")
    return [f"KEY_{_ALIASES.get(p, p.upper())}" for p in parts]


def make_inserter():
    if sys.platform == "win32":
        from .inserter_win import WindowsInserter
        return WindowsInserter()
    from .inserter_linux import LinuxInserter
    return LinuxInserter()


def parse_chord(chord: str):
    """Validate a paste shortcut for this OS; raises ValueError."""
    if sys.platform == "win32":
        from .inserter_win import parse_chord as p
    else:
        from .inserter_linux import parse_chord as p
    return p(chord)


def copy_to_clipboard(text: str):
    if sys.platform == "win32":
        from .inserter_win import copy_to_clipboard as c
    else:
        from .inserter_linux import copy_to_clipboard as c
    c(text)
