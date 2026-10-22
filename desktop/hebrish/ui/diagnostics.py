"""Diagnostics tab: how fast inference is on this machine, to judge whether the model is the
right size for it (Daniel, 2026-10-21: "useful in terms of seeing if the model is suitably
sized, because we might want to have even a smaller quantization").

Numbers come from Engine.stats (one record per decoded piece: audio seconds, decode seconds,
output tokens) and Controller.latencies (stop -> text inserted), averaged over the last N.
Run benchmark decodes the bundled voice prompts (~10 s: 6 s of speech, 0.5 s gaps) three times, so there
are numbers before anyone has dictated.
"""

import json
import os
import platform
import sys
import threading
import time
import wave

import numpy as np
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QScrollArea, QFrame, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from .. import __version__, audio, model_store
from ..inserter import copy_to_clipboard

WINDOWS = [(10, "Last 10 decodes"), (20, "Last 20"), (50, "Last 50"), (0, "All since start")]


def cpu_name() -> str:
    if sys.platform.startswith("linux"):
        try:
            for line in open("/proc/cpuinfo"):
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return platform.processor() or platform.machine()


def rss_mb() -> float | None:
    """Resident memory of this process, MB."""
    if sys.platform.startswith("linux"):
        try:
            for line in open("/proc/self/status"):
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
        except OSError:
            return None
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize",
                                               "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                                               "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                                               "PagefileUsage", "PeakPagefileUsage")]
        c = PMC()
        c.cb = ctypes.sizeof(c)
        if ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),
                                                    ctypes.byref(c), c.cb):
            return c.WorkingSetSize / 2**20
    return None


def summarize(stats: list[dict], latencies: list[float]) -> dict:
    """Averages over the given records. Rates are totals over totals (a long piece weighs more
    than a short one), which is what a user waiting on a long take experiences."""
    audio_s = sum(r["audio_s"] for r in stats)
    decode_s = sum(r["decode_s"] for r in stats)
    tokens = sum(r["tokens"] for r in stats)
    return {
        "decodes": len(stats), "audio_s": round(audio_s, 2), "decode_s": round(decode_s, 3),
        "tokens": tokens,
        "tokens_per_s": round(tokens / decode_s, 1) if decode_s else None,
        "x_realtime": round(audio_s / decode_s, 1) if decode_s else None,
        "rtf": round(decode_s / audio_s, 3) if audio_s else None,
        "ms_per_audio_s": round(1000 * decode_s / audio_s) if audio_s else None,
        "latency_avg_s": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "latency_max_s": round(max(latencies), 2) if latencies else None,
    }


def verdict(x_rt: float | None) -> tuple[str, str]:
    """(advice, colour) from speed in multiples of real time. Thresholds are judgement, not
    measurement: with insert as you go a piece is ~10-25 s, so 3x real time means up to
    ~8 s of waiting for the last piece."""
    if x_rt is None:
        return "No decodes yet: dictate something, or press Run benchmark.", "gray"
    if x_rt >= 10:
        return ("Plenty of headroom. The model is comfortably sized for this computer; text "
                "arrives about a second after you stop."), "#2e9e5b"
    if x_rt >= 3:
        return ("Fine for dictation. Long takes leave a short wait at the end; insert as you go "
                "keeps it small."), "#2e9e5b"
    if x_rt >= 1:
        return ("Tight. Long takes lag behind; keep insert as you go on, try more CPU threads, or a "
                "smaller model or quantization would help on this computer."), "#b07a0c"
    return ("Slower than real time. This computer struggles with this model: more threads, or "
            "a smaller model or quantization, is needed."), "#D62828"


class _Sig(QObject):
    bench_done = Signal(object)


class DiagnosticsPage(QScrollArea):
    def __init__(self, ctl, card, muted):
        super().__init__()
        self.ctl = ctl
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.sig = _Sig()
        self.sig.bench_done.connect(self._bench_done)
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)

        box, b = card("Inference speed")
        row = QHBoxLayout()
        self.window = QComboBox()
        for n, label in WINDOWS:
            self.window.addItem(label, n)
        self.window.currentIndexChanged.connect(self.refresh)
        row.addWidget(self.window)
        row.addStretch(1)
        self.btn_bench = QPushButton("Run benchmark")
        self.btn_bench.setToolTip("Decode ~10 s of bundled speech three times")
        self.btn_bench.clicked.connect(self._bench)
        row.addWidget(self.btn_bench)
        b.addLayout(row)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(6)
        self.vals = {}
        for i, (key, label, tip) in enumerate([
                ("tokens_per_s", "Tokens per second", "Output tokens decoded per second of compute"),
                ("x_realtime", "Speed", "Seconds of audio decoded per second of compute"),
                ("ms_per_audio_s", "Compute per audio second", "Milliseconds of decoding per second of audio"),
                ("latency_avg_s", "Stop → text (avg)", "From stopping a take to its last text being inserted"),
                ("latency_max_s", "Stop → text (max)", ""),
                ("decodes", "Decodes averaged", "Pieces decoded (long takes are decoded in pieces)"),
                ("audio_s", "Audio decoded", ""),
                ("tokens", "Tokens", "")]):
            name = QLabel(label)
            name.setToolTip(tip)
            val = QLabel("–")
            val.setStyleSheet("font-size: 15px; font-weight: 700;")
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(name, i // 2, (i % 2) * 2)
            grid.addWidget(val, i // 2, (i % 2) * 2 + 1)
            self.vals[key] = val
        b.addLayout(grid)
        self.verdict = QLabel()
        self.verdict.setWordWrap(True)
        b.addWidget(self.verdict)
        lay.addWidget(box)

        box, b = card("This computer and model")
        self.system = QLabel()
        self.system.setTextFormat(Qt.RichText)
        self.system.setWordWrap(True)
        self.system.setTextInteractionFlags(Qt.TextSelectableByMouse)
        b.addWidget(self.system)
        lay.addWidget(box)

        box, b = card("Recent decodes")
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Time", "Audio s", "Decode s", "Tokens", "Tok/s", "× real time"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setMinimumHeight(200)
        b.addWidget(self.table)
        row = QHBoxLayout()
        copy = QPushButton("Copy as JSON")
        copy.setToolTip("The summary, system details and every record, for a bug report")
        copy.clicked.connect(lambda: (copy_to_clipboard(json.dumps(self.report(), indent=1)),
                                      self.ctl.win.status("Diagnostics copied as JSON.")))
        clear = QPushButton("Clear")
        clear.clicked.connect(lambda: (self.ctl.engine.stats.clear(), self.ctl.latencies.clear(),
                                       self.refresh()))
        row.addWidget(copy)
        row.addWidget(clear)
        row.addStretch(1)
        b.addLayout(row)
        b.addWidget(muted("Measured on this computer from your own dictation (and benchmarks), "
                          "kept in memory only, never sent anywhere."))
        lay.addWidget(box)
        lay.addStretch(1)
        self.setWidget(page)
        self._timer = QTimer(self, interval=1000, timeout=self._tick)
        self._timer.start()
        self._shown = -1

    def _tick(self):
        if self.isVisible() and len(self.ctl.engine.stats) != self._shown:
            self.refresh()

    def _recent(self):
        n = self.window.currentData()
        stats = list(self.ctl.engine.stats)
        lat = list(self.ctl.latencies)
        return (stats[-n:], lat[-n:]) if n else (stats, lat)

    def system_info(self) -> dict:
        cur = model_store.active()
        eng = self.ctl.engine
        try:
            import sherpa_onnx
            so = sherpa_onnx.__version__
        except Exception:
            so = "?"
        rss = rss_mb()
        return {
            "app": __version__, "os": f"{platform.system()} {platform.release()}",
            "cpu": cpu_name(), "logical_cpus": os.cpu_count(), "decode_threads": eng.threads,
            "model": cur[1].full_label if cur else None,
            "model_id": model_store.current_id(),
            "quantization": "int8 (encoder, decoder, joiner)",
            "model_mb": round(sum(f.stat().st_size for f in cur[0].iterdir() if f.is_file()) / 2**20)
            if cur else None,
            "load_s": round(eng.load_s, 2), "sherpa_onnx": so, "provider": "cpu",
            "memory_mb": round(rss) if rss else None,
        }

    def report(self) -> dict:
        stats, lat = self._recent()
        return {"summary": summarize(stats, lat), "system": self.system_info(), "records": stats,
                "latencies_s": lat}

    def refresh(self):
        stats, lat = self._recent()
        self._shown = len(self.ctl.engine.stats)
        s = summarize(stats, lat)
        fmt = {"x_realtime": "{}× real time", "ms_per_audio_s": "{} ms", "latency_avg_s": "{} s",
               "latency_max_s": "{} s", "audio_s": "{} s"}
        for k, lbl in self.vals.items():
            v = s[k]
            lbl.setText("–" if v is None else fmt.get(k, "{}").format(v))
        text, col = verdict(s["x_realtime"])
        self.verdict.setText(f"<span style='color:{col}'><b>{text}</b></span>")
        info = self.system_info()
        self.system.setText(
            f"<b>CPU</b> {info['cpu']} · {info['logical_cpus']} logical CPUs · "
            f"{info['decode_threads']} decode threads (Settings → Speed)<br>"
            f"<b>Model</b> {info['model'] or 'none loaded'} · {info['quantization']} · "
            f"{info['model_mb'] or '–'} MB on disk · loaded in {info['load_s']} s<br>"
            f"<b>Runtime</b> sherpa-onnx {info['sherpa_onnx']}, {info['provider']} · app memory "
            f"{info['memory_mb'] or '–'} MB · {info['os']} · Hebrish {info['app']}")
        rows = stats[-50:][::-1]
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vals = [time.strftime("%H:%M:%S", time.localtime(r["at"])), f"{r['audio_s']:.1f}",
                    f"{r['decode_s']:.2f}", str(r["tokens"]),
                    f"{r['tokens'] / r['decode_s']:.0f}" if r["decode_s"] else "–",
                    f"{r['audio_s'] / r['decode_s']:.1f}" if r["decode_s"] else "–"]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, j, it)

    # -- benchmark -------------------------------------------------------------------
    def _bench(self):
        eng = self.ctl.engine
        if eng.loaded_dir is None or self.ctl.state != "idle":
            self.ctl.win.status("Benchmark: wait until the model is loaded and nothing is recording.")
            return
        self.btn_bench.setEnabled(False)
        self.btn_bench.setText("Running…")
        gap = np.zeros(audio.SAMPLE_RATE // 2, np.float32)
        parts = []
        for k in audio.VOICE_PROMPTS:
            try:
                with wave.open(str(audio.VOICE_DIR / "herman" / f"{k}.wav")) as w:
                    parts += [np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768, gap]
            except (OSError, wave.Error):
                continue
        clip = np.concatenate(parts) if parts else np.zeros(audio.SAMPLE_RATE, np.float32)

        def work():
            try:
                for _ in range(3):
                    eng.transcribe(clip)
                self.sig.bench_done.emit(None)
            except Exception as e:
                self.sig.bench_done.emit(e)
        threading.Thread(target=work, daemon=True).start()

    def _bench_done(self, err):
        self.btn_bench.setEnabled(True)
        self.btn_bench.setText("Run benchmark")
        self.ctl.win.status(f"Benchmark failed: {err}" if err else "Benchmark done.")
        self.refresh()
