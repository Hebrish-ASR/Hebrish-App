"""Which keyboard layout is active: Hebrew or not (Hebrew switching, 2026-11-16).

Asked once at the start of each take (Controller.start), never polled. Every route is cheap (a
D-Bus call, a gsettings read, one Win32 or Xlib call) and has a short timeout; any failure is
"unknown", which the caller treats as English. `detect()` says which method answered, for the log.

Routes, first that answers wins:
- Windows: GetKeyboardLayout(GetWindowThreadProcessId(GetForegroundWindow())): the layout of the
  window the take will type into. Low word = LANGID; primary language 0x0D is Hebrew.
- KDE Plasma (Wayland or X11): org.kde.keyboard /Layouts getLayout (index) + getLayoutsList.
- GNOME: org.gnome.desktop.input-sources: `mru-sources` first entry (GNOME 3.x+ writes it on each
  switch), else `current` as an index into `sources`.
- X11 (any other desktop): XkbGetState's group as an index into `setxkbmap -query`'s layouts.

The parsers are pure functions, unit-tested in tests/test_keyboard_layout.py.
"""

import ast
import ctypes
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

log = logging.getLogger(__name__)

TIMEOUT_S = 0.5
HEBREW, ENGLISH, UNKNOWN = "he", "en", "unknown"
LANG_HEBREW = 0x0D            # Windows primary language id
_HEBREW_NAMES = ("il", "he", "heb", "hebrew")


@dataclass
class Detected:
    lang: str                 # he | en (any non-Hebrew layout) | unknown
    method: str               # windows | kde | gnome | x11 | none
    layout: str = ""          # what the method reported: "il", "0x040d", ...


# -- parsing (pure) -------------------------------------------------------------------------

def is_hebrew_layout(code: str) -> bool:
    """An xkb layout, a KDE short or long name, or a GNOME/IBus source id: "il", "il(phonetic)",
    "il+lyx", "Hebrew", "he", ibus "m17n:he:kbd"."""
    c = (code or "").strip().lower()
    if not c:
        return False
    base = re.split(r"[(+:]", c, maxsplit=1)[0].strip()
    if base in _HEBREW_NAMES or c.startswith("hebrew"):
        return True
    return ":he:" in c or c.endswith(":he") or c.startswith("he:")    # IBus m17n engines


def lang_of(code: str) -> str:
    """A layout as a probe reports it; KDE's carry the long name after a tab ("il\tHebrew")."""
    return HEBREW if any(is_hebrew_layout(p) for p in (code or "").split("\t")) else ENGLISH


def lang_from_hkl(hkl: int) -> str:
    """Windows HKL (or LANGID): low word is the LANGID, its low 10 bits the primary language."""
    return HEBREW if (int(hkl) & 0xFFFF) & 0x3FF == LANG_HEBREW else ENGLISH


def parse_dbus_uint(out: str) -> int | None:
    """`dbus-send --print-reply` of a method returning uint32/int32: its number."""
    m = re.search(r"\b(?:u?int32|uint16|int16|byte)\s+(\d+)", out)
    return int(m.group(1)) if m else None


def parse_kde_layouts(out: str) -> list[str]:
    """`dbus-send --print-reply` of getLayoutsList (Plasma 5.2x and 6: a(sss), short name,
    variant/display name, long name): each layout as "short" or "short(variant)", plus the long
    name after a tab, so either can say Hebrew."""
    layouts = []
    for block in re.findall(r"struct\s*\{(.*?)\}", out, re.S):
        strings = re.findall(r'string\s+"((?:[^"\\]|\\.)*)"', block)
        if not strings:
            continue
        short = strings[0]
        long_ = strings[2] if len(strings) > 2 else (strings[1] if len(strings) > 1 else "")
        layouts.append(f"{short}\t{long_}" if long_ else short)
    return layouts


def kde_layout(index_out: str, list_out: str) -> str | None:
    i = parse_dbus_uint(index_out)
    layouts = parse_kde_layouts(list_out)
    if i is None or not 0 <= i < len(layouts):
        return None
    return layouts[i]


def parse_gvariant_sources(out: str) -> list[tuple[str, str]]:
    """gsettings' `[('xkb', 'us'), ('xkb', 'il')]` (or `@a(ss) []`) as a list of pairs."""
    text = out.strip()
    if text.startswith("@"):
        text = text.split(" ", 1)[1] if " " in text else "[]"
    try:
        val = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return []
    return [(str(a), str(b)) for a, b in val] if isinstance(val, list) else []


def gnome_layout(mru_out: str, sources_out: str, current_out: str) -> str | None:
    """The active GNOME input source id: mru-sources' first, else sources[current]."""
    mru = parse_gvariant_sources(mru_out)
    if mru:
        return mru[0][1]
    sources = parse_gvariant_sources(sources_out)
    i = parse_dbus_uint(current_out)
    if i is not None and 0 <= i < len(sources):
        return sources[i][1]
    return sources[0][1] if len(sources) == 1 else None


def parse_setxkbmap_layouts(out: str) -> list[str]:
    """`setxkbmap -query`'s layout line ("layout: us,il") with its variants ("variant: ,phonetic")."""
    lay = re.search(r"^layout:\s*(\S+)", out, re.M)
    if not lay:
        return []
    names = lay.group(1).split(",")
    var = re.search(r"^variant:\s*(\S+)", out, re.M)
    variants = var.group(1).split(",") if var else []
    return [f"{n}({v})" if i < len(variants) and (v := variants[i]) else n for i, n in enumerate(names)]


# -- probes -----------------------------------------------------------------------------------

def _run(cmd: list[str]) -> str | None:
    if not shutil.which(cmd[0]):
        return None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _kde() -> str | None:
    base = ["dbus-send", "--session", "--print-reply", "--dest=org.kde.keyboard", "/Layouts"]
    idx = _run(base + ["org.kde.KeyboardLayouts.getLayout"])
    if idx is None:
        return None
    lst = _run(base + ["org.kde.KeyboardLayouts.getLayoutsList"])
    return kde_layout(idx, lst) if lst else None


def _gnome() -> str | None:
    if not shutil.which("gsettings"):
        return None
    schema = "org.gnome.desktop.input-sources"
    sources = _run(["gsettings", "get", schema, "sources"])
    if sources is None:
        return None
    mru = _run(["gsettings", "get", schema, "mru-sources"]) or ""
    cur = _run(["gsettings", "get", schema, "current"]) or ""
    return gnome_layout(mru, sources, cur)


def _x11() -> str | None:
    if not os.environ.get("DISPLAY"):
        return None
    query = _run(["setxkbmap", "-query"])
    layouts = parse_setxkbmap_layouts(query or "")
    if not layouts:
        return None
    if len(layouts) == 1:
        return layouts[0]
    try:
        x11 = ctypes.CDLL("libX11.so.6")
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XkbGetState.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p]
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        dpy = x11.XOpenDisplay(None)
        if not dpy:
            return None
        try:
            state = (ctypes.c_ubyte * 32)()       # XkbStateRec; its first byte is the group
            if x11.XkbGetState(dpy, 0x100, state) != 0:     # XkbUseCoreKbd
                return None
            group = state[0]
        finally:
            x11.XCloseDisplay(dpy)
    except (OSError, AttributeError):
        return None
    return layouts[group] if group < len(layouts) else None


def _windows() -> str | None:
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        user32.GetWindowThreadProcessId.restype = ctypes.c_uint32
        user32.GetKeyboardLayout.argtypes = [ctypes.c_uint32]
        user32.GetKeyboardLayout.restype = ctypes.c_void_p
        hwnd = user32.GetForegroundWindow()
        tid = user32.GetWindowThreadProcessId(hwnd, None) if hwnd else 0
        hkl = user32.GetKeyboardLayout(tid) or 0
    except (OSError, AttributeError):
        return None
    return f"0x{hkl & 0xFFFF:04x}"


def detect() -> Detected:
    """The active layout's language, and which method said so. Never raises."""
    if sys.platform == "win32":
        routes = (("windows", _windows),)
    else:
        desk = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        routes = [("kde", _kde), ("gnome", _gnome), ("x11", _x11)]
        if "gnome" in desk or "unity" in desk or "ubuntu" in desk:
            routes = [routes[1], routes[0], routes[2]]
        if os.environ.get("WAYLAND_DISPLAY"):
            routes = [r for r in routes if r[0] != "x11"]     # XWayland's group doesn't follow the compositor
    for name, probe in routes:
        try:
            code = probe()
        except Exception:
            log.exception("keyboard layout: %s probe failed", name)
            code = None
        if code:
            lang = lang_from_hkl(int(code, 16)) if name == "windows" else lang_of(code)
            return Detected(lang, name, code.split("\t")[0])
    return Detected(UNKNOWN, "none")
