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


def test_noise_filter_maps_to_silero_threshold():
    assert vad.threshold(50) == pytest.approx(vad.THRESHOLD)   # 50 is the old fixed value
    assert vad.threshold(0) == pytest.approx(0.2) and vad.threshold(100) == pytest.approx(0.8)
    assert vad.threshold(-5) == vad.threshold(0) and vad.threshold(500) == vad.threshold(100)
    assert vad.threshold(vad.FILTER_DEFAULT) > vad.THRESHOLD   # the default is stricter


def test_default_noise_filter_matches_config():
    from hebrish import config
    assert config.DEFAULTS["vad_noise_filter"] == vad.FILTER_DEFAULT


def test_set_level_rebuilds_the_detector():
    pytest.importorskip("sherpa_onnx")
    s = vad.Silero(vad.BUNDLED)
    s.speech_frames(np.zeros(16000, np.float32) + 0.1, 320)
    s.set_level(100)
    assert s._det is None and s._cfg.silero_vad.threshold == pytest.approx(0.8)



# Custom VAD model (vad_custom_path, 2026-11-19): a Silero-format file replaces the bundled one;
# a file that won't load never does.
def test_custom_path_default_is_empty():
    from hebrish import config
    assert config.DEFAULTS["vad_custom_path"] == ""


def test_custom_model_is_loaded_and_used(tmp_path):
    pytest.importorskip("sherpa_onnx")
    mine = tmp_path / "my-silero.onnx"
    mine.write_bytes(vad.BUNDLED.read_bytes())           # a copy: not the pinned path, no SHA check
    assert vad.check(mine) is None
    sel = vad.select(str(mine))
    assert sel.custom and sel.path == mine and sel.error is None
    assert vad.Silero(sel.path).path == mine             # the detector is built from it


def test_garbage_custom_model_falls_back_to_bundled(tmp_path):
    pytest.importorskip("sherpa_onnx")
    bad = tmp_path / "bad.onnx"
    bad.write_bytes(b"not an onnx file")
    assert vad.check(bad)
    sel = vad.select(str(bad))
    assert not sel.custom and sel.path == vad.BUNDLED and sel.error


def test_missing_or_empty_custom_path(tmp_path):
    gone = vad.select(str(tmp_path / "gone.onnx"))
    assert gone.path == vad.BUNDLED and not gone.custom and "not found" in gone.error
    none = vad.select("")
    assert none.path == vad.BUNDLED and not none.custom and none.error is None
