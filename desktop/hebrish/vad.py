"""Silero VAD for voice detection (Daniel, 2026-10-29: "can't hurt to have it as an option", then
"VAD should be enabled by default"; reverses the 2026-10-21 "not added", docs/maintaining.md, "VAD").

Bundled with the app (data/vad/, 643,854 bytes, MIT, licence beside it), so it is on wherever
Voice detection is on, unless `vad_silero` is turned off on Models > Utilities. Then
`engine._speech_frames` asks Silero which 20 ms frames are speech instead of the energy rule, for
the two jobs of Voice detection: skipping takes with no speech and shortening long silences. Live
cuts (`live_cut`, `stretch_pauses`) stay on the energy rule: those cut points are measured (1% WER,
2026-10-21).

The file is sherpa-onnx's copy of Silero VAD (`asr-models` release, SHA-256 below), run through
`sherpa_onnx.VoiceActivityDetector` (no new dependency). Android can use the same file through the
same sherpa-onnx API (1.13.8 there too).

Custom model (Daniel, 2026-11-19: "support for a custom [VAD]: just provide the path to your custom
VAD ... it's Silero, so point it to your custom Silero"): config `vad_custom_path`, a Silero-format
ONNX file (a fine-tune). When it is set and passes `check()` it replaces BUNDLED everywhere (live
detector, calibration); no SHA pin. A file that fails the check is never used: `select()` falls back
to BUNDLED and returns the error for the log and the Models page. Docs: maintaining.md, "VAD".
"""

import logging
import threading
from pathlib import Path
from typing import NamedTuple

import numpy as np

from .audio import SAMPLE_RATE

MODEL_ID = "silero-vad"
BUNDLED = Path(__file__).resolve().parent / "data" / "vad" / "silero_vad.onnx"
SHA256 = "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6"
WINDOW = 512                  # samples per Silero step at 16 kHz
THRESHOLD = 0.5              # Silero's own default, and Noise filter 50
FILTER_DEFAULT = 60          # `vad_noise_filter` (Daniel, 2026-11-05): a little stricter than 50, to keep room noise out
MIN_SPEECH_S = 0.1
MIN_SILENCE_S = 0.25
DEAD = 10 ** (-70 / 20)       # as engine.VAD_DEAD: a muted mic is no speech, whatever Silero says
PEAK = 0.5                    # loudness Silero is fed at (the take's 99.9th-percentile sample)


def threshold(level: int) -> float:
    """Noise filter 0-100 as Silero's speech probability: 0 = 0.2, 50 = 0.5 (the old fixed value),
    100 = 0.8. Silero sees each take scaled to PEAK, so room noise in a quiet take is scaled up
    too; a higher threshold is what keeps that out."""
    return 0.2 + 0.006 * min(100, max(0, int(level)))


log = logging.getLogger(__name__)


def installed() -> Path | None:
    return BUNDLED if BUNDLED.is_file() else None


def check(path) -> str | None:
    """None if `path` loads as a Silero VAD in sherpa-onnx and takes ~1 s of silence; else why not.
    Run on set and on load of `vad_custom_path`. Never raises."""
    try:
        p = Path(path).expanduser()
        if not p.is_file():
            return f"file not found: {p}"
        import sherpa_onnx
        cfg = sherpa_onnx.VadModelConfig()
        cfg.silero_vad.model = str(p)
        cfg.silero_vad.threshold = THRESHOLD
        cfg.silero_vad.min_speech_duration = MIN_SPEECH_S
        cfg.silero_vad.min_silence_duration = MIN_SILENCE_S
        cfg.silero_vad.window_size = WINDOW
        cfg.sample_rate = SAMPLE_RATE
        cfg.num_threads = 1
        det = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=5)
        zeros = np.zeros(WINDOW, np.float32)
        for _ in range(SAMPLE_RATE // WINDOW):
            det.accept_waveform(zeros)
        det.flush()
        return None
    except Exception as e:                      # sherpa raises RuntimeError, or aborts the load with a message
        return f"{type(e).__name__}: {e}".strip()[:300] or "could not be loaded"


class Selection(NamedTuple):
    path: Path | None             # the model to run: custom if it passed, else the bundled one
    custom: bool                  # True when `path` is the user's file
    error: str | None             # why the custom file was not used (None when none was asked for)


def select(custom: str = "") -> Selection:
    """The model `vad_custom_path` asks for, or BUNDLED (error says why) when it can't be used."""
    custom = (custom or "").strip()
    if custom:
        err = check(custom)
        if err is None:
            return Selection(Path(custom).expanduser(), True, None)
        log.warning("custom VAD %s not used, falling back to the bundled model: %s", custom, err)
        return Selection(installed(), False, err)
    return Selection(installed(), False, None)


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

    def set_level(self, level: int):
        """Apply the Noise filter; the detector is rebuilt on its next use."""
        with self._lock:
            self._cfg.silero_vad.threshold = threshold(level)
            self._det = None

    def speech_frames(self, x: np.ndarray, frame: int, floor: float = 0.0) -> np.ndarray:
        """True for each `frame`-sample frame of x inside a speech segment. floor: scale as if x
        peaked at least this high (auto_enter: a silent window judged by the take's speech level,
        not blown up to it)."""
        import sherpa_onnx
        n = len(x) // frame
        mask = np.zeros(n, bool)
        peak = float(np.percentile(np.abs(x), 99.9)) if len(x) else 0.0
        if n == 0 or peak < DEAD:
            return mask
        peak = max(peak, floor)
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
