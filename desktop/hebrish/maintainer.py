"""Maintainer mode (R-2026-11-02-2, opt-in, off by default): keep each Voice Typing take's audio
and a seam log beside its History row, so seam, cut and punctuation rules can be measured on
real dictation and replayed against changed rules (the private `dictation-boundary-audit` skill).

History itself stays text only (D-2026-10-22-20). This is a separate, capped folder,
DATA_DIR/maintainer/<YYYY-MM-DD>/<row id>.flac + .json:

- audio: the take as recorded, 16 kHz mono, FLAC 16-bit through soundfile (lossless, so a
  replay hears what the app heard); WAV when soundfile is missing. About 1 MB per minute.
- json: schema 1. `row_id`, `audio`, `sample_rate`, `decode` (as History's), and `pieces`, one per
  live piece in order: `start_s`/`len_s` in the take, `pause_s` (the pause it was cut at; 0 a
  forced cut, null the last piece), `context` (whether it was decoded after the previous piece),
  `stop` (the model's own mark at the seam: true, false, null = no context), `raw` (decoder text),
  `text` (after disfluency, seam and dictionary), `lead` (what was pasted before it), `held_in` /
  `held_out` (a full stop held back across the seam before / after it), `decode_s`. `pasted`: every
  string sent to the cursor, in order, with `late` true for words the Enter guard kept back.

Written on the GUI thread after the take's History row exists (Controller._done); encoding a
take takes milliseconds and never delays a paste. prune() runs after each save: day folders older
than `maintainer_keep_days` go first, then the oldest takes until under `maintainer_max_gb`.
Deleting all History empties the folder too. docs/maintaining.md, "Maintainer mode"."""

import json
import logging
import shutil
import time
import wave
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from . import config
from .audio import SAMPLE_RATE

log = logging.getLogger(__name__)

SCHEMA = 1
KEEP_DAYS = 14            # config maintainer_keep_days
MAX_GB = 3.0              # config maintainer_max_gb


def folder() -> Path:
    return config.DATA_DIR / "maintainer"


def save(row_id: int, samples, record: dict, root: Path | None = None, day: str | None = None) -> Path:
    """Write <row id>.flac (or .wav) and <row id>.json under root/<day>; returns the json path."""
    d = (root or folder()) / (day or time.strftime("%Y-%m-%d"))
    d.mkdir(parents=True, exist_ok=True)
    stem = d / f"{row_id:07d}"
    audio = _write_audio(stem, samples) if samples is not None and len(samples) else None
    rec = {"schema": SCHEMA, "row_id": row_id, "audio": audio.name if audio else None,
           "sample_rate": SAMPLE_RATE, **record}
    out = stem.with_suffix(".json")
    tmp = stem.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(out)
    return out


def _write_audio(stem: Path, samples) -> Path:
    x = np.clip(np.asarray(samples, dtype=np.float32).reshape(-1), -1.0, 1.0)
    try:
        import soundfile
        p = stem.with_suffix(".flac")
        soundfile.write(str(p), x, SAMPLE_RATE, format="FLAC", subtype="PCM_16")
        return p
    except Exception as e:          # ImportError, or a libsndfile without FLAC
        log.info("FLAC unavailable (%s): saving WAV", e)
    p = stem.with_suffix(".wav")
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    return p


def prune(keep_days: int = KEEP_DAYS, max_gb: float = MAX_GB, root: Path | None = None,
          today: date | None = None) -> int:
    """Delete day folders older than keep_days, then the oldest takes until the folder is under
    max_gb. Returns the number of files removed. Only touches files this module writes."""
    root = root or folder()
    if not root.is_dir():
        return 0
    removed = 0
    cutoff = (today or date.today()) - timedelta(days=max(1, keep_days))
    days = sorted(p for p in root.iterdir() if p.is_dir() and _is_day(p.name))
    for d in days:
        if date.fromisoformat(d.name) < cutoff:
            removed += sum(1 for _ in d.iterdir())
            shutil.rmtree(d)
    files = sorted(f for d in sorted(root.iterdir()) if d.is_dir() and _is_day(d.name)
                   for f in d.iterdir() if f.suffix in (".flac", ".wav", ".json"))
    total, cap = sum(f.stat().st_size for f in files), max_gb * 1024 ** 3
    stems: dict[Path, list[Path]] = {}
    for f in files:
        stems.setdefault(f.with_suffix(""), []).append(f)
    for _, group in sorted(stems.items()):
        if total <= cap:
            break
        for f in group:
            total -= f.stat().st_size
            f.unlink()
            removed += 1
    for d in root.iterdir():
        if d.is_dir() and _is_day(d.name) and not any(d.iterdir()):
            d.rmdir()
    return removed


def clear(root: Path | None = None):
    """Delete everything maintainer mode kept (History → delete all, or turning the mode off
    with delete)."""
    root = root or folder()
    if root.is_dir():
        shutil.rmtree(root)


def size_bytes(root: Path | None = None) -> int:
    root = root or folder()
    return sum(f.stat().st_size for f in root.rglob("*") if f.is_file()) if root.is_dir() else 0


def _is_day(name: str) -> bool:
    try:
        date.fromisoformat(name)
        return len(name) == 10
    except ValueError:
        return False
