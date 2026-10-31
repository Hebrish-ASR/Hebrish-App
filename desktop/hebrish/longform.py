"""Transcription Mode's recorder (R-2026-10-24-5, B-25): long recordings written to disk as they
are captured, so a crash or a power cut loses at most the last second.

Each recording is one 16 kHz mono 16-bit WAV in RECORDINGS_DIR. The header's sizes are rewritten
every HEADER_EVERY_S, and `recover()` repairs a file whose header lags (the app died
mid-recording). The file is deleted once its transcript is in History; one that never got that
far stays, and the Transcription tab offers it again (`leftovers()`). Audio is otherwise not
kept (D-2026-10-22-20), unless *Save audio* is on (`tm_save_audio`, 2026-10-29): then `keep()`
moves the file to the chosen folder instead of deleting it.

Long sessions (Daniel, 2026-10-29: "at least 90 minutes", "recording doesn't crash"): a disk
error ends the file cleanly instead of killing the stream (`error`), and a stream that stops
delivering blocks (mic unplugged, sound server restarted, resume from suspend) is noticed by the
tab after STALL_S and reopened (`stalled`, `reopen()`). Measured 2026-10-29 on a synthetic 90-minute
recording: written in 2.4 s of callbacks, read back in 0.3 s, Silero VAD and splitting in under a
minute, peak memory 1.55 GB (docs/maintaining.md, "Long recordings").

Gain is digital, applied before the meter and the file, so the meter shows what is recorded:
GAIN_MIN_DB..GAIN_MAX_DB. The clip lamp lights for clipping at the input (before gain, which no
gain setting can undo) and for clipping that the gain causes.
"""

import shutil
import struct
import threading
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

from . import audio, config, mics
from .config import DATA_DIR

RECORDINGS_DIR = DATA_DIR / "recordings"
MAX_S = 4 * 60 * 60          # stops itself after 4 hours (about 460 MB)
RECOMMENDED_S = 90 * 60      # what the tab tells you it is good for (measured, see above)
BYTES_PER_S = 2 * 16000
STALL_S = 3.0                # no block for this long while recording: the stream is reopened
HEADER_EVERY_S = 2.0
GAIN_MIN_DB, GAIN_MAX_DB = -12, 24
_HEADER = 44


def _header(n_bytes: int) -> bytes:
    sr = audio.SAMPLE_RATE
    return (b"RIFF" + struct.pack("<I", 36 + n_bytes) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16) + b"data" + struct.pack("<I", n_bytes))


def apply_gain(block: np.ndarray, gain_db: float) -> np.ndarray:
    return block if not gain_db else block * np.float32(10 ** (gain_db / 20))


class TapeRecorder:
    """Same meter attributes as audio.Recorder (rms, peak, clipped_at, paused, level), so the
    LevelMeter reads either. Nothing is held in memory: blocks go straight to the file."""

    def __init__(self):
        self.path: Path | None = None
        self.gain_db = 0.0
        self.rms = self.peak = self.level = 0.0
        self.clipped_at = 0.0
        self.paused = False
        self._stream = None
        self._f = None
        self._n = 0                  # samples written
        self._lock = threading.Lock()
        self._header_at = 0.0
        self._device = ""
        self.error: OSError | None = None    # writing failed (disk full); the file stops there
        self._last_block = 0.0

    @property
    def active(self) -> bool:
        return self._f is not None

    @property
    def seconds(self) -> float:
        return self._n / audio.SAMPLE_RATE

    @property
    def full(self) -> bool:
        return self._n >= MAX_S * audio.SAMPLE_RATE

    def start(self, device: str = ""):
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        self.path = RECORDINGS_DIR / time.strftime("recording-%Y-%m-%d-%H%M%S.wav")
        self._f = open(self.path, "wb")
        self._f.write(_header(0))
        self._n, self.paused, self.clipped_at, self.error = 0, False, 0.0, None
        try:
            self._open(device)
        except Exception:
            self._f.close()
            self._f = None
            self.path.unlink(missing_ok=True)
            self.path = None
            raise

    def _open(self, device):
        self._device = device
        s = sd.InputStream(samplerate=audio.SAMPLE_RATE, channels=1, dtype="float32",
                           device=device or None, callback=self._cb)
        try:
            s.start()
        except Exception:
            s.close()
            raise
        self._stream = s
        self._last_block = time.monotonic()
        mics.OPEN.add(self)

    def _close_stream(self):
        if self._stream is not None:
            s, self._stream = self._stream, None
            try:
                s.stop()
                s.close()
            except Exception:            # a dead stream (device gone) may fail to stop; drop it
                pass
        mics.OPEN.discard(self)
        self.rms = self.peak = self.level = 0.0

    def switch_device(self, device: str):
        """Change the mic mid-recording; the file carries on."""
        if self.active and not self.paused:
            self._close_stream()
            self._open(device)
        else:
            self._device = device

    @property
    def stalled(self) -> bool:
        """Recording, but no audio block for STALL_S: the stream died without telling us."""
        return (self.active and not self.paused and self._stream is not None
                and time.monotonic() - self._last_block > STALL_S)

    def reopen(self):
        """Close and reopen the stream on the same mic; the file carries on."""
        self._close_stream()
        self._open(self._device)

    def pause(self):
        """Closes the stream, so the mic (and the privacy indicator) goes off."""
        if self.active and not self.paused:
            self._close_stream()
            self.paused = True
            self._flush_header()

    def resume(self):
        if self.active and self.paused:
            self._open(self._device)
            self.paused = False

    def _cb(self, indata, frames, time_info, status):
        self._last_block = time.monotonic()
        raw = indata[:, 0]
        input_clip = len(raw) and float(np.max(np.abs(raw))) >= audio.CLIP_PEAK
        block = apply_gain(raw, self.gain_db)
        self.rms = float(np.sqrt(np.mean(block ** 2))) if len(block) else 0.0
        self.peak = float(np.max(np.abs(block))) if len(block) else 0.0
        if input_clip or self.peak >= audio.CLIP_PEAK:
            self.clipped_at = time.monotonic()
        self.level = min(1.0, self.rms * 4)
        with self._lock:
            if self._f is None or self.full or self.error:
                return
            try:
                self._f.write((np.clip(block, -1, 1) * 32767).astype("<i2").tobytes())
                self._n += len(block)
                if time.monotonic() - self._header_at > HEADER_EVERY_S:
                    self._flush_header()
            except OSError as e:         # disk full: an exception here would kill the stream
                self.error = e

    def _flush_header(self):
        """Rewrite the sizes and flush, so the file on disk is a valid WAV up to now."""
        f = self._f
        if f is None:
            return
        pos = f.tell()
        f.seek(0)
        f.write(_header(self._n * 2))
        f.seek(pos)
        f.flush()
        self._header_at = time.monotonic()

    def stop(self) -> Path | None:
        """Close the stream and the file; returns the recording (None if nothing was captured)."""
        self._close_stream()
        with self._lock:
            if self._f is not None:
                try:
                    self._flush_header()
                    self._f.close()
                except OSError as e:     # disk full: recover() sizes the file from its length
                    self.error = self.error or e
                self._f = None
        path, self.path, self.paused = self.path, None, False
        if path and self._n == 0:
            path.unlink(missing_ok=True)
            return None
        return path

    def discard(self):
        path = self.stop()
        if path:
            path.unlink(missing_ok=True)


def free_seconds() -> float:
    """How much recording the disk under RECORDINGS_DIR has room for."""
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(RECORDINGS_DIR).free / BYTES_PER_S


def default_keep_dir() -> Path:
    """Without a cfg: <Hebrish folder>/recordings. The app passes config.recordings_folder(cfg)."""
    return config.default_files_root() / "recordings"


def keep(path: Path, folder: str) -> Path:
    """Move a transcribed recording into `folder` (the tm_save_audio option), as it was
    recorded: 16 kHz mono 16-bit, gain applied, which is what the model is fed."""
    dest_dir = Path(folder) if folder else default_keep_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    i = 2
    while dest.exists():
        dest = dest_dir / f"{path.stem}-{i}{path.suffix}"
        i += 1
    return Path(shutil.move(str(path), dest))


def recover(path: Path) -> float:
    """Fix the header of a recording the app didn't close (sizes from the file's length);
    returns its length in seconds."""
    n = max(0, path.stat().st_size - _HEADER) // 2 * 2
    with open(path, "r+b") as f:
        f.write(_header(n))
    return n / 2 / audio.SAMPLE_RATE


def load(path: Path) -> np.ndarray:
    recover(path)
    with wave.open(str(path), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768


def leftovers() -> list[Path]:
    """Recordings not yet transcribed (or whose transcription failed), oldest first."""
    if not RECORDINGS_DIR.is_dir():
        return []
    return sorted(p for p in RECORDINGS_DIR.glob("recording-*.wav") if p.stat().st_size > _HEADER)
