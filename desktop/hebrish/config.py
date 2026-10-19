"""Paths and the user config (~/.config/hebrish/config.json)."""

import json
import os
import shutil
import sys
from pathlib import Path

APP_ID = "app.hebrish.Dictation"
APP_NAME = "Hebrish"
AUTOSTART_KEY = "Hebrish"     # Windows HKCU Run value name
TAGLINE = "On-device dictation with Parakeet"

_env = lambda var, default: Path(os.environ.get(var) or Path.home() / default)  # noqa: E731
if sys.platform == "win32":
    CONFIG_DIR = _env("APPDATA", "AppData/Roaming") / "Hebrish"
    DATA_DIR = _env("LOCALAPPDATA", "AppData/Local") / "Hebrish"   # 660 MB: not roaming
else:
    CONFIG_DIR = _env("XDG_CONFIG_HOME", ".config") / "hebrish"
    DATA_DIR = _env("XDG_DATA_HOME", ".local/share") / "hebrish"
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
    "hotkey": "KEY_F14",          # evdev key name; any key. Not F13: Parlance's default
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


# --- Import from Parlance (2026-10-19). Review for removal at 0.3.0. -----------------------
# Hebrish desktop was "parlance" internally up to 0.1.2. From 0.2.0 it is a separate app that
# installs alongside Parlance (which keeps every parlance identifier and upgrades 0.1.x in place).
# On Hebrish's first start, Parlance's settings and data are COPIED, never moved: models are
# hardlinked (copied only where linking fails), so nothing is downloaded twice and Parlance keeps
# working. Must run before anything creates CONFIG_DIR / DATA_DIR (including the Windows log).
# Both apps write models as <file>.part then rename, and prune by unlinking, so sharing inodes
# between the two trees is safe.
PARLANCE = "Parlance" if sys.platform == "win32" else "parlance"
_NOT_IMPORTED = ("hotkey",)     # Parlance keeps F13; the same key would fire both apps


def _link_or_copy(src, dst):
    try:
        os.link(src, dst)
    except OSError:                         # cross-device, or no hardlink support
        shutil.copy2(src, dst)
    return dst


def import_parlance() -> bool:
    """Called first by every entry point (the app's and hebrish-model's main()).
    Config: only if Hebrish has no config.json yet. Data: only if it has no state.json and no
    models/ yet (install.sh puts a venv in DATA_DIR first, so the dir itself may exist).
    True if anything was imported. Parlance's dirs are only read."""
    imported = False
    old_cfg = CONFIG_DIR.with_name(PARLANCE) / "config.json"
    if old_cfg.is_file() and not CONFIG_PATH.exists():
        stored = load_json(old_cfg)
        save_json(CONFIG_PATH, {k: v for k, v in stored.items()
                                if k in DEFAULTS and k not in _NOT_IMPORTED})
        imported = True
    old_data = DATA_DIR.with_name(PARLANCE)
    if old_data.is_dir() and not STATE_PATH.exists() and not MODELS_DIR.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        for name in ("state.json", "history.json"):
            if (old_data / name).is_file():
                shutil.copy2(old_data / name, DATA_DIR / name)
                imported = True
        if (old_data / "models").is_dir():
            shutil.copytree(old_data / "models", MODELS_DIR, copy_function=_link_or_copy,
                            ignore=shutil.ignore_patterns("*.part"))
            imported = True
    return imported
# --- end import from Parlance --------------------------------------------------------------


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
        old_history = DATA_DIR.with_name(name) / "history.json"
        if old_history.is_file() and not HISTORY_PATH.exists():
            shutil.copy2(old_history, HISTORY_PATH)
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
