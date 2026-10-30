"""Microphone capture (16 kHz mono float32), audio files, and the start/stop beeps and
spoken status prompts."""

import logging
import math
import shutil
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

from . import mics

log = logging.getLogger("hebrish")

SAMPLE_RATE = 16000
DICTATION_MAX_S = 60 * 60          # one take (hotkey or the Dictate tab); stops itself at the cap
AUDIO_FILTER = "Audio files (*.wav *.mp3 *.m4a *.ogg *.oga *.opus *.flac *.webm *.aac *.mp4)"


def input_devices() -> list[str]:
    """Input device names, the PipeWire/Pulse virtual ones first."""
    seen, out = set(), []
    for d in sd.query_devices():
        if d["max_input_channels"] > 0 and d["name"] not in seen:
            seen.add(d["name"])
            out.append(d["name"])
    return out


VOICE_DIR = Path(__file__).resolve().parent / "data" / "voice"
VOICE_PROMPTS = ("recording", "paused", "resumed", "transcribing", "discarded", "retake",
                 "copied", "no_speech", "failed")      # data/voice/<voice>/<key>.wav
# Character voices (0.7.0), made by scripts/make_voice_characters.py. Config `voice`.
VOICES = [("herman", "Herman"), ("corn", "Corn"), ("hilbert", "Hilbert")]
# Level zones for the meter, in dBFS of the block RMS (speech guidance from Voice Notepad's mic
# test: aim for -30 to -12) and of the block peak (clipping).
QUIET_DB, LOUD_DB, CLIP_PEAK = -40.0, -12.0, 0.98


def db(x: float) -> float:
    return 20 * math.log10(x) if x > 1e-6 else -120.0


def _play(samples: np.ndarray, sr: int) -> float:
    """Start playing (returns at once); returns how long it plays, in seconds."""
    # 25 ms of silence first: PipeWire/Pulse often swallow or click the first few ms of a
    # fresh stream, which is what made the 0.4.0 pips sound clipped and odd.
    lead = np.zeros(int(sr * 0.025), np.float32)
    try:
        sd.play(np.concatenate([lead, samples.astype(np.float32)]), sr)
    except sd.PortAudioError:
        return 0.0
    return (len(lead) + len(samples)) / sr


def default_input_name() -> str:
    """What "System default" means right now. PortAudio on PipeWire/Pulse only sees a device
    called "default", so on Linux ask the sound server for its default source's description."""
    if sys.platform.startswith("linux") and shutil.which("pactl"):
        try:
            import json
            src = subprocess.run(["pactl", "get-default-source"], capture_output=True, text=True,
                                 timeout=2).stdout.strip()
            for d in json.loads(subprocess.run(["pactl", "-f", "json", "list", "sources"],
                                               capture_output=True, text=True, timeout=2).stdout):
                if d.get("name") == src:
                    return d.get("description") or src
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    try:
        return sd.query_devices(kind="input")["name"]
    except Exception:
        return ""


# Beep styles (config `beep_style`, 1.008, Daniel 2026-10-28: a less conspicuous beep, still
# audible but not jarring for people nearby; Soft is the default, the old beep stays as Loud).
# Each is (pitch factor, length ms, attack ms, release ms, octave level, volume factor):
# - soft: a fifth lower (x0.67, 880 Hz -> 587 Hz), a pure sine, slow fades, about half as loud.
#   Low pure tones carry less across a room and have no edge for the ear to catch.
# - loud: the 0.5.0 to 1.007 pip, sine plus a quiet octave (config value "classic").
# Freedesktop/KDE/Yaru theme sounds were auditioned the same day and not wanted.
BEEP_STYLES = {"soft": (0.67, 150, 35, 90, 0.0, 0.5),
               "classic": (1.0, 110, 12, 45, 0.2, 1.0)}
BEEP_STYLE_NAMES = [("soft", "Soft"), ("classic", "Loud")]


def _pip(freq: float, style: str, volume: float, sr: int) -> np.ndarray:
    k, ms, att, rel, octave, gain = BEEP_STYLES.get(style, BEEP_STYLES["soft"])
    f = freq * k
    t = np.arange(int(sr * ms / 1000)) / sr
    tone = (np.sin(2 * np.pi * f * t) + octave * np.sin(4 * np.pi * f * t)) * volume * gain / (1 + octave)
    a, r = int(sr * att / 1000), int(sr * rel / 1000)
    tone[:a] *= 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, a))
    tone[-r:] *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, r))
    return tone


def beep(freq: float | tuple, volume: float = 0.25, style: str = "soft") -> float:
    """A pip in one of BEEP_STYLES. A tuple of frequencies plays them in turn, 40 ms apart
    (discard's falling "doo-doo"). Up to 0.4.0 it was a 70 ms bare sine with 10 ms linear fades;
    0.5.0 to 1.007 only the Loud pip."""
    sr = 48000
    gap = np.zeros(int(sr * 0.04))
    parts = []
    for f in (freq if isinstance(freq, tuple) else (freq,)):
        parts += [_pip(f, style, volume, sr), gap]
    return _play(np.concatenate(parts[:-1]), sr)


def say(key: str, voice: str = "herman", volume: float = 0.5) -> float:
    """Play a spoken status prompt (data/voice/<voice>/<key>.wav); returns its length in
    seconds. Missing file: silent, 0."""
    try:
        with wave.open(str(VOICE_DIR / voice / f"{key}.wav"), "rb") as w:
            sr, raw = w.getframerate(), w.readframes(w.getnframes())
    except (OSError, wave.Error):
        return 0.0
    return _play(np.frombuffer(raw, "<i2").astype(np.float32) / 32768 * min(1.0, volume * 1.6), sr)


class Recorder:
    def __init__(self, max_s: int = DICTATION_MAX_S):
        self._max = max_s * SAMPLE_RATE
        self._chunks: list[np.ndarray] = []
        self._n = 0
        self._stream = None
        self._lock = threading.Lock()
        self.level = 0.0            # RMS of the last block, 0..1, for a meter
        self.rms = 0.0              # the same, unscaled (dBFS: db(rms))
        self.peak = 0.0             # peak of the last block
        self.clipped_at = 0.0       # time.monotonic() of the last block that hit CLIP_PEAK
        self.paused = False
        self._mute_until = 0.0      # time.monotonic(): drop input until then (mute())

    @property
    def active(self) -> bool:
        return self._stream is not None

    @property
    def seconds(self) -> float:
        return self._n / SAMPLE_RATE

    @property
    def full(self) -> bool:
        return self._n >= self._max

    def peek(self) -> np.ndarray:
        """The audio not yet consumed, without stopping (live insertion)."""
        with self._lock:
            return np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)

    def consume(self, n: int) -> np.ndarray:
        """Remove and return the first n unconsumed samples. seconds still counts them."""
        with self._lock:
            buf = np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
            self._chunks = [buf[n:]] if len(buf) > n else []
        return buf[:n]

    def mute(self, seconds: float):
        """Drop the next `seconds` of input: our own beep or spoken prompt playing through the
        speakers, which the mic would otherwise record (and the model transcribe)."""
        self._mute_until = max(self._mute_until, time.monotonic() + seconds)

    def start(self, device: str = ""):
        self._chunks, self._n, self.paused, self._mute_until = [], 0, False, 0.0
        self._open(device)

    def _open(self, device):
        self._device = device
        s = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                           device=device or None, callback=self._cb)
        try:
            s.start()
        except Exception:
            s.close()        # not left as self._stream: the recorder would look active with no mic
            raise
        self._stream = s
        mics.OPEN.add(self)

    def pause(self):
        """Stops the stream, so the mic (and the privacy indicator) goes off."""
        if self._stream and not self.paused:
            self._close()
            self._stream = object()        # still "active"
            self.paused = True
            self.level = self.rms = self.peak = 0.0

    def resume(self):
        if self.paused:
            self.paused = False
            self._open(self._device)

    def _cb(self, indata, frames, time_info, status):
        block = indata[:, 0]
        self.rms = float(np.sqrt(np.mean(block ** 2)))
        self.peak = float(np.max(np.abs(block))) if len(block) else 0.0
        if self.peak >= CLIP_PEAK:
            self.clipped_at = time.monotonic()
        self.level = min(1.0, self.rms * 4)
        if time.monotonic() < self._mute_until:
            return
        with self._lock:
            if self._n < self._max:
                self._chunks.append(block.copy())
                self._n += len(block)

    def _close(self):
        s = self._stream
        try:
            if isinstance(s, sd.InputStream):
                s.stop()
                s.close()
        except Exception:        # a dead stream (device unplugged) may fail to stop; drop it
            log.warning("closing the input stream failed", exc_info=True)
        finally:
            mics.OPEN.discard(self)

    def stop(self) -> np.ndarray:
        self._close()
        self._stream, self.paused, self.level, self.rms, self.peak = None, False, 0.0, 0.0, 0.0
        with self._lock:
            out = np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
            self._chunks, self._n = [], 0
        return out


# -- files -----------------------------------------------------------------------

def _resample(x: np.ndarray, sr: int) -> np.ndarray:
    if sr == SAMPLE_RATE:
        return x
    # box-filter before linear interpolation, so downsampling doesn't alias badly
    k = max(1, round(sr / SAMPLE_RATE))
    if k > 1:
        x = np.convolve(x, np.ones(k) / k, mode="same")
    n = int(len(x) * SAMPLE_RATE / sr)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def load_file(path: str) -> np.ndarray:
    """Any audio file -> 16 kHz mono float32. ffmpeg when installed (every format),
    else soundfile (wav, flac, ogg, mp3)."""
    ff = shutil.which("ffmpeg")
    if ff:
        flags = {"creationflags": 0x08000000} if sys.platform == "win32" else {}   # no console flash
        r = subprocess.run([ff, "-v", "error", "-i", path, "-ac", "1", "-ar", str(SAMPLE_RATE),
                            "-f", "f32le", "-"], capture_output=True, **flags)
        if r.returncode == 0:
            return np.frombuffer(r.stdout, np.float32).copy()
        err = r.stderr.decode(errors="replace").strip().splitlines()
        raise RuntimeError(err[-1] if err else "ffmpeg couldn't read the file")
    try:
        import soundfile
    except ImportError:
        raise RuntimeError("Install ffmpeg to open audio files") from None
    data, sr = soundfile.read(path, dtype="float32", always_2d=True)
    return _resample(data.mean(axis=1), sr)


def save_wav(path: str, samples: np.ndarray):
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
