"""Paths and the user config (~/.config/hebrish/config.json)."""

import json
import os
import shutil
import sys
import time
from pathlib import Path

APP_ID = "app.hebrish.Dictation"
APP_NAME = "Hebrish"
AUTOSTART_KEY = "Hebrish"     # Windows HKCU Run value name
# Brand short form ("Dictation that gets the Hebrew words right.", Hebrish-Mgmt/brand/BRAND.md) with
# the app's own name for the mode: Voice Typing, not dictation (Daniel, 2026-10-27).
TAGLINE = "Voice typing that gets the Hebrew words right."

_env = lambda var, default: Path(os.environ.get(var) or Path.home() / default)  # noqa: E731
if sys.platform == "win32":
    CONFIG_DIR = _env("APPDATA", "AppData/Roaming") / "Hebrish"
    DATA_DIR = _env("LOCALAPPDATA", "AppData/Local") / "Hebrish"   # 660 MB: not roaming
else:
    CONFIG_DIR = _env("XDG_CONFIG_HOME", ".config") / "hebrish"
    DATA_DIR = _env("XDG_DATA_HOME", ".local/share") / "hebrish"
CONFIG_PATH = CONFIG_DIR / "config.json"
STATE_PATH = DATA_DIR / "state.json"          # active model, last update checks, dismissed app version
HISTORY_PATH = DATA_DIR / "history.json"     # 0.6.x history (last 50); imported into HISTORY_DB once
HISTORY_DB = DATA_DIR / "history.db"         # 0.7.0+: every transcript (hebrish.history)
MODELS_DIR = DATA_DIR / "models"            # models/<catalogue id>/<version>-<sha12>/
CATALOGUE_CACHE = DATA_DIR / "catalogue-v2.json"   # last shared/catalogue.json fetched (0.6.0+)
# DATA_DIR / "catalogue.json" is the schema-1 models.json cached by 0.5.x and earlier; left alone.

# Predecessor apps (Voice To Hebrish, and before it Codeswitch Dictation) ran only the
# code-switching model. Their settings are copied and their downloaded versions moved into
# models/codeswitch/, so switching apps doesn't re-download 660 MB.
_LEGACY = ("voice-to-hebrish", "codeswitch-dictation") if sys.platform != "win32" else ("VoiceToHebrish",)

DEFAULTS = {
    "hotkey": "KEY_F14",          # toggle key (tap to start, tap to stop); evdev name, "" = none.
                                  # Not F13: Parlance's default
    "hold_to_talk": True,         # holding the toggle key past hybrid_hold_ms is push-to-talk
    "hybrid_hold_ms": 350,
    "ptt_hotkey": "",             # a second, push-to-talk-only key; "" = none
    "key_start": "",              # action keys (macropad, pedals), "" = none: see hotkey.ACTIONS
    "key_stop": "",
    "key_pause": "",              # pause / resume
    "key_retake": "",
    "key_discard": "",
    "key_send": "",               # Stop and send: stop, insert, then press send_chord
    "key_paste_last": "",         # paste the last transcription again (1.000)
    "send_chord": "enter",        # e.g. ctrl+enter for apps where Enter is a new line
    # The send key pressed while a stopped take's last words are still coming (1.007,
    # R-2026-10-22-2): "late" keeps those words out of the next message (clipboard + Paste in the
    # overlay); "hold" also holds the Enter until they are in, then sends it (grabs the keyboard
    # for up to ENTER_HOLD_S); "off" pastes them wherever the cursor is, as before 1.007.
    "enter_guard": "late",
    # Press Enter after silence (R-2026-10-31-1; auto_enter.py): while recording with insert-as-you-go,
    # press send_chord once the take has been silent this long after text was typed. Off by default:
    # an unexpected Enter in another app can send or run something.
    "auto_enter": False,
    "auto_enter_s": 8,
    "double_tap_retake": True,    # double tap of the toggle key while recording = Retake
    "double_tap_ms": 300,         # how long a stopping tap waits for the second tap
    "escape_discards": True,      # Esc while recording discards the take
    "live_insert_s": 6,           # decode while recording and insert every ~N s, at a pause; 0 = off
                                  # presets Fast 4, Normal 6, Relaxed 10 (R-2026-10-25-3; 0.7.1: 3/5/8;
                                  # 0.7.0: 5/7/10), else Custom
    "stream_release": "phrase",   # streaming models: paste every word | phrase | sentence (engine.STREAM_RELEASE; 0.7.1)
    "overlay": "off",             # off | active (while dictating) | always
    "overlay_pos": None,          # [x, y] of the overlay's top-left; None = bottom centre
    "overlay_opacity": 85,        # idle opacity %, "always" mode
    # Where text goes (1.000, Daniel 2026-10-24): three switches, any combination. At the cursor
    # (clipboard + paste chord) only by default; the Dictate tab's text box shows takes only when
    # out_window is on. Up to 0.8.0 one choice, `insert`: paste | clipboard | app.
    "out_cursor": True,
    "out_clipboard": False,       # the whole take on the clipboard when it ends (pieces, if not pasting)
    "out_window": False,          # the Dictate tab's text box
    # After a pasted take, ask AT-SPI whether a text field had focus and, if not, show "No text
    # field" with Paste in the overlay (1.000, hebrish.focus). Opt-in: it turns the desktop's
    # accessibility switch on, and some apps report no field when there is one.
    "detect_no_field": False,

    "paste_chord": "ctrl+v",      # e.g. ctrl+shift+v if you dictate mostly into terminals
    "trailing_space": True,
    "all_caps": False,            # type everything in capitals, just for fun (0.7.2)
    "feedback": "beeps",          # beeps | voice (spoken status: data/voice/<voice>/) | off
    "voice": "herman",            # herman | corn | hilbert (audio.VOICES; 0.7.0)
    "beep_style": "soft",         # soft | classic (shown as Loud: the beep up to 1.007); audio.BEEP_STYLES
    "beep_volume": 50,            # %; 50 = the 0.3.x level; also the voice volume
    "quiet_hours": False,         # between quiet_from and quiet_to (may cross midnight): quiet_sound
    "quiet_sound": "off",         # off (no beeps or voice) | soft (soft beeps, in voice mode too; 1.008)
    "quiet_from": "22:00",
    "quiet_to": "07:00",
    "audio_device": "",           # "" = system default; audio.PREFERRED = the first connected mic in
                                  # mic_order; else a sounddevice name
    # Microphones (R-2026-10-25-2): every input the app has seen, by audio.Mic key (bus, vendor and
    # product id, serial on Linux; the device name elsewhere), each {"label", "alias", "type",
    # "vendor_id", "product_id", "serial", "bus", "device", "first_seen", "last_seen"}; and the
    # order to use them in when audio_device is audio.PREFERRED.
    "mics": {},
    "mic_order": [],
    # Transcription Mode (the Transcription tab's recorder, longform.py; R-2026-10-24-5)
    "tm_audio_device": "",        # its own mic: "" = system default, independent of Dictate's
    "tm_gain_db": 0,              # digital gain, longform.GAIN_MIN_DB..GAIN_MAX_DB
    "tm_levels": "docked",        # gain + level meter (B-45): docked (hidden) | shown (in the card) |
                                  # floating (its own small window). Up to 1.002 `tm_show_meter`
    "tm_paragraphs": "",          # none | time | model (paragraphs.MODES, B-44); "" = not chosen: model
                                  # when the paragraph model is installed, else time
    "tm_cleanup": False,          # clean up each finished transcript with the chosen clean-up model
                                  # (cleanup.py, B-40) once it is downloaded; its paragraphs replace
                                  # the Paragraphs setting while it is on
    "tm_cleanup_model": None,     # the clean-up model the user picked (a catalogue addon id, 2026-10-30);
                                  # None = cleanup.chosen(): an installed one, else the default
                                  # (S1-mini by Superwhisper)
    "tm_vad": True,               # Voice detection for this tab (2026-10-29: on by default here,
                                  # independent of Voice Typing's `vad`; also in the tray menu)
    "tm_save_audio": False,       # keep each transcribed recording (16 kHz mono WAV) in tm_audio_dir
    "tm_audio_dir": "",           # "" = ~/Documents/Hebrish recordings (longform.default_keep_dir)
    "vad": True,                  # skip takes with no speech, shorten long silences (engine.vad)
    "vad_silero": True,           # with Voice detection on, use Silero VAD (bundled, vad.py,
                                  # 2026-10-29); off = the energy rule
    "num_threads": 0,             # decoder threads; 0 = auto (physical cores, at most 8)
    "keep_history": True,         # keep every transcript in history.db (History tab); 0.7.0: on
    "clear_each_take": False,     # the Dictate tab's text box starts empty for each take (0.7.0; off
                                  # since 1.000: takes collect, a blank line between them)
    "models_dir": "",             # where model weights live; "" = DATA_DIR/models
    "update_check_hours": 24,     # 0 = never check automatically
    "auto_update": True,          # download a new model version without asking (0.5.1: default on)
    "app_update_check": True,     # look for a new Hebrish app at start and about daily (0.6.2, app_update)
    # Old model versions are always deleted once the new one verifies (0.5.1, Daniel,
    # 2026-10-21); up to 0.5.0 `keep_old_versions` kept them, default on.
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
_NOT_IMPORTED = ("hotkey", "ptt_hotkey", "key_start", "key_stop", "key_pause", "key_retake",
                 "key_discard")     # Parlance keeps F13; the same key would fire both apps


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
        stored = upgrade(load_json(old_cfg))
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
        stored = upgrade(load_json(old_cfg))
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


def upgrade(stored: dict) -> dict:
    """0.2.x had one key and a `mode` (hold | toggle | hybrid). From 0.3.0 there are two keys:
    `hotkey` toggles (hybrid when `hold_to_talk`), `ptt_hotkey` is push-to-talk only."""
    mode = stored.pop("mode", None)
    if mode == "hold":
        stored["ptt_hotkey"] = stored.get("hotkey", DEFAULTS["hotkey"])
        stored["hotkey"] = ""
    elif mode == "toggle":
        stored["hold_to_talk"] = False
    # Up to 0.3.x num_threads had no setting and every config was saved with the default 4.
    # 0.4.0 adds "auto" (0); a 4 from a file without 0.4.0's keys is that old default.
    if "live_insert_s" not in stored and stored.get("num_threads") == 4:
        stored["num_threads"] = 0
    # 0.5.0 (Daniel, 2026-10-21): insert as you go every ~10 s and no history by default, and
    # `beeps` (bool) became `feedback`. A config without `feedback` predates that: give it the
    # new defaults once, so they reach existing installs too.
    # 0.5.1: no more old model versions on disk, and updates install by themselves. A config
    # that still has `keep_old_versions` predates that: switch auto_update on once.
    if stored.pop("keep_old_versions", None) is not None:
        stored["auto_update"] = True
    if stored and "feedback" not in stored:
        stored["feedback"] = "beeps" if stored.pop("beeps", True) else "off"
        if not stored.get("live_insert_s"):
            stored["live_insert_s"] = 10
        stored["keep_history"] = False
    # 0.7.0 (Daniel, 2026-10-22): Normal insert-as-you-go is ~7 s, not ~10. A config without
    # `send_chord` predates that, and its 10 was the old default, not a choice: move it once.
    if stored and "send_chord" not in stored and stored.get("live_insert_s") == 10:
        stored["live_insert_s"] = 7
    # 0.7.0 (Daniel, 2026-10-22, D-2026-10-22-13): history is on by default, kept in full and
    # searchable. A config without `clear_each_take` predates that, and since 0.5.0 its
    # keep_history False was almost always the forced default: switch it on once.
    if stored and "clear_each_take" not in stored:
        stored["keep_history"] = True
    # 1.000 (Daniel, 2026-10-24): `insert` became three switches, and the text box no longer
    # shows takes unless asked ("by default the paste mode should only be going into ... the
    # cursor position and shouldn't be displayed there in the window"). Takes in the box collect
    # with a blank line between them, so clear_each_take goes off once.
    if "insert" in stored:
        mode = stored.pop("insert")
        stored["out_cursor"] = mode == "paste"
        stored["out_clipboard"] = mode == "clipboard"
        stored["out_window"] = mode == "app"
        stored["clear_each_take"] = False
    # 0.7.3 (Daniel, 2026-10-22, D-2026-10-22-20): the app keeps no audio; the setting is gone.
    stored.pop("keep_audio", None)
    # B-45 (Daniel, 2026-10-24: "I prefer less distraction"): the "Show level" box became the
    # Levels panel, docked (hidden) by default. The old switch is dropped, not carried over: it
    # defaulted to on, so it says nothing about what he wants now.
    stored.pop("tm_show_meter", None)
    # 0.7.1 (Daniel, 2026-10-22: text "a bit too long" in coming): each preset is shorter, Fast
    # 5 -> 3, Normal 7 -> 5, Relaxed 10 -> 8. A config without `stream_release` predates that:
    # keep the preset it was on, once. Custom values stay.
    if stored.get("live_insert_s") in (5, 7, 10) and "stream_release" not in stored:
        stored["live_insert_s"] = {5: 3, 7: 5, 10: 8}[stored["live_insert_s"]]
    # R-2026-10-25-3 (Daniel, 2026-10-25: "the chunks could be ... slightly longer"): Fast 3 -> 4,
    # Normal 5 -> 6, Relaxed 8 -> 10. A config without `mics` (added with it) predates that.
    if stored and "mics" not in stored and stored.get("live_insert_s") in (3, 5, 8):
        stored["live_insert_s"] = {3: 4, 5: 6, 8: 10}[stored["live_insert_s"]]
    return stored


def threads(cfg) -> int:
    """Decoder threads. Auto = physical cores (logical / 2), at most 8: measured 2026-10-21 on a
    Ryzen 7 5700U (8 cores / 16 threads), 51 s of speech took 4.94 s on 4 threads, 4.41 on 8,
    5.29 on 12 and 5.79 on 16."""
    return cfg["num_threads"] or max(1, min(8, (os.cpu_count() or 4) // 2))


def models_root(cfg=None) -> Path:
    """The folder holding models/<id>/<version>/: the user's choice (Settings, "Model storage"),
    else MODELS_DIR."""
    return Path(cfg["models_dir"]).expanduser() if cfg and cfg.get("models_dir") else MODELS_DIR


def in_quiet_hours(cfg, now: time.struct_time | None = None) -> bool:
    if not cfg["quiet_hours"]:
        return False
    t = now or time.localtime()
    cur = t.tm_hour * 60 + t.tm_min
    try:
        a, b = ((int(h) * 60 + int(m)) for h, m in (v.split(":") for v in (cfg["quiet_from"], cfg["quiet_to"])))
    except ValueError:
        return False
    return a <= cur < b if a <= b else (cur >= a or cur < b)


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if default is None else default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")   # not the Windows code page
    tmp.replace(path)


class Config(dict):
    on_set = None             # callback(key) after set(): the window's "Settings saved" toast

    def __init__(self):
        super().__init__(DEFAULTS)
        stored = load_json(CONFIG_PATH)
        old = bool(stored) and ("mode" in stored or "keep_old_versions" in stored
                                or "feedback" not in stored or "send_chord" not in stored
                                or "clear_each_take" not in stored or "insert" in stored
                                or "tm_show_meter" in stored or "mics" not in stored)
        self.update({k: v for k, v in upgrade(stored).items() if k in DEFAULTS})
        if old or not CONFIG_PATH.exists():
            self.save()

    def save(self):
        save_json(CONFIG_PATH, dict(self))

    def set(self, key, value):
        self[key] = value
        self.save()
        if self.on_set:
            self.on_set(key)
