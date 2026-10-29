"""Silero VAD add-on (vad.py): engine uses it for speech frames when set, and falls back to the
energy rule if it fails; the bundled model is the pinned file and ignores steady noise."""

import numpy as np
import pytest
from hebrish import engine, vad


class Fake:
    def __init__(self, fail=False):
        self.fail = fail

    def speech_frames(self, x, frame):
        if self.fail:
            raise RuntimeError("boom")
        return np.ones(len(x) // frame, bool)


def test_engine_asks_silero_when_set(monkeypatch):
    x = np.zeros(engine.SAMPLE_RATE, np.float32)           # silence: the energy rule says no speech
    assert not engine.has_speech(x)
    monkeypatch.setattr(engine, "silero", Fake())
    assert engine.has_speech(x)


def test_engine_falls_back_to_energy_when_silero_fails(monkeypatch):
    monkeypatch.setattr(engine, "silero", Fake(fail=True))
    assert not engine.has_speech(np.zeros(engine.SAMPLE_RATE, np.float32))


def test_bundled_model_is_the_pinned_file():
    import hashlib
    assert vad.installed() is not None
    assert hashlib.sha256(vad.BUNDLED.read_bytes()).hexdigest() == vad.SHA256


def test_silero_ignores_steady_noise_and_silence():
    pytest.importorskip("sherpa_onnx")                     # Linux CI has no sherpa-onnx (Windows CI runs it)
    s = vad.Silero(vad.BUNDLED)
    rng = np.random.default_rng(0)
    for level in (0.0, 0.002, 0.02):
        noise = (rng.standard_normal(engine.SAMPLE_RATE * 5) * level).astype(np.float32)
        assert not s.speech_frames(noise, engine.FRAME).any()


def test_transcribe_chunks_runs_voice_detection_once(monkeypatch):
    """One pass over the take, shared by has_speech and shorten_silences (2026-10-29)."""
    calls = []

    class Count(Fake):
        def speech_frames(self, x, frame):
            calls.append(len(x))
            return super().speech_frames(x, frame)
    monkeypatch.setattr(engine, "silero", Count())
    e = engine.Engine()
    with pytest.raises(RuntimeError):                      # no model: fails at the first piece
        list(e.transcribe_chunks(np.full(5 * engine.SAMPLE_RATE, 0.1, np.float32), vad=True))
    assert len(calls) == 1
