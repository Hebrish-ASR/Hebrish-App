"""Windows key source: a low-level keyboard hook through pynput.

RegisterHotKey would be the polite API, but it reports presses only, and push-to-talk
needs the release. The hook sees every key without consuming it, except the Enter guard's
send key while holding (hotkey.HotkeyMachine.send_key): win32_event_filter suppresses it.
Injected keys (ours: the paste chord, Stop and send, the replayed Enter) are never the user's
send key.
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


VK_RETURN = 0x0D
LLKHF_INJECTED = 0x10
LLKHF_EXTENDED = 0x01                       # with VK_RETURN: the keypad Enter
KEYDOWN = (0x0100, 0x0104)                  # WM_KEYDOWN, WM_SYSKEYDOWN


class WindowsHotkeys(HotkeyMachine):
    def _filter(self, msg, data):
        if data.vkCode == VK_RETURN and not data.flags & LLKHF_INJECTED:
            name = "KEY_KPENTER" if data.flags & LLKHF_EXTENDED else "KEY_ENTER"
            if self.send_key(name, msg in KEYDOWN):
                self._listener.suppress_event()
        return True

    def start(self):
        self._listener = keyboard.Listener(
            on_press=lambda k: self.key(key_name(k), True),
            on_release=lambda k: self.key(key_name(k), False),
            win32_event_filter=self._filter)
        self._listener.daemon = True
        self._listener.start()
