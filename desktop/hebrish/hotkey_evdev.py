"""Linux key source: read /dev/input directly (evdev).

evdev rather than a desktop shortcut API because it is the one route that works on
every Wayland compositor *and* reports key release, which push-to-talk needs. It
needs read access to /dev/input/event* (the `input` group). Reading is non-exclusive:
the key still reaches other apps, so pick a key nothing else uses (F13-F24, a pedal).

The one exception is the Enter guard's opt-in hold (hotkey.HotkeyMachine.send_key): while a
take's last words are pending, keyboards with an Enter key are grabbed (EVIOCGRAB) and every
event except the send key is forwarded at once through a passthrough uinput device, so typing
still works and only the Enter waits. A keyboard with a key down is not grabbed (its release
would go astray), and keys forwarded but still down are released through the passthrough before
the grab ends. GRAB_MAX_S caps a grab even if the controller never ends it.
"""

import glob
import selectors
import threading
import time

import evdev
from evdev import UInput, ecodes
from evdev.uinput import UInputError

from .hotkey import HotkeyMachine

OWN_DEVICE_NAME = "hebrish-keyboard"     # our uinput paster; never listen to it
# Paste devices never listened to: ours, and Parlance's (a separate app that can run alongside
# and has the same hotkey code), so neither app reacts to the other's paste chord.
PASSTHROUGH_NAME = "hebrish-passthrough"   # forwards keys from grabbed keyboards (Enter hold)
IGNORED_DEVICES = (OWN_DEVICE_NAME, PASSTHROUGH_NAME, "parlance-keyboard")
GRAB_MAX_S = 5.0


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
        self._lock = threading.RLock()
        self._grabbed: set[str] = set()       # device paths grabbed for the Enter hold
        self._forwarded: set[int] = set()     # key codes the passthrough holds down
        self._pass: UInput | None = None
        self._grab_timer: threading.Timer | None = None

    def hold_send(self, on: bool) -> bool:
        with self._lock:
            if on and not self._grabbed:
                try:
                    self._pass = self._pass or UInput(
                        {ecodes.EV_KEY: [c for c in ecodes.KEY if c < ecodes.BTN_MISC]}, name=PASSTHROUGH_NAME)
                except (OSError, UInputError):              # UInputError: no /dev/uinput at all
                    return super().hold_send(False)       # no uinput: guard falls back to late words
                for path, dev in self._devices.items():
                    keys = dev.capabilities().get(ecodes.EV_KEY, [])
                    if ecodes.KEY_ENTER not in keys and ecodes.KEY_KPENTER not in keys:
                        continue
                    try:
                        if dev.active_keys():
                            continue
                        dev.grab()
                        self._grabbed.add(path)
                    except OSError:
                        pass
                if self._grabbed:
                    self._grab_timer = threading.Timer(GRAB_MAX_S, lambda: self.hold_send(False))
                    self._grab_timer.daemon = True
                    self._grab_timer.start()
                return super().hold_send(bool(self._grabbed))
            if not on:
                self._ungrab()
                return super().hold_send(False)
            return self.holding

    def _ungrab(self):
        if self._grab_timer:
            self._grab_timer.cancel()
            self._grab_timer = None
        if self._pass and self._forwarded:
            for code in self._forwarded:
                self._pass.write(ecodes.EV_KEY, code, 0)
            self._pass.syn()
        self._forwarded.clear()
        for path in self._grabbed:
            dev = self._devices.get(path)
            if dev:
                try:
                    dev.ungrab()
                except OSError:
                    pass
        self._grabbed.clear()

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="hotkey").start()

    def _rescan(self):
        paths = set(evdev.list_devices())
        if not paths and not self._devices and glob.glob("/dev/input/event*"):
            # list_devices() silently skips nodes it cannot open
            self.problem = ("Can't read /dev/input, so the hotkey is off. Run "
                            "`sudo usermod -aG input $USER` and log in again. Until then use "
                            "the button, the tray, or `hebrish --toggle`.")
        for path in list(self._devices):
            if path not in paths:
                self._drop(path)
        for path in paths - self._devices.keys():
            try:
                dev = evdev.InputDevice(path)
            except OSError:
                continue
            keys = dev.capabilities().get(ecodes.EV_KEY, [])
            if dev.name in IGNORED_DEVICES or not any(_is_key(k) for k in keys):
                dev.close()
                continue
            self._devices[path] = dev
            self._sel.register(dev, selectors.EVENT_READ)

    def _drop(self, path):
        self._grabbed.discard(path)
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
                        if ev.type != ecodes.EV_KEY or not _is_key(ev.code):
                            continue
                        name = key_name(ev.code)
                        # send_key may call the controller, which may call hold_send: not under _lock
                        swallow = self.send_key(name, ev.value != 0, dev.path in self._grabbed)
                        with self._lock:
                            if dev.path in self._grabbed and not swallow and self._pass:
                                self._pass.write(ecodes.EV_KEY, ev.code, ev.value)
                                self._pass.syn()
                                (self._forwarded.add if ev.value else self._forwarded.discard)(ev.code)
                        if ev.value != 2:
                            self.key(name, ev.value == 1)
                except OSError:            # unplugged
                    self._drop(dev.path)
