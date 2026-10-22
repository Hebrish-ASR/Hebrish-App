"""Global hotkeys: one state machine, fed by a per-OS key source.

Key names are evdev-style on every OS ("KEY_F13", "KEY_RIGHTCTRL"), so a config file
means the same key on Linux and Windows.

Two keys, either may be "" (off):
  hotkey      toggle: press = start, next press = stop ("tap, tap"). With hold_to_talk,
              holding it past hybrid_hold_ms is push-to-talk instead (release = stop).
  ptt_hotkey  push-to-talk only: press = start, release = stop.
While one hotkey is held the other is ignored. Up to 0.2.x there was one key and a `mode`;
config.upgrade() maps old files.

Action keys (0.4.0), each "" = off, for a macropad or pedals: key_start, key_stop, key_pause
(pause / resume), key_retake, key_discard. They act on press, independently of the two above.
key_send (0.7.0) is Stop and send: stop, insert the last text, then press `send_chord` (Enter by
default), so a chat box is submitted only once the whole take is in it.

Built in (0.5.0, both on by default): Esc while a take is recording discards it
(`escape_discards`; the Esc still reaches the focused app, key sources never grab), and a
double tap of the toggle key while recording is Retake (`double_tap_retake`): the tap that
would stop the take waits `double_tap_ms` for a second press first, so stopping by tap is
that much later. Holding the key (push-to-talk) is unaffected.
"""

import sys
import threading
import time

MODIFIERS = {"KEY_LEFTCTRL", "KEY_RIGHTCTRL", "KEY_LEFTSHIFT", "KEY_RIGHTSHIFT",
             "KEY_LEFTALT", "KEY_RIGHTALT", "KEY_LEFTMETA", "KEY_RIGHTMETA"}
ACTIONS = [("start", "Start"), ("stop", "Stop"), ("pause", "Pause / resume"),
           ("retake", "Retake"), ("discard", "Discard"), ("send", "Stop and send")]
SLOTS = ["hotkey", "ptt_hotkey"] + [f"key_{a}" for a, _ in ACTIONS]   # one key per slot, at most


def pretty(name: str) -> str:
    """KEY_RIGHTCTRL -> Right Ctrl, KEY_F13 -> F13, "" -> Not set."""
    if not name:
        return "Not set"
    n = name.removeprefix("KEY_")
    for side in ("LEFT", "RIGHT"):
        if n.startswith(side) and len(n) > len(side):
            return f"{side.title()} {n[len(side):].title().replace('Meta', 'Super')}"
    return n if len(n) <= 3 else n.title()


def describe(cfg) -> str:
    """One line for the Dictate tab: how the configured keys work."""
    toggle, ptt = cfg["hotkey"], cfg["ptt_hotkey"]
    parts = []
    if toggle:
        parts.append(f"Tap {pretty(toggle)} to start and stop"
                     + (", or hold it while you talk" if cfg["hold_to_talk"] else ""))
    if ptt:
        parts.append(f"Hold {pretty(ptt)} while you talk")
    keys = [f"{label} {pretty(cfg[f'key_{a}'])}" for a, label in ACTIONS if cfg[f"key_{a}"]]
    if toggle and cfg.get("double_tap_retake"):
        parts.append(f"Double-tap {pretty(toggle)} to start again")
    if cfg.get("escape_discards"):
        parts.append("Esc discards")
    if keys:
        parts.append("Keys: " + ", ".join(keys))
    return ". ".join(parts) + "." if parts else "No hotkey set: use the button, the tray or the overlay."


class HotkeyMachine:
    """Calls start() / stop() / cancel() / action(name); is_recording() is polled. Subclasses
    call self.key(name, down) from their own thread and implement run()."""

    def __init__(self, config, start, stop, cancel, is_recording, action=None):
        self._cfg = config
        self._start, self._stop, self._cancel = start, stop, cancel
        self._action = action
        self._is_recording = is_recording
        self._capture = None
        self._held = None                 # the hotkey currently down, if any
        self._down_at = 0.0
        self._started_this_press = False
        self._chorded = False
        self._pending_stop: threading.Timer | None = None   # a tap's stop, waiting for a double tap
        self.problem = ""               # shown in the window when the source can't run

    def capture_next_key(self, callback):
        """Hand the next key press (any key) to callback(name) instead of acting on it."""
        self._capture = callback

    def key(self, name: str, down: bool):
        if self._capture and down:
            cb, self._capture = self._capture, None
            cb(name)
            return
        action = next((a for a, _ in ACTIONS if name and self._cfg.get(f"key_{a}") == name), None)
        if action:
            if down and self._action:
                self._action(action)
            return
        toggle, ptt = self._cfg["hotkey"], self._cfg["ptt_hotkey"]
        if (name == "KEY_ESC" and down and self._cfg.get("escape_discards") and name not in (toggle, ptt)
                and self._is_recording()):
            self._drop_pending()
            self._held = None
            self._cancel()
            return
        if not name or name not in (toggle, ptt):
            if down and self._held in MODIFIERS:
                self._chorded = True              # Right-Ctrl+C is a shortcut, not dictation
                if self._started_this_press:
                    self._started_this_press = False
                    self._cancel()
            return

        if down:
            if self._held is not None:            # autorepeat (Windows), or the other hotkey
                return
            self._held, self._down_at = name, time.monotonic()
            self._chorded = False
            self._started_this_press = False
            if self._pending_stop is not None and name == toggle:     # second tap: retake
                self._drop_pending()
                self._held = None                 # its release must not stop the new take
                (self._action or (lambda a: None))("retake")
                return
            if self._is_recording():
                if name == toggle:                # the PTT key never stops a toggled take
                    if self._cfg.get("double_tap_retake") and self._action:
                        self._pending_stop = threading.Timer(
                            self._cfg.get("double_tap_ms", 300) / 1000, self._fire_stop)
                        self._pending_stop.daemon = True
                        self._pending_stop.start()
                    else:
                        self._stop()
            else:
                self._started_this_press = True
                self._start()
        elif name == self._held:
            held_ms = (time.monotonic() - self._down_at) * 1000
            self._held = None
            if self._chorded or not self._started_this_press:
                return
            if name != toggle or (self._cfg["hold_to_talk"] and held_ms >= self._cfg["hybrid_hold_ms"]):
                self._stop()

    def _drop_pending(self):
        t, self._pending_stop = self._pending_stop, None
        if t:
            t.cancel()

    def _fire_stop(self):
        if self._pending_stop is not None:
            self._pending_stop = None
            if self._is_recording():
                self._stop()


def make_listener(*args):
    if sys.platform == "win32":
        from .hotkey_win import WindowsHotkeys
        return WindowsHotkeys(*args)
    from .hotkey_evdev import EvdevHotkeys
    return EvdevHotkeys(*args)
