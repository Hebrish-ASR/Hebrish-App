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


def test_disk_error_ends_the_file_without_raising(monkeypatch, tmp_path):
    """Disk full inside the audio callback used to raise there, which kills the stream."""
    t = _tape(monkeypatch, tmp_path)
    _feed(t, np.full(1600, 0.1, np.float32))

    class Full:
        def __init__(self, f):
            self.f = f

        def write(self, b):
            raise OSError(122, "Disk quota exceeded")

        def __getattr__(self, k):
            return getattr(self.f, k)
    t._f = Full(t._f)
    _feed(t, np.full(1600, 0.1, np.float32))      # must not raise
    assert t.error is not None and t.seconds == 0.1
    _feed(t, np.full(1600, 0.1, np.float32))      # nothing more is written
    assert t.seconds == 0.1


def test_stalled_stream_is_noticed_and_reopened(monkeypatch, tmp_path):
    t = _tape(monkeypatch, tmp_path)
    opened = []
    monkeypatch.setattr(longform.TapeRecorder, "_open",
                        lambda self, dev: (opened.append(dev), setattr(self, "_last_block", longform.time.monotonic())))
    t._stream = object()
    _feed(t, np.full(1600, 0.1, np.float32))
    assert not t.stalled
    t._last_block -= longform.STALL_S + 1
    assert t.stalled
    t.reopen()
    assert opened == [""] and not t.stalled
    t.paused = True
    t._last_block -= longform.STALL_S + 1
    assert not t.stalled                            # a paused tape gets no blocks by design


def test_keep_moves_without_overwriting(monkeypatch, tmp_path):
    t = _tape(monkeypatch, tmp_path / "rec")
    _feed(t, np.full(1600, 0.1, np.float32))
    path = t.stop()
    dest = tmp_path / "kept"
    (dest).mkdir()
    (dest / path.name).write_bytes(b"older")
    got = longform.keep(path, str(dest))
    assert not path.exists() and got.parent == dest and got.name != path.name
    assert len(longform.load(got)) == 1600
