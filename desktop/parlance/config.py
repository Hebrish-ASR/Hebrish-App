"""Paths and the user config (~/.config/parlance/config.json)."""

import json
import os
import shutil
import sys
from pathlib import Path

APP_ID = "com.danielrosehill.Parlance"
APP_NAME = "Parlance"
TAGLINE = "On-device dictation with Parakeet"

_env = lambda var, default: Path(os.environ.get(var) or Path.home() / default)  # noqa: E731
if sys.platform == "win32":
    CONFIG_DIR = _env("APPDATA", "AppData/Roaming") / "Parlance"
    DATA_DIR = _env("LOCALAPPDATA", "AppData/Local") / "Parlance"   # 660 MB: not roaming
else:
    CONFIG_DIR = _env("XDG_CONFIG_HOME", ".config") / "parlance"
    DATA_DIR = _env("XDG_DATA_HOME", ".local/share") / "parlance"
CONFIG_PATH = CONFIG_DIR / "config.json"
STATE_PATH = DATA_DIR / "state.json"          # active model, last update check
HISTORY_PATH = DATA_DIR / "history.json"
MODELS_DIR = DATA_DIR / "models"            # models/<catalogue id>/<version>-<sha12>/
CATALOGUE_CACHE = DATA_DIR / "catalogue.json"   # last models.json fetched from GitHub

# Predecessor apps (Voice To Hebrish, and before it Codeswitch Dictation) ran only the
# code-switching model. Their settings are copied and their downloaded versions moved into
# models/codeswitch/, so switching apps doesn't re-download 660 MB.
_LEGACY = ("voice-to-hebrish", "codeswitch-dictation") if sys.platform != "win32" else ("VoiceToHebrish",)

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
    """One-off, on first start only (when our own config doesn't exist yet)."""
    if CONFIG_PATH.exists():
        return
    for name in _LEGACY:
        old_cfg = CONFIG_DIR.with_name(name) / "config.json"
        old_models = DATA_DIR.with_name(name) / "models"
        if not (old_cfg.is_file() or old_models.is_dir()):
            continue
        stored = load_json(old_cfg)
        save_json(CONFIG_PATH, {k: v for k, v in stored.items() if k in DEFAULTS})
        if old_models.is_dir():
            dest = MODELS_DIR / "codeswitch"
            dest.mkdir(parents=True, exist_ok=True)
            for d in old_models.iterdir():
                if (d / "manifest.json").is_file() and not (dest / d.name).exists():
                    shutil.move(str(d), dest / d.name)
            if any(dest.iterdir()):
                state = load_json(STATE_PATH)
                state["model"] = "codeswitch"
                save_json(STATE_PATH, state)
        return


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
