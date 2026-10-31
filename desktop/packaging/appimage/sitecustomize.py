"""AppImage only (build-appimage.sh puts it on PYTHONPATH; Python imports it at startup).

sounddevice finds PortAudio with ctypes.util.find_library("portaudio"), which on Linux asks
ldconfig's cache (and gcc/ld, absent on most desktops) and ignores LD_LIBRARY_PATH, so it never
sees the copy bundled in $APPDIR/usr/lib ("PortAudio library not found" on Fedora 43,
2026-10-31). Answer with the bundled file when the system has no PortAudio of its own."""
import ctypes.util
import os

_orig = ctypes.util.find_library


def find_library(name):
    found = _orig(name)
    if found is None and name == "portaudio":
        path = os.path.join(os.environ.get("APPDIR", ""), "usr", "lib", "libportaudio.so.2")
        if os.path.isfile(path):
            return path
    return found


ctypes.util.find_library = find_library
