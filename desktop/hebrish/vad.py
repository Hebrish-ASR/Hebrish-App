"""Silero VAD for voice detection (Daniel, 2026-10-29: "can't hurt to have it as an option", then
"VAD should be enabled by default"; reverses the 2026-10-21 "not added", docs/maintaining.md, "VAD").

Bundled with the app (data/vad/, 643,854 bytes, MIT, licence beside it), so it is on wherever
Voice detection is on, unless `vad_silero` is turned off on Models > Add-ons. Then
`engine._speech_frames` asks Silero which 20 ms frames are speech instead of the energy rule, for
the two jobs of Voice detection: skipping takes with no speech and shortening long silences. Live
cuts (`live_cut`, `stretch_pauses`) stay on the energy rule: those cut points are measured (1% WER,
2026-10-21).

The file is sherpa-onnx's copy of Silero VAD (`asr-models` release, SHA-256 below), run through
`sherpa_onnx.VoiceActivityDetector` (no new dependency). Android can use the same file through the
same sherpa-onnx API (1.13.8 there too).
"""

import threading
from pathlib import Path

import numpy as np

from .audio import SAMPLE_RATE

MODEL_ID = "silero-vad"
BUNDLED = Path(__file__).resolve().parent / "data" / "vad" / "silero_vad.onnx"
SHA256 = "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6"
WINDOW = 512                  # samples per Silero step at 16 kHz
THRESHOLD = 0.5
MIN_SPEECH_S = 0.1
MIN_SILENCE_S = 0.25
DEAD = 10 ** (-70 / 20)       # as engine.VAD_DEAD: a muted mic is no speech, whatever Silero says
PEAK = 0.5                    # loudness Silero is fed at (the take's 99.9th-percentile sample)


def installed() -> Path | None:
    return BUNDLED if BUNDLED.is_file() else None


class Silero:
    """One detector, reset per call; calls are serialised (the decode and live threads share it)."""

    def __init__(self, path: Path, threads: int = 1):
        import sherpa_onnx
        cfg = sherpa_onnx.VadModelConfig()
        cfg.silero_vad.model = str(path)
        cfg.silero_vad.threshold = THRESHOLD
        cfg.silero_vad.min_speech_duration = MIN_SPEECH_S
        cfg.silero_vad.min_silence_duration = MIN_SILENCE_S
        cfg.silero_vad.window_size = WINDOW
        cfg.sample_rate = SAMPLE_RATE
        cfg.num_threads = threads
        self.path = path
        self._cfg = cfg
        self._lock = threading.Lock()
        self._det = None
        self._buf = 0.0

    def speech_frames(self, x: np.ndarray, frame: int) -> np.ndarray:
        """True for each `frame`-sample frame of x inside a speech segment."""
        import sherpa_onnx
        n = len(x) // frame
        mask = np.zeros(n, bool)
        peak = float(np.percentile(np.abs(x), 99.9)) if len(x) else 0.0
        if n == 0 or peak < DEAD:
            return mask
        y = np.ascontiguousarray(x * (PEAK / peak), dtype=np.float32)
        secs = len(y) / SAMPLE_RATE + 2
        with self._lock:
            if self._det is None or secs > self._buf:      # the buffer must hold the whole take
                self._buf = max(secs, 60.0)
                self._det = sherpa_onnx.VoiceActivityDetector(self._cfg, buffer_size_in_seconds=self._buf)
            det = self._det
            det.reset()
            for i in range(0, len(y) - WINDOW + 1, WINDOW):
                det.accept_waveform(y[i:i + WINDOW])
            det.flush()
            while not det.empty():
                seg = det.front
                a, b = seg.start // frame, -(-(seg.start + len(seg.samples)) // frame)
                mask[a:min(b, n)] = True
                det.pop()
        return mask
