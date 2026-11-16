"""Bind a take to where it started: the Konsole pane that had focus when the take began.

Why (Daniel, 2026-11-16): with Claude Code in four Konsole split panes, drifting into the wrong
pane while a take was transcribing sent the text there. A take now remembers its pane at the
start and delivers to it, wherever focus has moved since.

Konsole's D-Bus API, measured on Konsole 25.12.3 (KDE Plasma 6.6.6, Wayland), 2026-11-16:
- Each Konsole process owns `org.kde.konsole-<pid>` on the session bus.
- `/konsole/MainWindow_<n>` exports the Qt property `org.qtproject.Qt.QWidget.isActiveWindow`:
  true for the window with keyboard focus.
- `/Windows/<n>` has `org.kde.konsole.Window.currentSession()` (the focused pane's session id)
  and `setCurrentSession(int)`, which focuses a pane. Both work with Konsole's defaults.
- `/Sessions/<id>` has `org.kde.konsole.Session.sendText(QString)`: the text goes into that pane's
  terminal as typed input, with no clipboard, no key events and no focus needed. Hebrew arrives
  intact. It is refused ("org.freedesktop.DBus.Error.AccessDenied: Security sensitive DBus API
  is disabled in the settings.") unless Konsole's Settings > Configure Konsole > General >
  "Enable the security sensitive parts of the DBus API" is on: konsolerc `[KonsoleWindow]`
  `EnableSecuritySensitiveDBusAPI=true` (the `[General]` group does not work; tested both).
  Konsole reads it at start, so a hand edit of konsolerc needs a Konsole restart; the
  settings dialog applies at once.
- Assumed, not measured with two windows: MainWindow_<n> and /Windows/<n> number the same window
  (both counters start at 1 and go up one per window in that process).

Delivery (inserter_linux.LinuxInserter): sendText when allowed; when refused, focus the bound
pane with setCurrentSession and paste as before, which still fixes the wrong pane when its
Konsole window has focus. dbus-send (package dbus, always installed) does the calls, as
keyboard_layout does: no new dependency.
"""

from __future__ import annotations

import logging
import re
import subprocess
import threading
from dataclasses import dataclass

log = logging.getLogger(__name__)

TIMEOUT_MS = 300            # per call; a hung Konsole must not hold up a take
DENIED = "AccessDenied"
ENABLE_HINT = ("To send text to the pane a take started in without switching to it, turn on "
               "Konsole's Settings > Configure Konsole > General > \"Enable the security "
               "sensitive parts of the DBus API\". Until then Hebrish switches to that pane and pastes.")
# Bracketed paste (xterm): an app that turned it on (Claude Code, bash's readline) takes the text
# between these as one paste, so a newline in it is not an Enter that sends the message.
PASTE_START, PASTE_END = "\x1b[200~", "\x1b[201~"


class DBusError(Exception):
    pass


def _call(dest: str, path: str, method: str, *args: str) -> str:
    cmd = ["dbus-send", "--session", "--print-reply", f"--reply-timeout={TIMEOUT_MS}",
           f"--dest={dest}", path, method, *args]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_MS / 1000 + 0.5)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise DBusError(str(e)) from e
    if r.returncode:
        raise DBusError(r.stderr.strip() or f"dbus-send exited {r.returncode}")
    return r.stdout


def parse_konsole_services(out: str) -> list[str]:
    """ListNames' reply: the Konsole processes' bus names."""
    return sorted(set(re.findall(r'"(org\.kde\.konsole-\d+)"', out)))


def parse_main_windows(out: str) -> list[int]:
    """Introspect of /konsole: the n of each MainWindow_<n> child node."""
    return sorted(int(n) for n in re.findall(r'<node name="MainWindow_(\d+)"', out))


def parse_bool(out: str) -> bool:
    return bool(re.search(r"\bboolean true\b", out))


def parse_int(out: str) -> int | None:
    m = re.search(r"\bint32 (-?\d+)", out)
    return int(m.group(1)) if m else None


@dataclass(frozen=True)
class KonsolePane:
    service: str        # org.kde.konsole-<pid>
    window: int         # /Windows/<n>
    session: int        # /Sessions/<id>


def active_pane() -> KonsolePane | None:
    """The focused pane of the Konsole window that has keyboard focus, or None (focus is not
    in a Konsole, no Konsole runs, or D-Bus failed)."""
    try:
        names = parse_konsole_services(_call("org.freedesktop.DBus", "/", "org.freedesktop.DBus.ListNames"))
    except DBusError as e:
        log.debug("ListNames failed: %s", e)
        return None
    for svc in names:
        try:
            wins = parse_main_windows(_call(svc, "/konsole", "org.freedesktop.DBus.Introspectable.Introspect"))
            for n in wins:
                active = _call(svc, f"/konsole/MainWindow_{n}", "org.freedesktop.DBus.Properties.Get",
                               "string:org.qtproject.Qt.QWidget", "string:isActiveWindow")
                if not parse_bool(active):
                    continue
                sid = parse_int(_call(svc, f"/Windows/{n}", "org.kde.konsole.Window.currentSession"))
                return KonsolePane(svc, n, sid) if sid is not None else None
        except DBusError as e:
            log.debug("Konsole %s: %s", svc, e)
    return None


def wrap(text: str) -> str:
    """Text for sendText: in bracketed-paste markers only when it holds a line break. Plain text
    otherwise, so a shell or app that never turned bracketed paste on doesn't see the markers."""
    return f"{PASTE_START}{text}{PASTE_END}" if ("\n" in text or "\r" in text) else text


class Binding:
    """One take's target, looked up off the calling thread (start() is on the GUI thread, and a
    slow Konsole must not delay the start cue). get() waits for the lookup, up to a second."""

    def __init__(self, lookup=active_pane):
        self._pane: KonsolePane | None = None
        self._done = threading.Event()
        threading.Thread(target=self._run, args=(lookup,), daemon=True).start()

    def _run(self, lookup):
        try:
            self._pane = lookup()
            if self._pane:
                log.info("take bound to %s session %s", self._pane.service, self._pane.session)
        except Exception:
            log.exception("binding the take to its pane failed")
        finally:
            self._done.set()

    def get(self, timeout: float = 1.0) -> KonsolePane | None:
        self._done.wait(timeout)
        return self._pane


class PaneSender:
    """Delivers to a bound pane. sendText first; once a Konsole has refused it, that process
    isn't asked again (each refusal would cost a round trip per piece) and on_denied fires once."""

    def __init__(self, call=_call):
        self._call = call
        self._denied: set[str] = set()
        self.on_denied = None           # callable(hint), set by the app

    def send_text(self, pane: KonsolePane, text: str) -> bool:
        """True when Konsole took the text."""
        if pane.service in self._denied:
            return False
        try:
            self._call(pane.service, f"/Sessions/{pane.session}", "org.kde.konsole.Session.sendText",
                       f"string:{text}")
            return True
        except DBusError as e:
            if DENIED in str(e):
                self._denied.add(pane.service)
                log.info("Konsole %s refuses sendText (setting off): switching panes instead", pane.service)
                if self.on_denied:
                    try:
                        self.on_denied(ENABLE_HINT)
                    except Exception:
                        log.exception("on_denied failed")
            else:
                log.warning("sendText to %s session %s failed: %s", pane.service, pane.session, e)
            return False

    def focus(self, pane: KonsolePane) -> bool:
        """Make the bound pane the focused one in its window, if that window has focus (the paste
        that follows goes to the focused window, so another window's pane would not help).
        True when the pane is focused now."""
        try:
            active = self._call(pane.service, f"/konsole/MainWindow_{pane.window}",
                                "org.freedesktop.DBus.Properties.Get",
                                "string:org.qtproject.Qt.QWidget", "string:isActiveWindow")
            if not parse_bool(active):
                return False
            cur = parse_int(self._call(pane.service, f"/Windows/{pane.window}",
                                       "org.kde.konsole.Window.currentSession"))
            if cur != pane.session:
                self._call(pane.service, f"/Windows/{pane.window}", "org.kde.konsole.Window.setCurrentSession",
                           f"int32:{pane.session}")
                log.info("focused the take's pane %s (was %s)", pane.session, cur)
            return True
        except DBusError as e:
            log.warning("couldn't focus pane %s of %s: %s", pane.session, pane.service, e)
            return False


SENDER = PaneSender()
