"""The Benchmarks window (Diagnostics > Benchmarks…): its own window, because most people will never
open it. Run a file or record, then read the Markdown results box; the method is in benchmark.py."""

import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFontDatabase
from PySide6.QtWidgets import (QFileDialog, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit,
                               QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout,
                               QWidget)

from .. import audio, benchmark, mics
from ..inserter import copy_to_clipboard

RECORD_MAX_S = 600
MIN_AUDIO_S = 1.0
HEADERS = ("Date", "Source", "Model", "Audio", "Speed", "RTF", "Peak RAM", "CPU")


class BenchmarkWindow(QWidget):
    finished = Signal(object, object, object)       # row or None, transcript, error

    def __init__(self, parent, ctl):
        super().__init__(parent, Qt.Window)
        self.ctl = ctl
        self.rec = audio.Recorder(max_s=RECORD_MAX_S)
        self.cancel = None
        self.finished.connect(self._done)
        self.tick = QTimer(self, interval=200)
        self.tick.timeout.connect(self._tick)
        self.setWindowTitle("Hebrish benchmarks")
        self.resize(680, 720)
        lay = QVBoxLayout(self)
        intro = QLabel("Measure how fast Hebrish transcribes on this computer and how much it asks of it. "
                       "Everything runs here, and only the figures are saved.")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        row = QHBoxLayout()
        box = QGroupBox("Run a file")
        b = QVBoxLayout(box)
        ref = QLabel(f"The reference file is the first Hebrish podcast episode, {benchmark.REFERENCE['seconds'] / 60:.0f} "
                     "minutes long. Hebrish recognises it, so your result compares directly with other machines. "
                     "Any audio file works too.")
        ref.setWordWrap(True)
        b.addWidget(ref)
        self.btn_get = QPushButton(f"Get the reference file ({benchmark.REFERENCE['bytes'] / 1e6:.0f} MB)")
        self.btn_get.setToolTip("Opens the MP3 in your browser. Save it, then choose it here")
        self.btn_get.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(benchmark.REFERENCE["url"])))
        b.addWidget(self.btn_get)
        self.btn_file = QPushButton("Choose audio file…")
        self.btn_file.clicked.connect(self._choose)
        b.addWidget(self.btn_file)
        b.addStretch(1)
        row.addWidget(box, 3)
        box = QGroupBox("Record")
        b = QVBoxLayout(box)
        note = QLabel(f"Say anything, up to {RECORD_MAX_S // 60} minutes, then stop. The recording isn't kept.")
        note.setWordWrap(True)
        b.addWidget(note)
        self.btn_rec = QPushButton("Record")
        self.btn_rec.clicked.connect(self._record)
        b.addWidget(self.btn_rec)
        b.addStretch(1)
        row.addWidget(box, 2)
        lay.addLayout(row)

        row = QHBoxLayout()
        self.bar = QProgressBar(textVisible=False, maximum=1000)
        row.addWidget(self.bar, 1)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        row.addWidget(self.btn_cancel)
        lay.addLayout(row)
        self.status = QLabel("Ready.")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        row = QHBoxLayout()
        row.addWidget(QLabel("<b>Latest result</b>"))
        row.addStretch(1)
        self.btn_copy = QPushButton("Copy")
        self.btn_copy.setEnabled(False)
        self.btn_copy.clicked.connect(self._copy)
        row.addWidget(self.btn_copy)
        lay.addLayout(row)
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.result = QPlainTextEdit(readOnly=True, placeholderText="The result of your latest run appears here, as Markdown.")
        self.result.setFont(mono)
        self.result.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.result.setMinimumHeight(170)
        lay.addWidget(self.result, 2)

        self.toggle = QToolButton(text="Transcript", checkable=True, arrowType=Qt.RightArrow)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle.setStyleSheet("border: none; font-weight: 600;")
        self.toggle.toggled.connect(self._fold)
        self.toggle.setEnabled(False)
        lay.addWidget(self.toggle)
        self.transcript = QPlainTextEdit(readOnly=True)
        self.transcript.setFrameShape(QFrame.StyledPanel)
        self.transcript.hide()
        lay.addWidget(self.transcript, 1)

        lay.addWidget(QLabel("<b>Past runs</b>"))
        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMaximumHeight(150)
        lay.addWidget(self.table, 1)
        self._fill()

    # -- running ---------------------------------------------------------------------
    def _ready(self) -> bool:
        if self.ctl.engine.loaded_dir is None:
            self.status.setText("Wait until the model has loaded.")
            return False
        if self.ctl.state != "idle":
            self.status.setText("Finish the current dictation first.")
            return False
        return True

    def _busy(self, on: bool):
        for b in (self.btn_file, self.btn_rec):
            b.setEnabled(not on)
        self.btn_cancel.setEnabled(on)
        self.bar.setValue(0)
        self.tick.start() if on else self.tick.stop()

    def _choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose audio", str(Path.home()),
                                              f"{audio.AUDIO_FILTER};;All files (*)")
        if path:
            self.run_file(path)

    def run_file(self, path: str):
        if not self._ready():
            return
        self.status.setText("Reading the file…")
        self._start(lambda c: self._file_job(path, c))

    def _record(self):
        if self.rec.active:
            samples = self.rec.stop()
            self.btn_rec.setText("Record")
            self.tick.stop()
            if len(samples) < MIN_AUDIO_S * audio.SAMPLE_RATE:
                self.status.setText("That was too short to measure.")
                self._busy(False)
                return
            self.status.setText("Transcribing…")
            self._start(lambda c: self._job({"mode": "recording"}, samples, None, c))
            return
        if not self._ready():
            return
        try:
            self.rec.start(mics.resolve(self.ctl.cfg)[0])
        except Exception as e:
            self.status.setText(f"Couldn't open the microphone: {e}")
            return
        self._busy(True)
        self.btn_rec.setEnabled(True)
        self.btn_rec.setText("Stop")

    def _start(self, job):
        self._busy(True)
        self.btn_rec.setEnabled(False)
        self.cancel = threading.Event()
        cancel = self.cancel

        def work():
            try:
                job(cancel)
            except Exception as e:
                self.finished.emit(None, "", e)
        threading.Thread(target=work, daemon=True).start()

    def _file_job(self, path: str, cancel):
        size_match = Path(path).stat().st_size == benchmark.REFERENCE["bytes"]
        digest = benchmark.sha256_file(path)
        is_ref = size_match and digest == benchmark.REFERENCE["sha256"]
        t0 = time.monotonic()
        samples = audio.load_file(path)
        row = {"mode": "reference" if is_ref else "file", "file_name": Path(path).name, "file_sha256": digest,
               "read_s": round(time.monotonic() - t0, 2)}
        if len(samples) < MIN_AUDIO_S * audio.SAMPLE_RATE:
            raise RuntimeError("That file is too short to measure.")
        self._job(row, samples, benchmark.REFERENCE["seconds"] if is_ref else None, cancel)

    def _job(self, row: dict, samples, audio_s, cancel):
        info = benchmark.system_info(self.ctl.engine)
        out = benchmark.measure(self.ctl.engine, samples, audio_s, cancel)
        if out is None:
            self.finished.emit(None, "", None)
            return
        self.finished.emit({"at": time.time(), **row, **info, **out[0]}, out[1], None)

    def _tick(self):
        if self.rec.active:
            self.status.setText(f"Recording: {self.rec.seconds:.0f} s")
            self.bar.setValue(int(1000 * self.rec.seconds / RECORD_MAX_S))
            if self.rec.full:
                self._record()
            return
        done, total = self.ctl.engine.last_progress
        self.bar.setValue(int(1000 * done / max(total, 1)))
        if self.status.text().startswith("Reading") and done < total:
            self.status.setText("Transcribing…")

    def _cancel(self):
        if self.rec.active:
            self.rec.stop()
            self.btn_rec.setText("Record")
            self._busy(False)
            self.status.setText("Cancelled.")
        elif self.cancel is not None:
            self.cancel.set()
            self.status.setText("Cancelling…")

    def _done(self, row, transcript, err):
        self._busy(False)
        self.cancel = None
        if err is not None:
            self.status.setText(f"Benchmark failed: {err}")
            return
        if row is None:
            self.status.setText("Cancelled.")
            return
        self.ctl.history.add_benchmark(row)          # History.db belongs to the GUI thread
        self.result.setPlainText(benchmark.report(row))
        self.btn_copy.setEnabled(True)
        self.transcript.setPlainText(transcript)
        self.toggle.setEnabled(True)
        self.toggle.setChecked(False)
        self.status.setText(f"Done: {row['speed_x']}× real time. Saved.")
        self.bar.setValue(1000)
        self._fill()

    # -- showing ---------------------------------------------------------------------
    def _fold(self, on: bool):
        self.toggle.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self.transcript.setVisible(on)

    def _copy(self):
        copy_to_clipboard(self.result.toPlainText())
        self.status.setText("Copied.")

    def _fill(self):
        rows = self.ctl.history.benchmarks()
        self.table.setRowCount(len(rows))
        source = {"reference": "Reference", "file": "Own file", "recording": "Recording"}
        for i, r in enumerate(rows):
            vals = (time.strftime("%Y-%m-%d %H:%M", time.localtime(r["at"])), source.get(r["mode"], r["mode"]),
                    r["model"] or "–", f"{r['audio_s'] / 60:.1f} min", f"{r['speed_x']}×", str(r["rtf"]),
                    f"{r['ram_peak_mb'] or '–'} MB", f"{r['cpu_avg_pct']}%")
            for j, v in enumerate(vals):
                self.table.setItem(i, j, QTableWidgetItem(v))

    def closeEvent(self, ev):
        self._cancel()
        super().closeEvent(ev)
