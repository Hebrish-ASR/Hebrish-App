"""Windows key source: a low-level keyboard hook through pynput.

RegisterHotKey would be the polite API, but it reports presses only, and push-to-talk
needs the release. The hook sees every key without consuming it.
"""

from pynput import keyboard

from .hotkey import HotkeyMachine

# pynput Key names -> evdev-style names, so config files are the same on both OSes
_NAMES = {
    "ctrl_l": "KEY_LEFTCTRL", "ctrl_r": "KEY_RIGHTCTRL", "ctrl": "KEY_LEFTCTRL",
    "shift_l": "KEY_LEFTSHIFT", "shift_r": "KEY_RIGHTSHIFT", "shift": "KEY_LEFTSHIFT",
    "alt_l": "KEY_LEFTALT", "alt_r": "KEY_RIGHTALT", "alt_gr": "KEY_RIGHTALT", "alt": "KEY_LEFTALT",
    "cmd_l": "KEY_LEFTMETA", "cmd_r": "KEY_RIGHTMETA", "cmd": "KEY_LEFTMETA",
    "page_up": "KEY_PAGEUP", "page_down": "KEY_PAGEDOWN", "caps_lock": "KEY_CAPSLOCK",
    "num_lock": "KEY_NUMLOCK", "scroll_lock": "KEY_SCROLLLOCK", "print_screen": "KEY_SYSRQ",
    "enter": "KEY_ENTER", "esc": "KEY_ESC", "menu": "KEY_COMPOSE",
}


def key_name(k) -> str:
    if isinstance(k, keyboard.Key):
        return _NAMES.get(k.name, f"KEY_{k.name.upper()}")
    if getattr(k, "char", None) and k.char.isprintable() and len(k.char) == 1:
        return f"KEY_{k.char.upper()}"
    return f"VK_{getattr(k, 'vk', 0)}"


class WindowsHotkeys(HotkeyMachine):
    def start(self):
        self._listener = keyboard.Listener(
            on_press=lambda k: self.key(key_name(k), True),
            on_release=lambda k: self.key(key_name(k), False))
        self._listener.daemon = True
        self._listener.start()
