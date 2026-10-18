"""Global hotkey: one state machine, fed by a per-OS key source.

Key names are evdev-style on every OS ("KEY_F13", "KEY_RIGHTCTRL"), so a config file
means the same key on Linux and Windows.

Modes:
  hold    press = start, release = stop
  toggle  press = start, next press = stop            ("tap, tap")
  hybrid  a short tap latches like toggle; holding past hybrid_hold_ms is push-to-talk
"""

import sys
import time

MODIFIERS = {"KEY_LEFTCTRL", "KEY_RIGHTCTRL", "KEY_LEFTSHIFT", "KEY_RIGHTSHIFT",
             "KEY_LEFTALT", "KEY_RIGHTALT", "KEY_LEFTMETA", "KEY_RIGHTMETA"}


def pretty(name: str) -> str:
    """KEY_RIGHTCTRL -> Right Ctrl, KEY_F13 -> F13."""
    n = name.removeprefix("KEY_")
    for side in ("LEFT", "RIGHT"):
        if n.startswith(side) and len(n) > len(side):
            return f"{side.title()} {n[len(side):].title().replace('Meta', 'Super')}"
    return n if len(n) <= 3 else n.title()


class HotkeyMachine:
    """Calls start() / stop() / cancel(); is_recording() is polled. Subclasses call
    self.key(name, down) from their own thread and implement run()."""

    def __init__(self, config, start, stop, cancel, is_recording):
        self._cfg = config
        self._start, self._stop, self._cancel = start, stop, cancel
        self._is_recording = is_recording
        self._capture = None
        self._down_at = None
        self._started_this_press = False
        self._chorded = False
        self.problem = ""               # shown in the window when the source can't run

    def capture_next_key(self, callback):
        """Hand the next key press (any key) to callback(name) instead of acting on it."""
        self._capture = callback

    def key(self, name: str, down: bool):
        if self._capture and down:
            cb, self._capture = self._capture, None
            cb(name)
            return
        hot = self._cfg["hotkey"]
        if name != hot:
            if down and self._down_at is not None and hot in MODIFIERS:
                self._chorded = True              # Right-Ctrl+C is a shortcut, not dictation
                if self._started_this_press:
                    self._started_this_press = False
                    self._cancel()
            return

        mode = self._cfg["mode"]
        if down:
            if self._down_at is not None:         # Windows autorepeat arrives as more downs
                return
            self._down_at = time.monotonic()
            self._chorded = False
            self._started_this_press = False
            if mode != "hold" and self._is_recording():
                self._stop()
            else:
                self._started_this_press = True
                self._start()
        else:
            held_ms = (time.monotonic() - (self._down_at or time.monotonic())) * 1000
            self._down_at = None
            if self._chorded or not self._started_this_press:
                return
            if mode == "hold" or (mode == "hybrid" and held_ms >= self._cfg["hybrid_hold_ms"]):
                self._stop()


def make_listener(*args):
    if sys.platform == "win32":
        from .hotkey_win import WindowsHotkeys
        return WindowsHotkeys(*args)
    from .hotkey_evdev import EvdevHotkeys
    return EvdevHotkeys(*args)
