"""sherpa-onnx offline recognizer for the installed fine-tune."""

import threading
from pathlib import Path

import numpy as np

from .audio import SAMPLE_RATE

PIECE_S = 10          # long takes are decoded in pieces of ~10 s or more, cut at a pause (live_cut)
MIN_TAKE_S = 0.3
# Without trailing silence the model drops the end of the audio: with <0.6 s after the
# last word it lost a whole final sentence (measured 2026-10-18, v4). Releasing
# push-to-talk right as you stop talking produces exactly that, so every chunk is padded.
TAIL_PAD_S = 1.0
# Short pauses between sentences can swallow speech: two sentences 0.3 s apart lost half
# of the second, which decodes fine alone (v4, 2026-10-18). Stretching every pause of
# 0.12-0.6 s to 0.6 s recovered sentences in every test (0.3 s gaps: 6/8 -> 8/8) and the
# only single-sentence change was a fix ("Bokartov" -> "Boker Tov"). Costs ~20% more audio.
PAUSE_MIN_S = 0.12
PAUSE_TARGET_S = 0.6
FRAME = 320                       # 20 ms


def normalize(x: np.ndarray, target_dbfs=-20.0, max_gain=10.0) -> np.ndarray:
    rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
    if rms < 1e-5:
        return x
    gain = min(10 ** (target_dbfs / 20) / rms, max_gain)
    return np.clip(x * gain, -1.0, 1.0).astype(np.float32)


def stretch_pauses(x: np.ndarray) -> np.ndarray:
    """Pad quiet runs of PAUSE_MIN_S..PAUSE_TARGET_S out to PAUSE_TARGET_S (inserting zeros in
    the middle of the run). Quiet = below 15% of the way from the noise floor (10th
    percentile frame RMS) to speech level (90th), so it adapts to the mic's gain."""
    n = len(x) // FRAME
    if n < 10:
        return x
    rms = np.sqrt((x[: n * FRAME].reshape(n, FRAME) ** 2).mean(axis=1))
    floor, speech = np.percentile(rms, 10), np.percentile(rms, 90)
    quiet = rms < floor + 0.15 * (speech - floor)
    out, last, i = [], 0, 0
    while i < n:
        if not quiet[i]:
            i += 1
            continue
        j = i
        while j < n and quiet[j]:
            j += 1
        run = (j - i) * FRAME / SAMPLE_RATE
        if PAUSE_MIN_S <= run < PAUSE_TARGET_S and i > 0 and j < n:     # inner pauses only
            mid = (i + j) // 2 * FRAME
            out += [x[last:mid], np.zeros(int((PAUSE_TARGET_S - run) * SAMPLE_RATE), np.float32)]
            last = mid
        i = j
    out.append(x[last:])
    return np.concatenate(out)


# Voice activity (config `vad`, 0.5.0). Energy-based, no extra model: a frame is speech when
# its RMS is above VAD_ABS (-46 dBFS) and above the noise floor by a third of the way to the
# speech level. A take with under VAD_MIN_SPEECH_S of speech frames, or whose loudest frames
# stay under VAD_QUIET (-40 dBFS), is not decoded: Parakeet turns silence and breathing into
# stray words ("Yeah.", "Mm."). Silences longer than VAD_LONG_S are shortened to VAD_KEEP_S
# (still above PAUSE_TARGET_S and LIVE_PAUSE_S, so pause cuts are unaffected) to save decode time.
VAD_ABS = 0.005
VAD_QUIET = 0.01
VAD_MIN_SPEECH_S = 0.25
VAD_LONG_S = 1.5
VAD_KEEP_S = 0.8


def _speech_frames(x: np.ndarray) -> np.ndarray:
    n = len(x) // FRAME
    rms = np.sqrt((x[: n * FRAME].reshape(n, FRAME) ** 2).mean(axis=1))
    if not n:
        return rms > 1
    floor, loud = np.percentile(rms, 10), np.percentile(rms, 95)
    if loud < VAD_QUIET:
        return np.zeros(n, bool)
    return rms > max(VAD_ABS, floor + (loud - floor) / 3)


def has_speech(x: np.ndarray) -> bool:
    return int(_speech_frames(x).sum()) * FRAME >= VAD_MIN_SPEECH_S * SAMPLE_RATE


def shorten_silences(x: np.ndarray) -> np.ndarray:
    """Cut every non-speech run longer than VAD_LONG_S down to VAD_KEEP_S (keeping its two ends)."""
    sp = _speech_frames(x)
    n, keep = len(sp), int(VAD_KEEP_S * SAMPLE_RATE / FRAME)
    out, last, i = [], 0, 0
    while i < n:
        if sp[i]:
            i += 1
            continue
        j = i
        while j < n and not sp[j]:
            j += 1
        if (j - i) * FRAME > VAD_LONG_S * SAMPLE_RATE:
            out.append(x[last:(i + keep // 2) * FRAME])
            last = (j - keep // 2) * FRAME
        i = j
    out.append(x[last:])
    return np.concatenate(out) if out else x


def split_points(x: np.ndarray) -> list[tuple[int, int]]:
    """Cut a whole take the way live insertion cuts it while recording: grow the piece in
    0.5 s steps until live_cut finds a pause. Up to 0.3.x this cut every 30 s at the quietest
    100 ms, often inside a sentence, and lost 126 of 786 words on six 50 s test takes where
    pause cuts lost 9 (2026-10-21, docs/maintaining.md, "Live insertion")."""
    n, sr = len(x), SAMPLE_RATE
    out, start = [], 0
    while n - start > (PIECE_S + LIVE_FORCE_S) * sr:
        end = start + PIECE_S * sr
        while (cut := live_cut(x[start:end], PIECE_S)) is None:
            end += sr // 2
        out.append((start, start + cut))
        start += cut
    out.append((start, n))
    return out


# Live insertion: cut the take while it is still being recorded, at a pause of at least
# LIVE_PAUSE_S found in the last LIVE_SEARCH_S seconds (but not the newest LIVE_GUARD_S, which may
# hold the start of a word). With no pause by interval + LIVE_FORCE_S, cut at the quietest 100 ms.
LIVE_SEARCH_S = 6
LIVE_GUARD_S = 0.3
LIVE_PAUSE_S = 0.6      # 0.3 cut inside sentences: 24 vs 10 errors per 786 words at 15 s
LIVE_FORCE_S = 15


def live_cut(x: np.ndarray, interval_s: float) -> int | None:
    """Sample index to cut a live take at, or None to keep listening. Quiet frames as in
    stretch_pauses; the cut is the middle of the longest quiet run, so both halves keep some
    silence."""
    sr, n = SAMPLE_RATE, len(x)
    if n < interval_s * sr:
        return None
    lo, hi = max(0, n - LIVE_SEARCH_S * sr), n - int(LIVE_GUARD_S * sr)
    m = n // FRAME
    rms = np.sqrt((x[: m * FRAME].reshape(m, FRAME) ** 2).mean(axis=1))
    floor, speech = np.percentile(rms, 10), np.percentile(rms, 90)
    quiet = rms < floor + 0.15 * (speech - floor)
    best, i, a, b = 0, lo // FRAME, 0, 0
    while i < hi // FRAME:
        if quiet[i]:
            j = i
            while j < hi // FRAME and quiet[j]:
                j += 1
            if j - i > best:
                best, a, b = j - i, i, j
            i = j
        else:
            i += 1
    if best * FRAME >= LIVE_PAUSE_S * sr:
        return (a + b) // 2 * FRAME
    if n >= (interval_s + LIVE_FORCE_S) * sr:
        win = sr // 10
        frames = x[lo:hi][: (hi - lo) // win * win].reshape(-1, win)
        return lo + int(np.argmin((frames ** 2).mean(axis=1))) * win + win // 2
    return None


class Engine:
    def __init__(self):
        self._rec = None
        self._dir: Path | None = None
        self._lock = threading.Lock()
        self.last_progress = (0, 1)       # (samples done, total) of the current transcribe_chunks

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

    def transcribe(self, samples: np.ndarray, vad: bool = False) -> str:
        return " ".join(self.transcribe_chunks(samples, vad=vad))

    def transcribe_chunks(self, samples: np.ndarray, cancel=None, vad: bool = False):
        """Yield the text of each piece (split_points) as it is decoded. The lock is taken per
        piece, so a hotkey dictation can slip in between pieces of a long file. With vad, a
        take without speech yields nothing and long silences are shortened first."""
        if len(samples) < MIN_TAKE_S * SAMPLE_RATE:
            return
        if vad:
            if not has_speech(samples):
                self.last_progress = (1, 1)
                return
            samples = shorten_silences(samples)
        samples = stretch_pauses(normalize(samples))
        pad = np.zeros(int(TAIL_PAD_S * SAMPLE_RATE), np.float32)
        for a, b in split_points(samples):
            if cancel is not None and cancel.is_set():
                return
            with self._lock:
                if self._rec is None:
                    raise RuntimeError("Model not loaded")
                s = self._rec.create_stream()
                s.accept_waveform(SAMPLE_RATE, np.concatenate([samples[a:b], pad]))
                self._rec.decode_stream(s)
                text = s.result.text.strip()
            self.last_progress = (b, len(samples))
            if text:
                yield text
