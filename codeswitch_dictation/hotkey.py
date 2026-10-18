"""Global hotkey read straight from /dev/input (evdev).

evdev rather than a desktop shortcut API because it is the one route that works on
every Wayland compositor *and* reports key release, which push-to-talk needs. It
needs read access to /dev/input/event* (the `input` group). Reading is non-exclusive:
the key still reaches other apps, so pick a key nothing else uses (F13-F24, a pedal).

Modes:
  hold    press = start, release = stop
  toggle  press = start, next press = stop            ("tap, tap")
  hybrid  a short tap latches like toggle; holding past hybrid_hold_ms is push-to-talk
"""

import selectors
import threading
import time

import evdev
from evdev import ecodes

OWN_DEVICE_NAME = "codeswitch-dictation-keyboard"     # our uinput paster; never listen to it
MODIFIERS = {ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL, ecodes.KEY_LEFTSHIFT,
             ecodes.KEY_RIGHTSHIFT, ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT,
             ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA}


def key_code(name: str) -> int | None:
    code = ecodes.ecodes.get(name)
    return code if isinstance(code, int) else None


def key_name(code: int) -> str:
    n = ecodes.KEY.get(code, f"KEY_{code}")
    return n[0] if isinstance(n, list) else n


def _is_key(code: int) -> bool:
    return not (ecodes.BTN_MISC <= code < ecodes.KEY_OK)   # skip mouse/joystick buttons


class HotkeyListener(threading.Thread):
    """Calls start() / stop() / cancel() from this thread; is_recording() is polled."""

    RESCAN_S = 3.0

    def __init__(self, config, start, stop, cancel, is_recording, on_error=None):
        super().__init__(daemon=True, name="hotkey")
        self._cfg = config
        self._start, self._stop, self._cancel = start, stop, cancel
        self._is_recording = is_recording
        self._on_error = on_error
        self._sel = selectors.DefaultSelector()
        self._devices: dict[str, evdev.InputDevice] = {}
        self._capture = None
        self._down_at = None            # monotonic time the hotkey went down
        self._started_this_press = False
        self._chorded = False
        self.permission_denied = False

    def capture_next_key(self, callback):
        """Hand the next key press (any key) to callback(name) instead of acting on it."""
        self._capture = callback

    # -- devices ---------------------------------------------------------------
    def _rescan(self):
        paths = set(evdev.list_devices())
        if not paths and not self._devices:
            # list_devices() silently skips nodes it cannot open
            import glob
            self.permission_denied = bool(glob.glob("/dev/input/event*"))
        for path in list(self._devices):
            if path not in paths:
                self._drop(path)
        for path in paths - self._devices.keys():
            try:
                dev = evdev.InputDevice(path)
            except OSError:
                continue
            keys = dev.capabilities().get(ecodes.EV_KEY, [])
            if dev.name == OWN_DEVICE_NAME or not any(_is_key(k) for k in keys):
                dev.close()
                continue
            self._devices[path] = dev
            self._sel.register(dev, selectors.EVENT_READ)

    def _drop(self, path):
        dev = self._devices.pop(path, None)
        if dev:
            try:
                self._sel.unregister(dev)
                dev.close()
            except (KeyError, ValueError, OSError):
                pass

    # -- loop ------------------------------------------------------------------
    def run(self):
        last_scan = 0.0
        while True:
            now = time.monotonic()
            if now - last_scan > self.RESCAN_S:
                self._rescan()
                last_scan = now
            if not self._devices:
                time.sleep(self.RESCAN_S)
                continue
            for key, _ in self._sel.select(timeout=self.RESCAN_S):
                dev = key.fileobj
                try:
                    for ev in dev.read():
                        if ev.type == ecodes.EV_KEY:
                            self._on_key(ev.code, ev.value)
                except OSError:            # unplugged
                    self._drop(dev.path)

    def _on_key(self, code: int, value: int):
        if value == 2 or not _is_key(code):       # autorepeat
            return
        if self._capture and value == 1:
            cb, self._capture = self._capture, None
            cb(key_name(code))
            return
        hot = key_code(self._cfg["hotkey"])
        if code != hot:
            if value == 1 and self._down_at is not None and hot in MODIFIERS:
                self._chorded = True              # Right-Ctrl+C is a shortcut, not dictation
                if self._started_this_press:
                    self._started_this_press = False
                    self._cancel()
            return

        mode = self._cfg["mode"]
        if value == 1:
            self._down_at = time.monotonic()
            self._chorded = False
            self._started_this_press = False
            if mode == "hold":
                self._started_this_press = True
                self._start()
            elif self._is_recording():
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
