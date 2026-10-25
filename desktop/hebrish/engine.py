"""sherpa-onnx recognizer for the installed fine-tune: offline (Parakeet: Sabich, Jachnun, stock)
or streaming (Nemotron: Shakshuka, 0.7.0)."""

import logging
import re
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np

from .audio import SAMPLE_RATE

log = logging.getLogger(__name__)

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
# A piece of a take (live pieces and the last one, decoded after Stop) is judged against the levels
# of the take so far (`ref`), not its own (R-2026-10-25-3). Alone, the few seconds spoken just
# before Stop were often too short and soft to pass: their loudest frames stayed under VAD_QUIET
# on a headset at its default gain (B-46: speech around -41 dBFS), so the last words were dropped
# and nothing said so. With `ref`, a frame is speech when it clears the usual rule on the take's
# levels or stands VAD_REL_DB above the take's noise floor, and in any case VAD_DEAD (a dead or
# muted mic). Not yet measured against the benchmark. A quiet whole take gets the same rule (B-46).
VAD_REL_DB = 15
VAD_DEAD = 10 ** (-70 / 20)
REF_S = 30                 # how much of the take before a piece serves as its `ref`


def _frame_rms(x: np.ndarray) -> np.ndarray:
    n = len(x) // FRAME
    return np.sqrt((x[: n * FRAME].reshape(n, FRAME) ** 2).mean(axis=1))


def _speech_frames(x: np.ndarray, ref: np.ndarray | None = None) -> np.ndarray:
    rms = _frame_rms(x)
    if not len(rms):
        return rms > 1
    levels = rms if ref is None or len(ref) < FRAME else np.concatenate([_frame_rms(ref), rms])
    floor, loud = np.percentile(levels, 10), np.percentile(levels, 95)
    # the 5th percentile: a take spoken with few pauses has its noise floor in under 10% of frames
    rel = np.percentile(levels, 5) * 10 ** (VAD_REL_DB / 20)
    # B-46 (2026-10-25): a quiet take is speech when it rises VAD_REL_DB over its own floor. Up to
    # 1.002 any take whose loudest frames stayed under VAD_QUIET was "no speech", which on a headset
    # at its default gain (speech about -41 dBFS, floor -76) dropped real takes. Quiet and flat
    # (silence, a muted mic) is still nothing.
    if loud < VAD_QUIET and loud < rel:
        return np.zeros(len(rms), bool)
    gate = max(VAD_ABS, floor + (loud - floor) / 3)
    if levels is not rms or loud < VAD_QUIET:
        gate = max(VAD_DEAD, min(gate, rel))
    return rms > gate


def has_speech(x: np.ndarray, ref: np.ndarray | None = None) -> bool:
    return int(_speech_frames(x, ref).sum()) * FRAME >= VAD_MIN_SPEECH_S * SAMPLE_RATE


def shorten_silences(x: np.ndarray, ref: np.ndarray | None = None) -> np.ndarray:
    """Cut every non-speech run longer than VAD_LONG_S down to VAD_KEEP_S (keeping its two ends)."""
    sp = _speech_frames(x, ref)
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
# hold the start of a word), once the take holds `interval` seconds. A pause of LIVE_BREAK_S or more
# (a sentence end, or stopping to think) cuts as soon as the take holds LIVE_MIN_S and some speech
# (0.7.1: Daniel, 2026-10-22, text came too late and "the insertion breaks don't make sense").
# With no pause by interval + LIVE_FORCE_S, cut at the quietest 100 ms.
LIVE_SEARCH_S = 6
LIVE_GUARD_S = 0.3
LIVE_PAUSE_S = 0.6      # 0.3 cut inside sentences: 24 vs 10 errors per 786 words at 15 s
LIVE_BREAK_S = 1.0
LIVE_MIN_S = 2.0
LIVE_FORCE_S = 15


def live_split(x: np.ndarray, interval_s: float) -> tuple[int, float] | None:
    """(sample index to cut a live take at, length of the pause cut in s; 0 for a forced cut),
    or None to keep listening. Quiet frames as in stretch_pauses; the cut is the middle of the
    longest quiet run, so both halves keep some silence."""
    sr, n = SAMPLE_RATE, len(x)
    if n < min(interval_s, LIVE_MIN_S) * sr:
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
    pause, cut = best * FRAME / sr, (a + b) // 2 * FRAME
    if n >= interval_s * sr and pause >= LIVE_PAUSE_S:
        return cut, pause
    if pause >= LIVE_BREAK_S and a > 0 and has_speech(x[:cut]):
        return cut, pause
    if n >= (interval_s + LIVE_FORCE_S) * sr:
        win = sr // 10
        frames = x[lo:hi][: (hi - lo) // win * win].reshape(-1, win)
        return lo + int(np.argmin((frames ** 2).mean(axis=1))) * win + win // 2, 0.0
    return None


def live_cut(x: np.ndarray, interval_s: float) -> int | None:
    """live_split's cut alone."""
    r = live_split(x, interval_s)
    return r[0] if r else None


# Seams between live pieces (0.7.1). Parakeet decodes each piece on its own, so a piece cut at a
# pause inside a sentence comes back as a sentence: "...after the kids are asleep." then "So
# nothing else is running..." (2026-10-22 pacing run, docs/maintaining.md). The full stop of a
# piece cut at a pause shorter than LIVE_BREAK_S is therefore held back with the space after it;
# if the next piece starts with one of these words, the sentence goes on ("asleep so nothing"),
# otherwise the full stop is pasted in front of it, as before.
#
# Context (0.7.6, Daniel 2026-10-23: sentences "reaching sentence boundaries a bit too prematurely",
# "capitals in the middle of sentences"). In real dictation the pause rules above still gave about
# 1.2 capitalised function words a minute mid-sentence ("kind of Dumping", "the hardest part is. Is
# the room noise?"), most after a piece that ended with no mark at all, where nothing was held. So
# each live piece cut at a pause is decoded after the last CONTEXT_S of the piece before it, and
# only the words heard after that point are kept (token timestamps; the cut is the middle of a
# pause, so no word straddles it). The model then sees the sentence go on: it writes the first word
# in the case it has mid-sentence, and its punctuation at the seam replaces the guess the previous
# piece made without hearing what followed. Measured: desktop/docs/maintaining.md, "Context at the seams".
CONTEXT_S = 3.0
CONTINUES = frozenset("""and or but so because since which who whom whose that than then to of for
    with without in on at by from as if when while where whether after before until till unless
    about into onto like plus nor yet although though""".split())


def hold_stop(text: str, pause_s: float | None) -> bool:
    """Hold back the full stop at the end of a live piece (pause_s None: the last piece). Since 0.7.6
    every pause length holds it: the next piece is decoded after this one's audio
    (Engine.transcribe_after), which decides. Up to 0.7.5 only pauses under LIVE_BREAK_S held."""
    return pause_s is not None and text.endswith(".") and not text.endswith("..")


def after_held_stop(text: str, stop: bool | None = None) -> str:
    """What to paste for text when the previous piece's full stop (and space) was held back.
    stop: whether the model, decoding the end of the previous piece together with this one, ended
    it with a sentence mark (Engine.transcribe_after); None when it had no context, and then the
    CONTINUES rule decides, as in 0.7.1-0.7.5."""
    if stop is not None:
        return ". " + text[:1].upper() + text[1:] if stop else " " + text
    first = text.split(" ", 1)[0]
    if first[:1].islower():                 # the model already heard it as a continuation
        return " " + text
    if first.lower().strip(",;:") in CONTINUES and not first[1:2].isupper():
        return " " + text[:1].lower() + text[1:]
    return ". " + text


# How much text one paste of a streaming take holds (config `stream_release`, 0.7.1). Daniel,
# 2026-10-22: a paste every word or two "is very jarring", and each paste flickers the screen; too
# long a wait and "you're there wondering if it's actually working". Rule: (sentence marks, clause
# marks, fewest words before a clause mark, pause s, longest hold s). Release up to the last
# sentence mark at once, and up to a clause mark once that makes at least that many words;
# everything once the text has stopped growing for `pause` s (the speaker paused); whole words
# once the oldest held word is `hold` s old. "word" releases every whole word, as 0.7.0 did.
# Measured on six clips read back to back (2026-10-22, docs/maintaining.md): "phrase" pastes
# 3-12 words about every 2-3 s while you speak, and a sentence's end as soon as it is heard.
STREAM_RELEASE = {
    "word": None,
    "phrase": (".?!", ",;:", 4, 0.8, 2.5),
    "sentence": (".?!", "", 0, 1.2, 6.0),
}
_MARK_END = r"(?=\s|$)"     # a mark counts when a space (or nothing yet) follows it


class LiveStream:
    """One streaming take (Shakshuka): feed audio as it is recorded, get back the new text.

    Cache-aware streaming with greedy decoding only ever appends to its result, so text is
    inserted once and never revised (measured 2026-10-22 on two code-switched clips: no
    update rewrote earlier text; research/streaming-revision). Because it only appends, any
    prefix of the result can be released: the next release continues it exactly, even
    mid-word. The result arrives in BPE pieces ("ask Av", "i for"), so without a pause only
    text up to the last space is released while the take runs; finish() releases the rest.
    `release` (STREAM_RELEASE) holds words back so they go out a phrase or sentence at a time."""

    def __init__(self, engine: "Engine", release: str = "phrase"):
        self._engine = engine
        with engine._lock:
            self._s = engine._rec.create_stream()
        self.sent = ""
        self.audio_s = 0.0
        self.decode_s = 0.0
        self._rule = STREAM_RELEASE.get(release, STREAM_RELEASE["phrase"])
        self._text = ""          # the whole result so far
        self._grew_at = 0.0      # when it last grew
        self._held_at = None     # when the oldest unreleased text appeared

    def _decode(self, samples: np.ndarray, last: bool) -> str:
        eng = self._engine
        with eng._lock:
            if eng._rec is None:
                raise RuntimeError("Model not loaded")
            t0 = time.monotonic()
            if len(samples):
                self._s.accept_waveform(SAMPLE_RATE, samples)
            if last:
                self._s.accept_waveform(SAMPLE_RATE, np.zeros(int(TAIL_PAD_S * SAMPLE_RATE), np.float32))
                self._s.input_finished()
            while eng._rec.is_ready(self._s):
                eng._rec.decode_stream(self._s)
            text = eng._rec.get_result(self._s).lstrip()
            self.decode_s += time.monotonic() - t0
        self.audio_s += len(samples) / SAMPLE_RATE
        return text

    def _ready(self, text: str, last: bool, now: float) -> str:
        """The prefix of text to have released by now. Releases end on a word or mark, never on
        a space, so each later one starts with its space and none is a lone space."""
        if text != self._text:
            self._text, self._grew_at = text, now
        if last:
            return text
        pending = text[len(self.sent):]
        if not pending.strip():
            return self.sent
        if self._held_at is None:
            self._held_at = now
        if self._rule is None:
            return text[: text.rfind(" ") + 1]
        stops, clauses, min_words, pause, hold = self._rule
        if now - self._grew_at >= pause:
            return text.rstrip()
        cut = 0
        for m in re.finditer(f"[{re.escape(stops)}]{_MARK_END}", pending):
            cut = m.end()
        if clauses:
            for m in re.finditer(f"[{re.escape(clauses)}]{_MARK_END}", pending):
                if m.end() > cut and len(pending[: m.end()].split()) >= min_words:
                    cut = m.end()
        if now - self._held_at >= hold:
            # whole words, but keep the last two back so a sentence's last word doesn't follow
            # on its own half a second later (" table.")
            spaces = [m.start() for m in re.finditer(" ", pending.rstrip())]
            cut = max(cut, spaces[-2] if len(spaces) >= 3 else 0)
        return self.sent + pending[:cut] if cut > 0 else self.sent

    def _release(self, text: str, last: bool, now: float | None = None) -> str:
        now = time.monotonic() if now is None else now
        ready = self._ready(text, last, now)
        if len(ready) <= len(self.sent):
            return ""
        if not ready.startswith(self.sent):
            # Not seen with greedy decoding; if a runtime ever revises, keep what is on screen
            # and append nothing that would contradict it.
            log.warning("streaming result changed earlier text: %r -> %r", self.sent[-40:], ready[-40:])
            return ""
        new, self.sent = ready[len(self.sent):], ready
        # What is still held started arriving about now.
        self._held_at = None if not text[len(ready):].strip() else now
        return new

    def feed(self, samples: np.ndarray) -> str:
        """Text released since the last call (STREAM_RELEASE), or ""."""
        return self._release(self._decode(samples, last=False), last=False)

    def finish(self, samples: np.ndarray) -> str:
        """The last of the audio, then the rest of the text (no trailing space)."""
        out = self._release(self._decode(samples, last=True), last=True)
        eng = self._engine
        eng.stats.append({"at": time.time(), "audio_s": self.audio_s, "decode_s": self.decode_s,
                          "tokens": len(eng._rec.get_result_all(self._s).tokens) if eng._rec else 0,
                          "words": len(self.sent.split()), "threads": eng.threads})
        return out


class Engine:
    def __init__(self):
        self._rec = None
        self.streaming = False            # an OnlineRecognizer (Shakshuka) is loaded
        self._dir: Path | None = None
        self._lock = threading.Lock()
        self.last_progress = (0, 1)       # (samples done, total) of the current transcribe_chunks
        # Diagnostics tab: one record per decoded piece, newest last. audio_s excludes the
        # tail pad; decode_s is the sherpa-onnx accept + decode time; tokens = output tokens.
        self.stats: deque[dict] = deque(maxlen=200)
        self.load_s = 0.0
        self.threads = 0

    @property
    def loaded_dir(self) -> Path | None:
        return self._dir

    def load(self, model_dir: Path, num_threads: int = 4, feature_dim: int = 128, streaming: bool = False):
        """feature_dim comes from the catalogue variant (128 for the 0.6B models, 80 for
        Sabich-Parakeet-110M). sherpa-onnx also reads it from the encoder metadata, which wins:
        the 110M decoded the same clip identically with 80 and 128 (2026-10-21, sherpa-onnx 1.13.8).
        streaming: the variant's engine is sherpa_online_transducer (Shakshuka, exported at
        560 ms chunks; the chunk size is in the encoder metadata, not passed here)."""
        import sherpa_onnx
        t0 = time.monotonic()
        files = dict(encoder=str(model_dir / "encoder.int8.onnx"),
                     decoder=str(model_dir / "decoder.int8.onnx"),
                     joiner=str(model_dir / "joiner.int8.onnx"),
                     tokens=str(model_dir / "tokens.txt"),
                     decoding_method="greedy_search", num_threads=num_threads,
                     sample_rate=SAMPLE_RATE, feature_dim=feature_dim, provider="cpu")
        if streaming:
            rec = sherpa_onnx.OnlineRecognizer.from_transducer(**files)
        else:
            rec = sherpa_onnx.OfflineRecognizer.from_transducer(model_type="nemo_transducer", **files)
        with self._lock:
            self._rec, self._dir, self.streaming = rec, model_dir, streaming
        self.threads = num_threads
        self.transcribe(np.zeros(SAMPLE_RATE, np.float32), record=False)      # warm-up
        self.load_s = time.monotonic() - t0

    def unload(self):
        with self._lock:
            self._rec, self._dir, self.streaming = None, None, False

    def live(self, release: str = "phrase") -> LiveStream:
        """A streaming take (only when self.streaming); release: a STREAM_RELEASE key."""
        if self._rec is None:
            raise RuntimeError("Model not loaded")
        return LiveStream(self, release)

    def _decode_piece(self, x: np.ndarray):
        """One piece, already padded: (text, tokens). Caller holds the lock."""
        s = self._rec.create_stream()
        s.accept_waveform(SAMPLE_RATE, x)
        if self.streaming:
            s.input_finished()
            while self._rec.is_ready(s):
                self._rec.decode_stream(s)
            return self._rec.get_result(s).strip(), len(self._rec.get_result_all(s).tokens)
        self._rec.decode_stream(s)
        return s.result.text.strip(), len(s.result.tokens)

    def transcribe(self, samples: np.ndarray, vad: bool = False, record: bool = True,
                   ref: np.ndarray | None = None) -> str:
        return " ".join(self.transcribe_chunks(samples, vad=vad, record=record, ref=ref))

    def _prepare(self, x: np.ndarray, vad: bool, ref: np.ndarray | None = None) -> np.ndarray:
        if vad:
            x = shorten_silences(x, ref)
        x = normalize(x)
        if not self.streaming:
            # Parakeet only. On Shakshuka it hurt 3 of 6 code-switched clips (a doubled
            # "tomorrow", a lost "ask Avi", a dropped full stop) and fixed none; without it the
            # whole-take text equals the live text (2026-10-22, desktop/docs/maintaining.md).
            x = stretch_pauses(x)
        return x

    def transcribe_after(self, samples: np.ndarray, context: np.ndarray | None, vad: bool = False,
                         record: bool = True, ref: np.ndarray | None = None) -> tuple[str, bool | None]:
        """A live piece decoded after the last CONTEXT_S of `context` (the audio just before it):
        (text of the piece alone, whether the model ended the context with a sentence mark). Falls
        back to transcribe (and None) without usable context: none, no speech in it, a streaming
        model, or a piece long enough to be split. `ref`: the take before this piece (voice
        detection judges the piece by the take's levels, REF_S)."""
        ctx = None if context is None else context[-int(CONTEXT_S * SAMPLE_RATE):]
        if (ctx is None or self.streaming or len(samples) > (PIECE_S + LIVE_FORCE_S) * SAMPLE_RATE
                or len(ctx) < MIN_TAKE_S * SAMPLE_RATE or not has_speech(ctx, ref)):
            return self.transcribe(samples, vad=vad, record=record, ref=ref), None
        if len(samples) < MIN_TAKE_S * SAMPLE_RATE or (vad and not has_speech(samples, ref)):
            return "", None
        ctx, x = self._prepare(ctx, vad, ref), self._prepare(samples, vad, ref)
        at = len(ctx) / SAMPLE_RATE
        pad = np.zeros(int(TAIL_PAD_S * SAMPLE_RATE), np.float32)
        with self._lock:
            if self._rec is None:
                raise RuntimeError("Model not loaded")
            t0 = time.monotonic()
            s = self._rec.create_stream()
            s.accept_waveform(SAMPLE_RATE, np.concatenate([ctx, x, pad]))
            self._rec.decode_stream(s)
            tokens, times = list(s.result.tokens), list(s.result.timestamps)
            took = time.monotonic() - t0
        k = next((i for i, t in enumerate(times) if t >= at), len(tokens))
        before, text = "".join(tokens[:k]).strip(), "".join(tokens[k:]).strip()
        if record:
            self.stats.append({"at": time.time(), "audio_s": len(samples) / SAMPLE_RATE,
                               "context_s": at, "decode_s": took, "tokens": len(tokens) - k,
                               "words": len(text.split()), "threads": self.threads})
        self.last_progress = (len(samples), len(samples))
        if not before:
            return text, None
        return text, before[-1] in ".?!"

    def transcribe_chunks(self, samples: np.ndarray, cancel=None, vad: bool = False, record: bool = True,
                          ref: np.ndarray | None = None):
        """Yield the text of each piece (split_points) as it is decoded. The lock is taken per
        piece, so a hotkey dictation can slip in between pieces of a long file. With vad, a
        take without speech yields nothing and long silences are shortened first (judged by
        `ref`'s levels too, when the samples are the end of a longer take)."""
        if len(samples) < MIN_TAKE_S * SAMPLE_RATE:
            return
        if vad and not has_speech(samples, ref):
            self.last_progress = (1, 1)
            return
        samples = self._prepare(samples, vad, ref)
        pad = np.zeros(int(TAIL_PAD_S * SAMPLE_RATE), np.float32)
        for a, b in split_points(samples):
            if cancel is not None and cancel.is_set():
                return
            with self._lock:
                if self._rec is None:
                    raise RuntimeError("Model not loaded")
                t0 = time.monotonic()
                text, tokens = self._decode_piece(np.concatenate([samples[a:b], pad]))
                took = time.monotonic() - t0
            if record:
                self.stats.append({"at": time.time(), "audio_s": (b - a) / SAMPLE_RATE,
                                   "decode_s": took, "tokens": tokens,
                                   "words": len(text.split()), "threads": self.threads})
            self.last_progress = (b, len(samples))
            if text:
                yield text
