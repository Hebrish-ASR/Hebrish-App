"""Microphone capture (16 kHz mono float32), audio files, and the start/stop beeps."""

import shutil
import subprocess
import sys
import threading
import wave

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
DICTATION_MAX_S = 15 * 60          # one hotkey take
LONGFORM_MAX_S = 3 * 60 * 60       # Transcribe tab; ~690 MB of float32 at the cap
AUDIO_FILTER = "Audio files (*.wav *.mp3 *.m4a *.ogg *.oga *.opus *.flac *.webm *.aac *.mp4)"


def input_devices() -> list[str]:
    """Input device names, the PipeWire/Pulse virtual ones first."""
    seen, out = set(), []
    for d in sd.query_devices():
        if d["max_input_channels"] > 0 and d["name"] not in seen:
            seen.add(d["name"])
            out.append(d["name"])
    return out


def beep(freq: float, ms: int = 70, volume: float = 0.25):
    t = np.arange(int(48000 * ms / 1000)) / 48000
    tone = np.sin(2 * np.pi * freq * t) * volume
    fade = min(len(t) // 4, 480)
    tone[:fade] *= np.linspace(0, 1, fade)
    tone[-fade:] *= np.linspace(1, 0, fade)
    try:
        sd.play(tone.astype(np.float32), 48000)
    except sd.PortAudioError:
        pass


class Recorder:
    def __init__(self, max_s: int = DICTATION_MAX_S):
        self._max = max_s * SAMPLE_RATE
        self._chunks: list[np.ndarray] = []
        self._n = 0
        self._stream = None
        self._lock = threading.Lock()
        self.level = 0.0            # RMS of the last block, 0..1, for a meter
        self.paused = False

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

    def start(self, device: str = ""):
        self._chunks, self._n, self.paused = [], 0, False
        self._open(device)

    def _open(self, device):
        self._device = device
        self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                      device=device or None, callback=self._cb)
        self._stream.start()

    def pause(self):
        """Stops the stream, so the mic (and the privacy indicator) goes off."""
        if self._stream and not self.paused:
            self._close()
            self._stream = object()        # still "active"
            self.paused = True
            self.level = 0.0

    def resume(self):
        if self.paused:
            self.paused = False
            self._open(self._device)

    def _cb(self, indata, frames, time_info, status):
        block = indata[:, 0]
        self.level = min(1.0, float(np.sqrt(np.mean(block ** 2))) * 4)
        with self._lock:
            if self._n < self._max:
                self._chunks.append(block.copy())
                self._n += len(block)

    def _close(self):
        s = self._stream
        if isinstance(s, sd.InputStream):
            s.stop()
            s.close()

    def stop(self) -> np.ndarray:
        self._close()
        self._stream, self.paused, self.level = None, False, 0.0
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
