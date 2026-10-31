"""Press Enter after silence (R-2026-10-31-1, opt-in).

While Voice Typing records with insert-as-you-go on, once text has been typed and the take has
been silent for `auto_enter_s` seconds (voice detection's view of silence: engine._speech_frames,
Silero when it is on, else the energy rule), the app presses the send key once, through the
inserter that pastes the text. For dictating into a chat box (Claude, Claude Code) and forgetting
Enter. At most once per silence, only when text was typed since the last Enter, and never while
paused or stopped. Wiring: ui/app.py `Controller._live_tick` and `_auto_enter`;
docs/maintaining.md, "Press Enter after silence".

SilenceClock has no Qt and no audio device, so tests drive it with arrays."""

import numpy as np

from .audio import SAMPLE_RATE
from .engine import FRAME

DEFAULT_S = 8                 # config auto_enter_s
MIN_S, MAX_S = 2, 60          # the settings spin box
OVERLAP_S = 0.3               # each check re-reads this much audio before the new part (a word at the seam)
REF_S = 10                    # earlier audio given to the energy rule as the take's levels


def _peak(x: np.ndarray) -> float:
    return float(np.percentile(np.abs(x), 99.9)) if len(x) else 0.0


class SilenceClock:
    """How long the take has been silent, counted in recorded samples (a paused mic records
    nothing, so pausing never counts as silence). Positions are sample indices of the whole take,
    as `audio.Recorder.tail()` reports them."""

    def __init__(self):
        self.reset(0)

    def reset(self, total: int):
        """A new take (total 0) or a resumed one: the silence starts again from `total`."""
        self.heard = total        # just after the last speech frame heard
        self.checked = total      # samples looked at so far
        self.level = 0.0          # loudness of the speech heard so far (99.9th-percentile sample)
        self.fired = False        # due() already said yes for this silence

    def update(self, buf: np.ndarray, total: int, speech_frames) -> float:
        """Look at the audio recorded since the last call and return the silence so far, in
        seconds. buf: the unconsumed audio, which ends at sample `total` of the take.
        speech_frames(window, ref, level) -> bool per engine.FRAME, as engine._speech_frames."""
        if self.checked < total - len(buf):
            # consumed before this clock saw it (turned on mid-take): count it as speech
            self.heard = max(self.heard, total - len(buf))
        new = total - self.checked
        if new > 0 and len(buf):
            n = min(len(buf), new + int(OVERLAP_S * SAMPLE_RATE))
            win = buf[-n:]
            ref = buf[max(0, len(buf) - n - REF_S * SAMPLE_RATE): len(buf) - n]
            sp = np.asarray(speech_frames(win, ref if len(ref) >= FRAME else None, self.level))
            hits = np.flatnonzero(sp)
            if len(hits):
                heard = total - n + (int(hits[-1]) + 1) * FRAME
                if heard > self.heard:
                    self.heard, self.fired = heard, False
                self.level = max(self.level, _peak(win))
        self.checked = max(self.checked, total)
        return max(0, total - self.heard) / SAMPLE_RATE

    def untyped(self, buf: np.ndarray, total: int) -> bool:
        """Speech in the audio not yet handed to the decoder (it would miss the Enter)."""
        return self.heard > total - len(buf)

    def due(self, delay_s: float, silence_s: float, ready: bool) -> bool:
        """True once per silence, when it has lasted delay_s and there is text to send."""
        if self.fired or not ready or silence_s < delay_s:
            return False
        self.fired = True
        return True


def speech_frames(win: np.ndarray, ref: np.ndarray | None, level: float) -> np.ndarray:
    """Voice detection on a short window. Silero normalises its input to its own peak, which
    would blow room noise up to speech level in a silent window, so it is scaled by the speech
    heard earlier in the take (`level`) when that is louder (vad.Silero.speech_frames `floor`)."""
    from . import engine
    if engine.silero is not None:
        try:
            return engine.silero.speech_frames(win, FRAME, floor=level)
        except Exception:
            engine.log.exception("Silero VAD failed; using the energy rule")
    return engine._energy_frames(win, ref)
