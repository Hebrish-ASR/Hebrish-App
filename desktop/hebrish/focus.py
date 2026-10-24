"""Was there a text field to paste into? A best-effort answer from AT-SPI (Linux), for the
"No text field" prompt (1.000, Daniel 2026-10-24: "when the transcription fired, there was no
text input position available ... a pop-up message ... a button for paste").

Three answers, and only False acts: True (the focused object takes text), False (a focused
object was found in the active window and it does not), None (can't tell: no AT-SPI, no
active window, nothing focused, a timeout, or Windows). None never prompts, so an app that
exposes nothing to accessibility can't cause a false alarm.

Measured on KDE Plasma 6 Wayland, 2026-10-24 (V):
- The session's accessibility switch (`org.a11y.Status.IsEnabled`, user bus) is off by default.
  Then only GTK apps and Chrome register; Qt/KDE apps (Konsole, Kate, Dolphin, plasmashell)
  appear once it is on. So the setting that turns this check on also turns that switch on
  (`enable_bus`), which makes every app build its accessibility tree: hence opt-in.
- With it on, the active window was found correctly (Konsole), but Konsole's focused object was
  a non-editable "filler": a terminal you are typing in looks like "no text field". Terminals are
  therefore always taken as text targets (`TERMINALS`, role TERMINAL).
- One query took 0.05-0.35 s (a bounded tree walk, `MAX_NODES`).
"""

import logging
import subprocess
import sys

log = logging.getLogger(__name__)

MAX_NODES = 3000            # most objects one focus search visits
TIMEOUT_MS = 800            # per AT-SPI call; the library default is 25 s for a hung app
# Apps whose focused object is not reported as editable although you type into it (Konsole,
# above). Matched against the AT-SPI application name, lower-case.
TERMINALS = {"konsole", "gnome-terminal", "gnome-terminal-server", "kgx", "ptyxis", "kitty",
             "alacritty", "wezterm", "wezterm-gui", "foot", "terminator", "tilix", "xterm",
             "yakuake", "ghostty", "warp", "tabby",
             "hebrish"}             # our own window: nothing to warn about there
# Roles that take text even when the EDITABLE state is missing.
TEXT_ROLES = {"terminal", "entry", "text", "password text", "editbar", "document text",
              "paragraph", "combo box"}


def classify(app: str, role: str, editable: bool) -> bool:
    """Does a focused object with this app name, role name and EDITABLE state take a paste?"""
    return editable or role.lower() in TEXT_ROLES or app.lower() in TERMINALS


def enable_bus(on: bool = True) -> bool:
    """Set the session's accessibility switch (what GNOME's and KDE's accessibility settings set).
    True when the call went through."""
    if sys.platform == "win32":
        return False
    try:
        return subprocess.run(["busctl", "--user", "set-property", "org.a11y.Bus", "/org/a11y/bus",
                               "org.a11y.Status", "IsEnabled", "b", "true" if on else "false"],
                              capture_output=True, timeout=3).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def text_target() -> bool | None:
    """True / False / None, as in the module docstring. Call it off the GUI thread."""
    if sys.platform == "win32":
        return None
    try:
        import gi
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
    except (ImportError, ValueError):
        return None
    try:
        Atspi.set_timeout(TIMEOUT_MS, -1)
        desktop = Atspi.get_desktop(0)
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if app is None:
                continue
            for j in range(app.get_child_count()):
                win = app.get_child_at_index(j)
                if win is None or not win.get_state_set().contains(Atspi.StateType.ACTIVE):
                    continue
                name = app.get_name() or ""
                if name.lower() in TERMINALS:
                    return True
                node = _focused(win, Atspi)
                if node is None:
                    return None
                return classify(name, node.get_role_name() or "",
                                node.get_state_set().contains(Atspi.StateType.EDITABLE))
    except Exception:
        log.exception("AT-SPI focus query failed")
    return None


def _focused(root, Atspi):
    stack, seen = [root], 0
    while stack and seen < MAX_NODES:
        node = stack.pop()
        seen += 1
        try:
            if node.get_state_set().contains(Atspi.StateType.FOCUSED):
                return node
            for k in range(node.get_child_count() - 1, -1, -1):
                child = node.get_child_at_index(k)
                if child is not None:
                    stack.append(child)
        except Exception:
            continue
    return None
