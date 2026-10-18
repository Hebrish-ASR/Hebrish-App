"""Windows paste: the clipboard (pyperclip, plain Win32 calls), then Ctrl+V via SendInput."""

import time

import pyperclip
from pynput.keyboard import Controller, Key, KeyCode

from .inserter import chord_names

_KEYS = {"KEY_LEFTCTRL": Key.ctrl_l, "KEY_LEFTSHIFT": Key.shift_l, "KEY_LEFTALT": Key.alt_l,
         "KEY_LEFTMETA": Key.cmd, "KEY_INSERT": Key.insert}


def parse_chord(chord: str) -> list:
    keys = []
    for name in chord_names(chord):
        k = name.removeprefix("KEY_")
        if name in _KEYS:
            keys.append(_KEYS[name])
        elif len(k) == 1:
            keys.append(KeyCode.from_char(k.lower()))
        elif hasattr(Key, k.lower()):
            keys.append(getattr(Key, k.lower()))
        else:
            raise ValueError(f"Unknown key in paste shortcut: {k.lower()!r}")
    return keys


def copy_to_clipboard(text: str):
    pyperclip.copy(text)


class WindowsInserter:
    error = ""

    def __init__(self):
        self._kb = Controller()

    def insert(self, text: str, method: str, chord: str):
        copy_to_clipboard(text)
        if method != "paste":
            return
        time.sleep(0.08)
        keys = parse_chord(chord)
        for k in keys:
            self._kb.press(k)
        for k in reversed(keys):
            self._kb.release(k)
