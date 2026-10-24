"""Transcription Mode's recorder (longform.py): written to disk as it goes, readable after a
crash, gain before the meter and the file, pause keeps the file."""

import wave

import numpy as np

from hebrish import audio, longform


def _tape(monkeypatch, tmp_path):
    monkeypatch.setattr(longform, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(longform.TapeRecorder, "_open", lambda self, dev: setattr(self, "_device", dev))
    monkeypatch.setattr(longform.TapeRecorder, "_close_stream", lambda self: None)
    t = longform.TapeRecorder()
    t.start("")
    return t


def _feed(t, x):
    t._cb(x.reshape(-1, 1).astype(np.float32), len(x), None, None)


def test_written_as_it_goes_and_recoverable(monkeypatch, tmp_path):
    t = _tape(monkeypatch, tmp_path)
    tone = 0.25 * np.sin(np.arange(audio.SAMPLE_RATE) / 10).astype(np.float32)
    _feed(t, tone)
    _feed(t, tone)
    t._f.flush()                       # a crash now: header may lag, data is on disk
    path = t.path
    assert longform.recover(path) == 2.0
    with wave.open(str(path)) as w:
        assert w.getframerate() == audio.SAMPLE_RATE and w.getnframes() == 2 * audio.SAMPLE_RATE
    assert path in longform.leftovers()
    t.stop()
    got = longform.load(path)
    assert len(got) == 2 * audio.SAMPLE_RATE
    assert abs(float(np.max(got)) - 0.25) < 1e-3


def test_gain_applies_before_meter_and_file(monkeypatch, tmp_path):
    t = _tape(monkeypatch, tmp_path)
    t.gain_db = 20 * np.log10(2)       # x2
    _feed(t, np.full(1600, 0.3, np.float32))
    assert abs(t.peak - 0.6) < 1e-4 and t.clipped_at == 0.0
    _feed(t, np.full(1600, 0.6, np.float32))      # 1.2 after gain: clipped in the file
    assert t.clipped_at > 0
    path = t.stop()
    got = longform.load(path)
    assert abs(got[0] - 0.6) < 1e-3 and got[-1] >= 0.999


def test_input_clipping_lights_lamp_even_with_gain_down(monkeypatch, tmp_path):
    t = _tape(monkeypatch, tmp_path)
    t.gain_db = -12
    _feed(t, np.full(1600, 1.0, np.float32))
    assert t.clipped_at > 0 and t.peak < 0.3


def test_pause_keeps_file_discard_removes_it(monkeypatch, tmp_path):
    t = _tape(monkeypatch, tmp_path)
    _feed(t, np.zeros(1600, np.float32))
    t.pause()
    assert t.paused and t.active and t.path.exists()
    t.resume()
    _feed(t, np.zeros(1600, np.float32))
    assert t.seconds == 0.2
    path = t.path
    t.discard()
    assert not path.exists() and not t.active


def test_empty_recording_leaves_nothing(monkeypatch, tmp_path):
    t = _tape(monkeypatch, tmp_path)
    assert t.stop() is None
    assert longform.leftovers() == []
