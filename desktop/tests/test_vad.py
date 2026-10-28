"""Silero VAD add-on (vad.py): engine uses it for speech frames when set, and falls back to the
energy rule if it fails. The model itself is exercised only when HEBRISH_SILERO points at it."""

import os
from pathlib import Path

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


def test_installed_needs_the_pinned_size(tmp_path, monkeypatch):
    from hebrish import model_store
    monkeypatch.setattr(model_store, "ROOT", tmp_path)
    assert vad.installed() is None
    (tmp_path / vad.MODEL_ID).mkdir()
    (tmp_path / vad.MODEL_ID / vad.FILE).write_bytes(b"x")
    assert vad.installed() is None


@pytest.mark.skipif(not os.environ.get("HEBRISH_SILERO"), reason="set HEBRISH_SILERO to silero_vad.onnx")
def test_silero_ignores_steady_noise_and_silence():
    s = vad.Silero(Path(os.environ["HEBRISH_SILERO"]))
    rng = np.random.default_rng(0)
    for level in (0.0, 0.002, 0.02):
        noise = (rng.standard_normal(engine.SAMPLE_RATE * 5) * level).astype(np.float32)
        assert not s.speech_frames(noise, engine.FRAME).any()
