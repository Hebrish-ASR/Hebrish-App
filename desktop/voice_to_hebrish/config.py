"""Paths and the user config (~/.config/voice-to-hebrish/config.json)."""

import json
import os
import sys
from pathlib import Path

APP_ID = "com.danielrosehill.VoiceToHebrish"
APP_NAME = "Voice To Hebrish"
TAGLINE = "Dictation for Anglos in Israel"

_env = lambda var, default: Path(os.environ.get(var) or Path.home() / default)  # noqa: E731
if sys.platform == "win32":
    CONFIG_DIR = _env("APPDATA", "AppData/Roaming") / "VoiceToHebrish"
    DATA_DIR = _env("LOCALAPPDATA", "AppData/Local") / "VoiceToHebrish"   # 660 MB: not roaming
else:
    CONFIG_DIR = _env("XDG_CONFIG_HOME", ".config") / "voice-to-hebrish"
    DATA_DIR = _env("XDG_DATA_HOME", ".local/share") / "voice-to-hebrish"
CONFIG_PATH = CONFIG_DIR / "config.json"
STATE_PATH = DATA_DIR / "state.json"          # active model, last update check
HISTORY_PATH = DATA_DIR / "history.json"
MODELS_DIR = DATA_DIR / "models"

# 0.1.0 shipped as "Codeswitch Dictation"; its folders are moved, not re-downloaded.
_LEGACY = "codeswitch-dictation"

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
    "keep_history": True,         # remember recent transcripts across restarts
    "update_check_hours": 24,     # 0 = never check automatically
    "auto_update": False,         # download a new version without asking
    "keep_old_versions": True,    # False = delete the previous model once the new one verifies
}


def migrate_legacy():
    for new in (CONFIG_DIR, DATA_DIR):
        old = new.with_name(_LEGACY)
        if old.is_dir() and not new.exists():
            old.rename(new)


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {} if default is None else default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
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
