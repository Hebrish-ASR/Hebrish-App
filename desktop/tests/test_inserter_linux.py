"""Which clipboard tool the Linux paste uses (inserter_linux.clipboard_command) and the Wayland
registry probe it decides by. wl-copy without zwlr data-control steals focus on every paste
(docs/maintaining.md, "Paste flicker on KDE (0.7.4)"; docs/debug-log/2026-10-22-paste-flicker-kde.md)."""

import os
import socket
import struct
import sys
import tempfile
import threading

import pytest

if not sys.platform.startswith("linux"):
    pytest.skip("Linux paste path", allow_module_level=True)
pytest.importorskip("evdev")

from hebrish import inserter_linux as il  # noqa: E402


def _global(name: int, iface: str, version: int = 1) -> bytes:
    s = iface.encode() + b"\0"
    s += b"\0" * (-len(s) % 4)
    body = struct.pack("<II", name, len(iface) + 1) + s + struct.pack("<I", version)
    return struct.pack("<II", 2, ((8 + len(body)) << 16) | 0) + body


def _serve(path: str, ifaces: list[str]):
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    srv.listen(1)

    def run():
        conn, _ = srv.accept()
        conn.recv(64)
        events = b"".join(_global(i + 1, n) for i, n in enumerate(ifaces))
        events += struct.pack("<III", 3, (12 << 16) | 0, 0)   # wl_callback.done
        conn.sendall(events[:20])                              # split mid-message on purpose
        conn.sendall(events[20:])
        conn.close()
        srv.close()

    threading.Thread(target=run, daemon=True).start()


def test_wayland_globals_reads_registry(monkeypatch):
    d = tempfile.mkdtemp()
    path = os.path.join(d, "wl-test")
    _serve(path, ["wl_compositor", "ext_data_control_manager_v1", "xdg_wm_base"])
    monkeypatch.setenv("WAYLAND_DISPLAY", path)
    assert il.wayland_globals() == {"wl_compositor", "ext_data_control_manager_v1", "xdg_wm_base"}


def test_wayland_globals_no_socket(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "/nonexistent/wayland-x")
    assert il.wayland_globals() == set()


@pytest.mark.parametrize("globals_, expected", [
    ({"zwlr_data_control_manager_v1"}, "wl-copy"),                   # wlroots, Hyprland
    ({"ext_data_control_manager_v1"}, "xclip"),                      # KWin 6.6
    (set(), "xclip"),                                                # Mutter
])
def test_clipboard_command_wayland(monkeypatch, globals_, expected):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(il.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(il, "_globals", lambda: globals_)
    assert il.clipboard_command()[0] == expected


def test_clipboard_command_wayland_without_xclip(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(il.shutil, "which", lambda name: None if name == "xclip" else f"/usr/bin/{name}")
    monkeypatch.setattr(il, "_globals", lambda: set())
    assert il.clipboard_command() == ["wl-copy"]


def test_clipboard_command_x11(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(il.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert il.clipboard_command()[0] == "xclip"


class _Proc:
    def __init__(self, cmd, **kw):
        self.cmd, self.stdin, self.ended = cmd, self, []
        self.data, self.running = b"", True
        _Proc.made.append(self)

    def write(self, b):
        self.data += b

    def close(self):
        pass

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.ended.append("terminate")
        self.running = False

    def wait(self, timeout=None):
        return 0


@pytest.mark.parametrize("tool, flag", [("xclip", "-quiet"), ("wl-copy", "--foreground")])
def test_paste_releases_clipboard(monkeypatch, tool, flag):
    """The paste path serves the clipboard in the foreground and ends it after the paste, so a
    stale xclip can't keep the XWayland clipboard (docs/debug-log/2026-10-24-xclip-holds-clipboard.md)."""
    _Proc.made = []
    monkeypatch.setattr(il, "clipboard_command", lambda: [tool] + (["-selection", "clipboard"] if tool == "xclip" else []))
    monkeypatch.setattr(il.subprocess, "Popen", _Proc)
    timers = []
    monkeypatch.setattr(il, "release_later", lambda p: timers.append(p))
    ins = il.LinuxInserter.__new__(il.LinuxInserter)
    ins._ui, pressed = object(), []
    ins.press = pressed.append
    ins.insert("hello", "paste", "ctrl+v")
    (p,) = _Proc.made
    assert p.cmd[-1] == flag and p.data == b"hello" and pressed == ["ctrl+v"] and timers == [p]


def test_release_later_ends_running_owner_only():
    p = _Proc(["xclip"])
    il.release_later(p, 0).join()
    assert p.ended == ["terminate"]
    q = _Proc(["xclip"])
    q.running = False                       # already gone: another copy took the selection
    il.release_later(q, 0).join()
    assert q.ended == []


def test_clipboard_method_keeps_the_text(monkeypatch):
    copied = []
    monkeypatch.setattr(il, "copy_to_clipboard", copied.append)
    monkeypatch.setattr(il, "copy_for_paste", lambda t: pytest.fail("clipboard output must keep owning"))
    ins = il.LinuxInserter.__new__(il.LinuxInserter)
    ins._ui = object()
    ins.insert("hello", "clipboard", "ctrl+v")
    assert copied == ["hello"]
