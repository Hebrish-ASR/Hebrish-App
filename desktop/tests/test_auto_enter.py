"""Press Enter after silence (R-2026-10-31-1): the silence clock (hebrish.auto_enter) and its
voice detection. The worker's Enter marker is tested in test_live.py."""

import numpy as np
import pytest

from hebrish import auto_enter, engine, vad
from hebrish.auto_enter import SilenceClock

SR = engine.SAMPLE_RATE
rng = np.random.default_rng(1)
TICK = SR // 2                    # Controller._live_tick runs every 500 ms


def speech(s):
    return (rng.standard_normal(int(s * SR)) * 0.2).astype(np.float32)


def silence(s):
    return (rng.standard_normal(int(s * SR)) * 0.002).astype(np.float32)


def energy(win, ref, level):
    return engine._energy_frames(win, ref)


def feed(clock, take, consumed=0, frames=energy):
    """Run the clock tick by tick over `take`; return the silence after each tick."""
    out = []
    for end in range(TICK, len(take) + 1, TICK):
        out.append(clock.update(take[consumed:end], end, frames))
    return out


def test_silence_counts_from_the_last_speech():
    take = np.concatenate([speech(2), silence(9)])
    s = feed(SilenceClock(), take)
    assert s[3] < 0.5                                   # still talking at 2 s
    assert 8.5 <= s[-1] <= 9.3                          # 9 s of silence, give or take a frame and the seam


def test_due_once_per_silence_and_again_after_speech():
    c = SilenceClock()
    assert not c.due(8, 7.9, True)
    assert not c.due(8, 9, False)                       # nothing to send: wait, don't use it up
    assert c.due(8, 9, True)
    assert not c.due(8, 12, True)                       # once per silence
    take = np.concatenate([speech(1), silence(1), speech(1)])
    assert feed(c, take)[-1] < 0.5                      # speech resumes: the silence starts again
    assert c.due(8, 9, True)                            # and the next one can fire


def test_untyped_speech_is_seen_until_consumed():
    c = SilenceClock()
    take = np.concatenate([speech(1), silence(3)])
    feed(c, take)
    assert c.untyped(take, len(take))                   # the speech is still in the recorder
    assert not c.untyped(take[len(take):], len(take))   # handed to the decoder


def test_a_resumed_take_starts_the_silence_again():
    c = SilenceClock()
    take = np.concatenate([speech(1), silence(6)])
    assert feed(c, take)[-1] > 5
    c.reset(len(take))                                  # resumed after a pause
    assert c.update(take, len(take) + 0, energy) == 0


def test_audio_consumed_before_the_clock_saw_it_counts_as_speech():
    # turned on mid-take: what live insertion already took is assumed to be speech
    c = SilenceClock()
    take = silence(10)
    assert c.update(take[8 * SR:], len(take), energy) == pytest.approx(2.0, abs=0.01)


def test_room_noise_alone_is_never_speech_for_the_energy_rule():
    c = SilenceClock()
    s = feed(c, silence(10))
    assert s[-1] == pytest.approx(10.0, abs=0.01)


def test_silero_judges_a_quiet_window_by_the_takes_speech_level():
    pytest.importorskip("sherpa_onnx")                  # Linux CI has no sherpa-onnx
    s = vad.Silero(vad.BUNDLED)
    hum = (rng.standard_normal(SR) * 0.001).astype(np.float32)     # -60 dBFS room noise
    assert not s.speech_frames(hum, engine.FRAME, floor=0.5).any()


def test_speech_frames_falls_back_to_energy_when_silero_fails(monkeypatch):
    class Broken:
        def speech_frames(self, x, frame, floor=0.0):
            raise RuntimeError("boom")
    monkeypatch.setattr(engine, "silero", Broken())
    assert not auto_enter.speech_frames(silence(1), None, 0.0).any()
    assert auto_enter.speech_frames(speech(1), None, 0.0).any()


def _ticker(take_audio, typed, monkeypatch):
    """Controller._auto_enter_tick on a fake controller; returns (ctl, recorder state)."""
    pytest.importorskip("PySide6")
    import queue
    from types import SimpleNamespace
    from hebrish.ui.app import Controller
    monkeypatch.setattr(engine, "silero", None)             # the energy rule: no model needed
    rec = {"buf": take_audio}

    def consume(n):
        out, rec["buf"] = rec["buf"][:n], rec["buf"][n:]
        return out
    ctl = SimpleNamespace(cfg={"auto_enter_s": 2}, _typed=typed, _take=3, _jobs=queue.Queue(),
                          _silence=SilenceClock(), recorder=SimpleNamespace(consume=consume))
    tick = Controller._auto_enter_tick.__get__(ctl)
    return ctl, rec, tick


def test_tick_hands_over_the_last_words_then_the_enter(monkeypatch):
    take = np.concatenate([speech(1.5), silence(2.5)])
    ctl, rec, tick = _ticker(take, False, monkeypatch)
    took = False
    for end in range(TICK, len(take) + 1, TICK):
        took = tick(rec["buf"][: end - (len(take) - len(rec["buf"]))], end) or took
    assert took
    piece, marker = ctl._jobs.get_nowait(), ctl._jobs.get_nowait()
    # everything recorded up to the tick that fired (2 s after the speech): the words and the silence
    assert piece[0] == 3 and piece[2] is False and piece[3] >= 2
    assert len(piece[1]) + len(rec["buf"]) == len(take) and len(piece[1]) >= 3.5 * SR
    assert marker == (3, None, False, ctl._silence.heard)
    assert ctl._jobs.empty()


def test_tick_does_nothing_without_text_or_speech(monkeypatch):
    take = silence(4)
    ctl, rec, tick = _ticker(take, False, monkeypatch)
    for end in range(TICK, len(take) + 1, TICK):
        tick(take[:end], end)
    assert ctl._jobs.empty()


def test_tick_sends_typed_text_once(monkeypatch):
    take = silence(6)
    ctl, rec, tick = _ticker(take, True, monkeypatch)     # text typed earlier in the take
    for end in range(TICK, len(take) + 1, TICK):
        tick(take[:end], end)
    assert ctl._jobs.qsize() == 1 and ctl._jobs.get_nowait()[1] is None
