"""A take bound to the Konsole pane it started in (hebrish.target_linux): parsing dbus-send replies,
finding the focused pane, sendText with its refused fallback, and the inserter's routing."""

import sys

import pytest

if not sys.platform.startswith("linux"):
    pytest.skip("Konsole D-Bus is Linux only", allow_module_level=True)

from hebrish import target_linux as tl  # noqa: E402

LIST = 'method return\n   array [\n      string "org.freedesktop.DBus"\n      string "org.kde.konsole-7703"\n' \
       '      string ":1.5"\n      string "org.kde.konsole-99"\n   ]\n'
INTRO = '<node><node name="MainWindow_1"/><node name="MainWindow_2"/><node name="actions"/></node>'


def test_parsers():
    assert tl.parse_konsole_services(LIST) == ["org.kde.konsole-7703", "org.kde.konsole-99"]
    assert tl.parse_main_windows(INTRO) == [1, 2]
    assert tl.parse_bool("   variant       boolean true\n")
    assert not tl.parse_bool("   variant       boolean false\n")
    assert tl.parse_int("method return\n   int32 12\n") == 12
    assert tl.parse_int("nothing") is None


def test_wrap_only_multiline():
    assert tl.wrap("hello world") == "hello world"
    assert tl.wrap("a\nb") == "\x1b[200~a\nb\x1b[201~"


def _bus(active, current=12, deny=False, log=None):
    """A fake _call: Konsole 7703 with windows 1 and 2; `active` is the focused window's n."""
    def call(dest, path, method, *args):
        if log is not None:
            log.append((dest, path, method, args))
        if method.endswith("ListNames"):
            return LIST
        if dest == "org.kde.konsole-99":
            raise tl.DBusError("org.freedesktop.DBus.Error.ServiceUnknown")
        if method.endswith("Introspect"):
            return INTRO
        if method.endswith("Properties.Get"):
            return f"variant boolean {'true' if path.endswith(f'_{active}') else 'false'}"
        if method.endswith("currentSession"):
            return f"int32 {current}"
        if method.endswith("sendText"):
            if deny:
                raise tl.DBusError("Error org.freedesktop.DBus.Error.AccessDenied: Security sensitive DBus API is disabled in the settings.")
            return ""
        if method.endswith("setCurrentSession"):
            return ""
        raise AssertionError(method)
    return call


def test_active_pane(monkeypatch):
    monkeypatch.setattr(tl, "_call", _bus(active=2, current=14))
    assert tl.active_pane() == tl.KonsolePane("org.kde.konsole-7703", 2, 14)


def test_no_active_konsole(monkeypatch):
    monkeypatch.setattr(tl, "_call", _bus(active=None))
    assert tl.active_pane() is None


def test_send_text_and_denied_once():
    log, hints = [], []
    s = tl.PaneSender(_bus(active=1, deny=True, log=log))
    s.on_denied = hints.append
    pane = tl.KonsolePane("org.kde.konsole-7703", 1, 12)
    assert not s.send_text(pane, "hi")
    assert not s.send_text(pane, "again")          # not asked twice
    assert sum(m.endswith("sendText") for _, _, m, _ in log) == 1
    assert hints == [tl.ENABLE_HINT]
    assert tl.PaneSender(_bus(active=1)).send_text(pane, "hi")


def test_focus_switches_pane_only_in_active_window():
    log = []
    s = tl.PaneSender(_bus(active=1, current=10, log=log))
    assert s.focus(tl.KonsolePane("org.kde.konsole-7703", 1, 12))
    assert ("org.kde.konsole-7703", "/Windows/1", "org.kde.konsole.Window.setCurrentSession", ("int32:12",)) in log
    log.clear()
    assert not s.focus(tl.KonsolePane("org.kde.konsole-7703", 2, 12))   # its window isn't focused
    assert not any(m.endswith("setCurrentSession") for _, _, m, _ in log)


def test_binding_runs_lookup_off_thread():
    pane = tl.KonsolePane("org.kde.konsole-1", 1, 3)
    assert tl.Binding(lambda: pane).get() == pane
    assert tl.Binding(lambda: None).get() is None


class _Pane:
    def __init__(self, pane):
        self.pane = pane

    def get(self, timeout=1.0):
        return self.pane


def test_inserter_routes_to_pane(monkeypatch):
    pytest.importorskip("evdev")
    from hebrish import inserter_linux as il
    sent, focused, pasted = [], [], []
    monkeypatch.setattr(tl.SENDER, "send_text", lambda p, t: sent.append(t) or True)
    monkeypatch.setattr(tl.SENDER, "focus", lambda p: focused.append(p) or True)
    ins = il.LinuxInserter.__new__(il.LinuxInserter)
    ins._ui = None
    monkeypatch.setattr(il, "copy_to_clipboard", lambda t: pasted.append(t))
    pane = _Pane(tl.KonsolePane("org.kde.konsole-1", 1, 3))
    ins.insert("שלום there ", "paste", "ctrl+v", target=pane)
    ins.press("enter", target=pane)
    assert sent == ["שלום there ", "\r"] and not pasted and not focused
    # sendText refused: the pane is focused, then the usual paste route
    monkeypatch.setattr(tl.SENDER, "send_text", lambda p, t: False)
    ins.insert("x", "paste", "ctrl+v", target=pane)
    assert focused and pasted == ["x"]
    # not bound (focus wasn't in a Konsole): as before
    focused.clear()
    ins.insert("y", "paste", "ctrl+v", target=_Pane(None))
    assert not focused and pasted == ["x", "y"]


def test_kwin_window_loads_script_once_and_invokes(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setattr(tl, "RESTORE_WAIT_S", 0)
    calls, loaded = [], []

    def call(dest, path, method, *args):
        calls.append((method.rsplit(".", 1)[-1], args))
        if method.endswith("isScriptLoaded"):
            return f"boolean {'true' if loaded else 'false'}"
        if method.endswith("loadScript"):
            loaded.append(args)
            return "int32 0"
        return ""
    k = tl.KWinWindow(call)
    assert k.bind() and k.bind()
    assert len(loaded) == 1
    assert (tmp_path / f"{tl.PLUGIN}.js").read_text() == tl.KWIN_SCRIPT
    k.restore()
    assert [a for m, a in calls if m == "invokeShortcut"] == [(f"string:{tl.BIND}",), (f"string:{tl.BIND}",),
                                                              (f"string:{tl.RESTORE}",)]


def test_kwin_unavailable():
    def call(*a):
        raise tl.DBusError("org.freedesktop.DBus.Error.ServiceUnknown")
    assert not tl.KWinWindow(call).bind()


def test_window_restored_before_fallback_paste(monkeypatch):
    pytest.importorskip("evdev")
    from hebrish import inserter_linux as il
    order = []

    class Target:
        def get(self, timeout=1.0):
            return None                     # not a Konsole: the window binding only

        def restore_window(self):
            order.append("restore")
    ins = il.LinuxInserter.__new__(il.LinuxInserter)
    ins._ui = None
    monkeypatch.setattr(il, "copy_to_clipboard", lambda t: order.append("paste"))
    ins.insert("z", "paste", "ctrl+v", target=Target())
    assert order == ["restore", "paste"]
