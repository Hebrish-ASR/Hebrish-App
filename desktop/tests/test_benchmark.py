"""Benchmarks: the figures, the reference file, the table, the report and the window."""

import hashlib
import os
import sys
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hebrish import benchmark  # noqa: E402
from hebrish.audio import SAMPLE_RATE  # noqa: E402
from hebrish.history import History  # noqa: E402


class FakeEngine:
    streaming, threads, load_s, loaded_dir = False, 4, 1.5, "x"

    def __init__(self, pieces=("hello there", "shalom"), delay=0.02):
        self.pieces, self.delay = pieces, delay
        self.stats, self.last_progress = [], (0, 1)

    def transcribe_chunks(self, samples, cancel=None, record=True):
        assert record is False                    # a long file must not flush Diagnostics' records
        for p in self.pieces:
            if cancel is not None and cancel.is_set():
                return
            time.sleep(self.delay)
            yield p


def row(**kw):
    out, _ = benchmark.measure(FakeEngine(), np.zeros(SAMPLE_RATE * 2, np.float32))
    return {"at": 1762340000.0, "mode": "file", "file_name": "secret-meeting.mp3", "file_sha256": "ab",
            "gpu_accel": 0, "cpu_name": "Test CPU", "model": "Sabich", **out, **kw}


def test_measure_figures():
    out, text = benchmark.measure(FakeEngine(), np.zeros(SAMPLE_RATE * 2, np.float32))
    assert text == "hello there shalom"
    assert out["audio_s"] == 2 and out["words"] == 3 and out["disturbed"] == 0
    assert out["rtf"] == pytest.approx(out["inference_s"] / 2, abs=1e-3)
    assert out["speed_x"] == pytest.approx(2 / out["inference_s"], rel=0.02)
    assert 0 < out["first_text_s"] <= out["inference_s"]


def test_known_length_wins_over_samples():
    out, _ = benchmark.measure(FakeEngine(), np.zeros(SAMPLE_RATE, np.float32), audio_s=100.0)
    assert out["audio_s"] == 100


def test_cancelled_run_is_none():
    c = threading.Event()
    c.set()
    assert benchmark.measure(FakeEngine(), np.zeros(SAMPLE_RATE, np.float32), cancel=c) is None


def test_another_decode_marks_the_run():
    e = FakeEngine()
    real = e.transcribe_chunks

    def chunks(*a, **k):
        e.stats.append({"at": time.time()})
        yield from real(*a, **k)
    e.transcribe_chunks = chunks
    assert benchmark.measure(e, np.zeros(SAMPLE_RATE, np.float32))[0]["disturbed"] == 1


def test_sampler_sees_load_shorter_than_an_interval():
    s = benchmark.Sampler(every_s=10)
    s.start()
    t = time.monotonic()
    while time.monotonic() - t < 0.05:
        pass
    out = s.stop()
    assert out["cpu_avg_cores"] > 0.5 and out["cpu_peak_pct"] >= out["cpu_avg_pct"]
    if sys.platform.startswith("linux"):
        assert out["ram_peak_mb"] >= out["ram_avg_mb"] > 0


def test_sha256_file(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"x" * 3_000_000)
    assert benchmark.sha256_file(str(f)) == hashlib.sha256(b"x" * 3_000_000).hexdigest()


def test_table_keeps_figures_only(tmp_path):
    h = History(tmp_path / "h.db")
    h.add_benchmark(row(transcript="never stored"))
    r = h.benchmarks()[0]
    assert "transcript" not in r and r["model"] == "Sabich" and r["gpu_accel"] == 0


def test_report_is_markdown_without_the_file_name():
    text = benchmark.report(row())
    assert text.startswith("## Hebrish benchmark, ") and "| Real-time factor | " in text
    assert "secret-meeting" not in text and "GPU acceleration | no" in text
    assert "aren't clean" in benchmark.report(row(disturbed=1))


def test_window_saves_a_run(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QWidget
    from hebrish.ui.benchmark import BenchmarkWindow
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(benchmark, "system_info", lambda e: {"model": "Sabich", "gpu_accel": 0})
    monkeypatch.setattr("hebrish.audio.load_file", lambda p: np.zeros(SAMPLE_RATE * 2, np.float32))
    f = tmp_path / "take.wav"
    f.write_bytes(b"not read: load_file is patched")
    ctl = SimpleNamespace(engine=FakeEngine(), state="idle", history=History(tmp_path / "h.db"), cfg={})
    host = QWidget()
    w = BenchmarkWindow(host, ctl)
    assert w.transcript.isHidden()
    w.run_file(str(f))
    end = time.monotonic() + 5
    while not ctl.history.benchmarks() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    r = ctl.history.benchmarks()[0]
    assert r["mode"] == "file" and r["file_name"] == "take.wav"
    assert "Hebrish benchmark" in w.result.toPlainText()
    assert w.transcript.isHidden() and w.transcript.toPlainText() == "hello there shalom"
    w.toggle.setChecked(True)
    assert not w.transcript.isHidden() and w.table.rowCount() == 1
