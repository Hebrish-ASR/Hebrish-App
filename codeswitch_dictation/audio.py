"""Microphone capture (16 kHz mono float32) and the start/stop beeps."""

import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
MAX_TAKE_S = 15 * 60


def input_devices() -> list[str]:
    return [d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0]


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
    def __init__(self):
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()

    @property
    def active(self) -> bool:
        return self._stream is not None

    def start(self, device: str = ""):
        self._chunks = []
        self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                      device=device or None, callback=self._cb)
        self._stream.start()

    def _cb(self, indata, frames, time_info, status):
        with self._lock:
            if sum(len(c) for c in self._chunks) < MAX_TAKE_S * SAMPLE_RATE:
                self._chunks.append(indata[:, 0].copy())

    def stop(self) -> np.ndarray:
        stream, self._stream = self._stream, None
        if stream:
            stream.stop()
            stream.close()
        with self._lock:
            out = np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
            self._chunks = []
        return out
