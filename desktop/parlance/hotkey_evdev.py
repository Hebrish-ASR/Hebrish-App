"""Linux key source: read /dev/input directly (evdev).

evdev rather than a desktop shortcut API because it is the one route that works on
every Wayland compositor *and* reports key release, which push-to-talk needs. It
needs read access to /dev/input/event* (the `input` group). Reading is non-exclusive:
the key still reaches other apps, so pick a key nothing else uses (F13-F24, a pedal).
"""

import glob
import selectors
import threading
import time

import evdev
from evdev import ecodes

from .hotkey import HotkeyMachine

OWN_DEVICE_NAME = "parlance-keyboard"     # our uinput paster; never listen to it


def key_name(code: int) -> str:
    n = ecodes.KEY.get(code, f"KEY_{code}")
    return n[0] if isinstance(n, list) else n


def _is_key(code: int) -> bool:
    return not (ecodes.BTN_MISC <= code < ecodes.KEY_OK)   # skip mouse/joystick buttons


class EvdevHotkeys(HotkeyMachine):
    RESCAN_S = 3.0

    def __init__(self, *args):
        super().__init__(*args)
        self._sel = selectors.DefaultSelector()
        self._devices: dict[str, evdev.InputDevice] = {}

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="hotkey").start()

    def _rescan(self):
        paths = set(evdev.list_devices())
        if not paths and not self._devices and glob.glob("/dev/input/event*"):
            # list_devices() silently skips nodes it cannot open
            self.problem = ("Can't read /dev/input, so the hotkey is off. Run "
                            "`sudo usermod -aG input $USER` and log in again. Until then use "
                            "the button, the tray, or `parlance --toggle`.")
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

    def _run(self):
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
                        if ev.type == ecodes.EV_KEY and ev.value != 2 and _is_key(ev.code):
                            self.key(key_name(ev.code), ev.value == 1)
                except OSError:            # unplugged
                    self._drop(dev.path)
