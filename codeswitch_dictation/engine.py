"""sherpa-onnx offline recognizer for the installed fine-tune."""

import threading
from pathlib import Path

import numpy as np

from .audio import SAMPLE_RATE

CHUNK_S = 30          # long takes are decoded in pieces, cut at the quietest moment
SEARCH_S = 5          # ...within the last few seconds of each piece
MIN_TAKE_S = 0.3
# Without trailing silence the model drops the end of the audio: with <0.6 s after the
# last word it lost a whole final sentence (measured 2026-10-18, v4). Releasing
# push-to-talk right as you stop talking produces exactly that, so every chunk is padded.
TAIL_PAD_S = 1.0


def normalize(x: np.ndarray, target_dbfs=-20.0, max_gain=10.0) -> np.ndarray:
    rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
    if rms < 1e-5:
        return x
    gain = min(10 ** (target_dbfs / 20) / rms, max_gain)
    return np.clip(x * gain, -1.0, 1.0).astype(np.float32)


def split_points(x: np.ndarray) -> list[tuple[int, int]]:
    n, step = len(x), CHUNK_S * SAMPLE_RATE
    win = SAMPLE_RATE // 10
    out, start = [], 0
    while n - start > step:
        lo, hi = start + step - SEARCH_S * SAMPLE_RATE, start + step
        frames = x[lo:hi][: (hi - lo) // win * win].reshape(-1, win)
        cut = lo + int(np.argmin((frames ** 2).mean(axis=1))) * win + win // 2
        out.append((start, cut))
        start = cut
    out.append((start, n))
    return out


class Engine:
    def __init__(self):
        self._rec = None
        self._dir: Path | None = None
        self._lock = threading.Lock()

    @property
    def loaded_dir(self) -> Path | None:
        return self._dir

    def load(self, model_dir: Path, num_threads: int = 4):
        import sherpa_onnx
        rec = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(model_dir / "encoder.int8.onnx"),
            decoder=str(model_dir / "decoder.int8.onnx"),
            joiner=str(model_dir / "joiner.int8.onnx"),
            tokens=str(model_dir / "tokens.txt"),
            model_type="nemo_transducer", decoding_method="greedy_search",
            num_threads=num_threads, sample_rate=SAMPLE_RATE, feature_dim=128,
            provider="cpu",
        )
        with self._lock:
            self._rec, self._dir = rec, model_dir
        self.transcribe(np.zeros(SAMPLE_RATE, np.float32))      # warm-up

    def unload(self):
        with self._lock:
            self._rec, self._dir = None, None

    def transcribe(self, samples: np.ndarray) -> str:
        if len(samples) < MIN_TAKE_S * SAMPLE_RATE:
            return ""
        samples = normalize(samples)
        with self._lock:
            if self._rec is None:
                raise RuntimeError("Model not loaded")
            parts = []
            pad = np.zeros(int(TAIL_PAD_S * SAMPLE_RATE), np.float32)
            for a, b in split_points(samples):
                s = self._rec.create_stream()
                s.accept_waveform(SAMPLE_RATE, np.concatenate([samples[a:b], pad]))
                self._rec.decode_stream(s)
                parts.append(s.result.text.strip())
        return " ".join(p for p in parts if p)
