"""Paths and the user config (~/.config/codeswitch-dictation/config.json)."""

import json
import os
from pathlib import Path

APP_ID = "com.danielrosehill.CodeswitchDictation"
APP_NAME = "Codeswitch Dictation"

_xdg = lambda var, default: Path(os.environ.get(var) or Path.home() / default)  # noqa: E731
CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "codeswitch-dictation"
DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share") / "codeswitch-dictation"
CONFIG_PATH = CONFIG_DIR / "config.json"
STATE_PATH = DATA_DIR / "state.json"          # active model, last update check
MODELS_DIR = DATA_DIR / "models"

DEFAULTS = {
    "hotkey": "KEY_F13",          # evdev key name; any key on any keyboard
    "mode": "hybrid",             # hold | toggle | hybrid (tap = toggle, hold = push-to-talk)
    "hybrid_hold_ms": 350,        # in hybrid, held longer than this = push-to-talk
    "insert": "paste",            # paste | clipboard
    "paste_chord": "ctrl+v",      # e.g. ctrl+shift+v if you dictate mostly into terminals
    "trailing_space": True,
    "beeps": True,
    "audio_device": "",           # "" = system default; else a sounddevice name
    "num_threads": 4,
    "update_check_hours": 24,     # 0 = never check automatically
    "auto_update": False,         # download a new version without asking
    "keep_old_versions": True,    # False = delete the previous model once the new one verifies
}


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)


class Config(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
        stored = load_json(CONFIG_PATH)
        self.update({k: v for k, v in stored.items() if k in DEFAULTS})
        if not CONFIG_PATH.exists():
            self.save()

    def save(self):
        save_json(CONFIG_PATH, dict(self))

    def set(self, key, value):
        self[key] = value
        self.save()
