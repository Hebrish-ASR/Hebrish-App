"""Linux paste: wl-copy (xclip on X11), then the chord through a uinput device."""

import os
import shutil
import socket
import struct
import subprocess
import threading
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


def wayland_globals(timeout: float = 1.0) -> set[str]:
    """Interface names the compositor advertises (what `wayland-info` lists), read straight
    off the Wayland socket: wl_display.get_registry, then a sync, collecting
    wl_registry.global events until the sync's callback is done. Empty on any failure."""
    display = os.environ.get("WAYLAND_DISPLAY", "")
    path = display if display.startswith("/") else os.path.join(os.environ.get("XDG_RUNTIME_DIR", ""), display)
    names: set[str] = set()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(path)
            # object 1 = wl_display: get_registry (opcode 1) -> id 2, sync (opcode 0) -> id 3
            s.sendall(struct.pack("<IIi", 1, (12 << 16) | 1, 2) + struct.pack("<IIi", 1, (12 << 16) | 0, 3))
            buf = b""
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    return names
                buf += chunk
                while len(buf) >= 8:
                    obj, word = struct.unpack_from("<II", buf)
                    size, opcode = word >> 16, word & 0xFFFF
                    if len(buf) < size:
                        break
                    if obj == 3:                      # wl_callback.done: every global is in
                        return names
                    if obj == 2 and opcode == 0:      # wl_registry.global(name, interface, version)
                        n = struct.unpack_from("<I", buf, 12)[0]
                        names.add(buf[16:16 + n - 1].decode(errors="replace"))
                    buf = buf[size:]
    except OSError:
        return names


def clipboard_command() -> list[str]:
    """The tool that sets the clipboard while Hebrish is NOT the focused app (the dictation
    path: the text is pasted into another window).

    wl-copy can only do that through the compositor's data-control protocol, and the
    wl-clipboard in Ubuntu 26.04 (2.2.1) knows only the wlr one, zwlr_data_control_manager_v1.
    Without it, wl-copy maps a toplevel ("wl-clipboard") to get keyboard focus: the focused
    window loses focus for a moment on every paste, which shows as a title-bar flicker (KWin
    6.6, which offers only ext_data_control_manager_v1) and can pull focus away from the
    window the Ctrl+V is meant for (Mutter, which has neither). So wl-copy is used only where
    the compositor offers the wlr protocol (wlroots, Hyprland); elsewhere the X11 CLIPBOARD
    selection is set with xclip (XWayland), which never maps a window, and the compositor's
    selection bridge makes it the Wayland clipboard."""
    wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
    xclip = ["xclip", "-selection", "clipboard"] if shutil.which("xclip") and os.environ.get("DISPLAY") else None
    wl = ["wl-copy"] if wayland and shutil.which("wl-copy") else None
    wlr = wl is not None and "zwlr_data_control_manager_v1" in _globals()
    for cmd in ((wl, xclip) if wlr or not wayland else (xclip, wl)):
        if cmd:
            return cmd
    raise RuntimeError("Install wl-clipboard and xclip")


_globals_cache: set[str] | None = None


def _globals() -> set[str]:
    global _globals_cache
    if _globals_cache is None:
        _globals_cache = wayland_globals()
    return _globals_cache


def copy_to_clipboard(text: str):
    subprocess.run(clipboard_command(), input=text.encode(), check=True, timeout=5)


# How long the paste path keeps serving the clipboard after the paste chord. The target app reads
# the selection as it handles Ctrl+V, well under a second; this leaves room for a slow one.
# The .deb's packaging/debian/70-hebrish-uinput.rules, for the AppImage (README, "AppImage").
UINPUT_RULE_COMMAND = ("echo 'KERNEL==\"uinput\", SUBSYSTEM==\"misc\", TAG+=\"uaccess\", "
                       "OPTIONS+=\"static_node=uinput\"' | sudo tee /etc/udev/rules.d/70-hebrish-uinput.rules "
                       "&& sudo udevadm control --reload-rules && sudo udevadm trigger --sysname-match=uinput")

PASTE_HOLD_S = 1.5
FOREGROUND = {"xclip": "-quiet", "wl-copy": "--foreground"}


def copy_for_paste(text: str) -> subprocess.Popen:
    """Set the clipboard for one paste and return the process serving it, kept in the
    foreground (xclip -quiet, wl-copy --foreground) so it can be ended after the paste.

    copy_to_clipboard's tool forks into the background and owns the selection until something
    else takes it. On KWin that held the XWayland CLIPBOARD with the dictated text after the
    Wayland clipboard had moved on (an image copied in a Wayland app), so X11 readers such as
    Claude Code's image paste (`xclip -t image/png -o`) got stale text
    (docs/debug-log/2026-10-24-xclip-holds-clipboard.md). The paste only needs the text for the
    moment the target app reads it."""
    cmd = clipboard_command()
    proc = subprocess.Popen(cmd + [FOREGROUND[os.path.basename(cmd[0])]], stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    proc.stdin.write(text.encode())
    proc.stdin.close()
    return proc


def release_later(proc: subprocess.Popen, delay: float = PASTE_HOLD_S):
    """End a copy_for_paste process after `delay`, so it stops owning the clipboard. It may
    already have exited: another copy took the selection over (xclip quits on SelectionClear)."""
    def end():
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
    t = threading.Timer(delay, end)
    t.daemon = True
    t.start()
    return t


class LinuxInserter:
    def __init__(self):
        self._ui = None
        self.error = ""
        try:
            keys = [c for c in ecodes.KEY.keys() if c < ecodes.BTN_MISC]
            self._ui = UInput({ecodes.EV_KEY: keys}, name=OWN_DEVICE_NAME)
        except OSError as e:
            self.error = f"Cannot open /dev/uinput ({e.strerror}); transcripts go to the clipboard only"
            if os.environ.get("APPIMAGE"):     # the .deb installs this rule; an AppImage can't
                self.error += (". To paste at the cursor, run once: " + UINPUT_RULE_COMMAND)

    def insert(self, text: str, method: str, chord: str):
        """method "clipboard" (or no uinput): the text stays on the clipboard. "paste": the
        clipboard holds it only for the paste, then the selection is released (copy_for_paste);
        the Clipboard output copies the whole take afterwards with copy_to_clipboard."""
        if method != "paste" or self._ui is None:
            copy_to_clipboard(text)
            return
        proc = copy_for_paste(text)
        time.sleep(0.12)          # let the compositor see the new clipboard owner
        try:
            self.press(chord)
        finally:
            release_later(proc)

    def press(self, chord: str):
        """Tap a chord (the paste shortcut, or Stop and send's Enter)."""
        if self._ui is None:
            return
        codes = parse_chord(chord)
        for c in codes:
            self._ui.write(ecodes.EV_KEY, c, 1)
        self._ui.syn()
        time.sleep(0.02)
        for c in reversed(codes):
            self._ui.write(ecodes.EV_KEY, c, 0)
        self._ui.syn()
