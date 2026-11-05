"""Noise filter calibration (B-93, Daniel, 2026-11-05: the right setting depends on the mic and the
room, so measure it instead of guessing).

Two recordings: the room with nobody talking, then normal speech. Both go through Silero at each
Noise filter position, exactly as a take would, so the suggestion tests the real setting. A loudness
figure alone can't give it: Silero scales every take to the same level first (vad.Silero).

Two limits come out of the sweep:
  keep_limit   the highest position that keeps essentially all of the speech
  noise_limit  the lowest position at which the room alone no longer counts as speech
Safe is the lower of the two and Optimized the higher. If noise_limit <= keep_limit, a range of
positions does both jobs (`clean`). If not, the gap is a real trade-off: Safe lets some noise
through and Optimized clips some speech.

The recordings are measured and thrown away; only the figures are kept (history.calibrations).
"""

from dataclasses import dataclass

import numpy as np

from . import audio, vad
from .audio import SAMPLE_RATE
from .engine import FRAME, VAD_MIN_SPEECH_S

QUIET_S = 5
SPEECH_S = 10
SETTLE_S = 0.3         # dropped from the start of each recording: the click, the device opening
STEP = 5               # Noise filter positions tried
KEEP = 0.98            # share of the speech that counts as "essentially all"
MARGIN = 10            # kept from each limit when a range does both jobs
SAFE_MIN = 30          # a quiet sample doesn't prove a quiet room: Safe goes no lower than this
MIN_SPEECH_S = 2.0     # less speech than this can't be judged
BRIDGE = 3             # frames (60 ms): a gap this short is inside a word
MIN_BURST = 5          # frames (100 ms): anything shorter isn't a word
CLIP_WARN = 0.9        # Optimized keeping less speech than this gets a warning


@dataclass
class Result:
    noise_db: float
    speech_db: float
    heard_speech: bool
    safe: int = 0
    optimized: int = 0
    clean: bool = False
    noise_beaten: bool = True      # False: the room counts as speech even at 100
    safe_kept: float = 0.0         # share of speech kept
    optimized_kept: float = 0.0
    safe_noise_s: float = 0.0      # seconds of the quiet recording heard as speech
    optimized_noise_s: float = 0.0

    @property
    def usable(self) -> bool:
        """Is there a suggestion? A quiet voice in the room (a TV, someone talking) counts as speech
        at every position, because Silero scales a take with no speech up to full level, so
        suggesting a setting would promise what it can't do."""
        return self.heard_speech and self.noise_beaten

    @property
    def clips(self) -> bool:
        return self.optimized_kept < CLIP_WARN


def _rms(x: np.ndarray) -> np.ndarray:
    m = len(x) // FRAME
    return np.sqrt((x[: m * FRAME].reshape(m, FRAME) ** 2).mean(axis=1))


def bursts(ref: np.ndarray) -> list[tuple[int, int]]:
    """Runs of `ref` frames about a word or syllable long: gaps up to BRIDGE frames are joined, and
    runs under MIN_BURST frames dropped."""
    edges = np.flatnonzero(np.diff(np.concatenate(([0], ref.astype(np.int8), [0]))))
    runs: list[list[int]] = []
    for a, b in zip(edges[::2], edges[1::2]):
        if runs and a - runs[-1][1] <= BRIDGE:
            runs[-1][1] = int(b)
        else:
            runs.append([int(a), int(b)])
    return [(a, b) for a, b in runs if b - a >= MIN_BURST]


def kept_share(runs: list[tuple[int, int]], mask: np.ndarray) -> float:
    """Share of the speech, by length, in bursts the detector mostly heard. Whole bursts, because
    what matters is a lost word: trimming a word's edges costs nothing, and counting frames
    instead made silent rooms, where every word tail is in `ref`, get the lowest suggestions."""
    total = sum(b - a for a, b in runs)
    return sum(b - a for a, b in runs if mask[a:b].mean() >= 0.5) / total


def settle(x: np.ndarray) -> np.ndarray:
    return x[int(SETTLE_S * SAMPLE_RATE):]


def measure(quiet: np.ndarray, speech: np.ndarray, detector) -> Result:
    """detector: a vad.Silero of its own (set_level changes it), or anything with its two methods."""
    q, s = _rms(quiet), _rms(speech)
    noise_db, speech_db = audio.db(float(np.median(q))), audio.db(float(np.percentile(s, 90)))
    # Frames that are surely speech: clearly above the room, and within 20 dB of the speech level. In
    # a silent room the first test alone also takes in breaths and word tails, which Silero rightly
    # drops; they then read as lost speech and the suggestion lands far too low.
    ref = s > max(2 * float(np.percentile(q, 95)), 0.1 * float(np.percentile(s, 90)))
    runs = bursts(ref)
    if sum(b - a for a, b in runs) * FRAME < MIN_SPEECH_S * SAMPLE_RATE:
        return Result(noise_db, speech_db, False)

    levels = list(range(0, 101, STEP))
    kept, noise = {}, {}
    for level in levels:
        detector.set_level(level)
        noise[level] = detector.speech_frames(quiet, FRAME).sum() * FRAME / SAMPLE_RATE
        kept[level] = kept_share(runs, detector.speech_frames(speech, FRAME))

    keep_limit = 0
    for level in levels:                           # up from 0, stopping at the first that loses speech
        if kept[level] < KEEP:
            break
        keep_limit = level
    noise_limit = levels[-1] + STEP                # down from 100, stopping at the first that lets noise in
    for level in reversed(levels):
        if noise[level] >= VAD_MIN_SPEECH_S:
            break
        noise_limit = level
    beaten = noise_limit <= levels[-1]
    noise_limit = min(noise_limit, levels[-1])

    clean = beaten and noise_limit <= keep_limit
    if clean:
        safe = min(max(noise_limit + MARGIN, SAFE_MIN), keep_limit)
        optimized = max(keep_limit - MARGIN, safe)
    else:
        safe, optimized = keep_limit, noise_limit
    return Result(noise_db, speech_db, True, safe, optimized, clean, beaten, kept[safe], kept[optimized],
                  float(noise[safe]), float(noise[optimized]))


def run(quiet: np.ndarray, speech: np.ndarray) -> Result | None:
    """measure() with a fresh detector, so a live take's isn't touched; None without Silero."""
    path = vad.installed()
    return measure(settle(quiet), settle(speech), vad.Silero(path)) if path else None
