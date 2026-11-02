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
    monkeypatch.setattr(il, "KEEPER", il.ClipboardKeeper(delay=60))
    monkeypatch.setattr(il, "read_clipboard", lambda: None)
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


# The user's clipboard is put back after a paste (docs/debug-log/2026-11-02-transcript-pasted-twice.md):
# before, the transcript stayed on it (Klipper refills an emptied clipboard from its history),
# so the user's next Ctrl+V pasted the transcript a second time.

class _Clip:
    """A fake clipboard behind read_clipboard/write_clipboard/copy_for_paste/_copy."""

    def __init__(self, monkeypatch, text):
        self.text, self.writes = text, []
        monkeypatch.setattr(il, "read_clipboard", lambda: self.text)
        monkeypatch.setattr(il, "write_clipboard", self.write)
        monkeypatch.setattr(il, "_copy", self.copy)
        monkeypatch.setattr(il, "copy_for_paste", self.copy)
        monkeypatch.setattr(il, "release_later", lambda p: None)
        monkeypatch.setattr(il.time, "sleep", lambda s: None)

    def write(self, text):
        self.writes.append(text)
        self.text = text

    def copy(self, text):
        self.text = text


def _inserter(monkeypatch, delay=0.05):
    keeper = il.ClipboardKeeper(delay=delay)
    monkeypatch.setattr(il, "KEEPER", keeper)
    ins = il.LinuxInserter.__new__(il.LinuxInserter)
    ins._ui = object()
    ins.press = lambda chord: None
    return ins, keeper


def _settle(keeper):
    t = keeper._timer
    if t is not None:
        t.join(2)


def test_paste_restores_the_users_clipboard(monkeypatch):
    clip = _Clip(monkeypatch, "user's text")
    ins, keeper = _inserter(monkeypatch)
    ins.insert("Transcript ", "paste", "ctrl+v")
    assert clip.text == "Transcript "              # on the clipboard for the paste
    _settle(keeper)
    assert clip.text == "user's text" and clip.writes == ["user's text"]


def test_restore_after_the_owner_is_gone(monkeypatch):
    """Without a clipboard manager the clipboard is empty once release_later ends xclip."""
    clip = _Clip(monkeypatch, "user's text")
    ins, keeper = _inserter(monkeypatch)
    ins.insert("Transcript ", "paste", "ctrl+v")
    clip.text = None
    _settle(keeper)
    assert clip.text == "user's text"


def test_burst_of_pastes_restores_the_first_save(monkeypatch):
    """Insert as you go: piece 2's save would be piece 1's text; the burst keeps the user's."""
    clip = _Clip(monkeypatch, "user's text")
    ins, keeper = _inserter(monkeypatch, delay=0.3)
    ins.insert("Piece one ", "paste", "ctrl+v")
    ins.insert("piece two ", "paste", "ctrl+v")
    _settle(keeper)
    assert clip.writes == ["user's text"]


def test_deliberate_copy_cancels_the_restore(monkeypatch):
    """The Clipboard output copies the whole take after the paste: that copy stays."""
    clip = _Clip(monkeypatch, "user's text")
    ins, keeper = _inserter(monkeypatch, delay=0.2)
    ins.insert("Transcript ", "paste", "ctrl+v")
    t = keeper._timer
    il.copy_to_clipboard("Whole take")
    t.join(2)
    assert clip.text == "Whole take" and clip.writes == []


def test_clipboard_method_cancels_the_restore(monkeypatch):
    clip = _Clip(monkeypatch, "user's text")
    ins, keeper = _inserter(monkeypatch, delay=0.2)
    ins.insert("Piece ", "paste", "ctrl+v")
    t = keeper._timer
    ins.insert("Whole take", "clipboard", "ctrl+v")
    t.join(2)
    assert clip.text == "Whole take" and clip.writes == []


def test_users_new_copy_is_not_overwritten(monkeypatch):
    clip = _Clip(monkeypatch, "user's text")
    ins, keeper = _inserter(monkeypatch)
    ins.insert("Transcript ", "paste", "ctrl+v")
    clip.text = "copied meanwhile"
    _settle(keeper)
    assert clip.text == "copied meanwhile" and clip.writes == []


def test_nothing_saved_nothing_restored(monkeypatch):
    """An image (no text) or an empty clipboard can't be saved: the transcript stays, as before."""
    clip = _Clip(monkeypatch, None)
    ins, keeper = _inserter(monkeypatch)
    ins.insert("Transcript ", "paste", "ctrl+v")
    _settle(keeper)
    assert clip.writes == []


class _Run:
    def __init__(self, returncode=0, stdout=b""):
        self.returncode, self.stdout = returncode, stdout


def test_klipper_get_reads_gvariant_text(monkeypatch):
    out = "(\"x'y \\\"q\\\" \\\\ tab\\there\\nb  \u05e2\u05d1\",)\n".encode()
    monkeypatch.setattr(il.subprocess, "run", lambda cmd, **kw: _Run(0, out))
    assert il._klipper_get() == "x'y \"q\" \\ tab\there\nb  \u05e2\u05d1"


def test_klipper_missing(monkeypatch):
    monkeypatch.setattr(il.subprocess, "run", lambda cmd, **kw: _Run(1))
    assert il._klipper_get() is None and il._klipper_set("x") is False


def test_read_clipboard_kde_wayland_without_klipper_is_unknown(monkeypatch):
    """KWin's X11 side can hold stale text, so xclip -o is not asked there."""
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setattr(il, "_klipper_get", lambda: None)
    monkeypatch.setattr(il, "_globals", lambda: {"ext_data_control_manager_v1"})
    monkeypatch.setattr(il.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(il.subprocess, "run", lambda *a, **kw: pytest.fail("must not read X11"))
    assert il.read_clipboard() is None


def test_read_clipboard_x11_uses_xclip(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(il, "_klipper_get", lambda: None)
    monkeypatch.setattr(il.shutil, "which", lambda name: f"/usr/bin/{name}")
    seen = []
    monkeypatch.setattr(il.subprocess, "run", lambda cmd, **kw: (seen.append(cmd), _Run(0, b"abc"))[1])
    assert il.read_clipboard() == "abc" and seen[0][0] == "xclip"
