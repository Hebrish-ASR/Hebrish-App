"""Transcribe tab: the long-form workflow. Record (with pause) or open a file, and the
transcript fills an editable text box piece by piece. Hotkey dictation is the Dictate tab."""

import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QToolButton,
                               QVBoxLayout, QWidget)

from .. import audio
from ..inserter import copy_to_clipboard


class _Sig(QObject):
    chunk = Signal(str)
    progress = Signal(float)
    done = Signal(object)
    loaded = Signal(object, str)       # samples or exception, file name


def _clock(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


class TranscribePage(QWidget):
    def __init__(self, ctl, card, muted):
        super().__init__()
        self.ctl, self.cfg = ctl, ctl.cfg
        self.rec = ctl.long_recorder
        self.last_audio = None
        self.cancel = None
        self.sig = _Sig()
        self.sig.chunk.connect(self._append)
        self.sig.progress.connect(lambda f: self.pbar.setValue(int(f * 1000)))
        self.sig.done.connect(self._finished)
        self.sig.loaded.connect(self._file_loaded)
        self.setAcceptDrops(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 8)
        lay.setSpacing(12)

        # -- source
        box, b = card("Record or open audio")
        row = QHBoxLayout()
        row.addWidget(QLabel("Microphone"))
        self.mic = QComboBox()
        row.addWidget(self.mic, 1)
        refresh = QToolButton()
        refresh.setIcon(QIcon.fromTheme("view-refresh"))
        refresh.setText("↻")
        refresh.setToolTip("Rescan microphones")
        refresh.clicked.connect(self._fill_mics)
        row.addWidget(refresh)
        b.addLayout(row)
        self._fill_mics()
        self.mic.currentIndexChanged.connect(lambda _i: self.cfg.set("audio_device", self.mic.currentData()))

        row = QHBoxLayout()
        self.btn_rec = QPushButton("● Record", objectName="primary")
        self.btn_rec.clicked.connect(self._record)
        self.btn_pause = QPushButton("Pause")
        self.btn_pause.clicked.connect(self._pause)
        self.btn_stop = QPushButton("■ Stop and transcribe")
        self.btn_stop.clicked.connect(self._stop)
        self.clock = QLabel("00:00")
        self.clock.setStyleSheet("font-size: 18px; font-weight: 700; font-family: monospace;")
        for w in (self.btn_rec, self.btn_pause, self.btn_stop):
            row.addWidget(w)
        row.addStretch(1)
        row.addWidget(self.clock)
        b.addLayout(row)
        self.meter = QProgressBar(maximum=100, textVisible=False)
        self.meter.setFixedHeight(8)
        b.addWidget(self.meter)

        row = QHBoxLayout()
        self.btn_open = QPushButton(QIcon.fromTheme("document-open"), "Open audio file…")
        self.btn_open.clicked.connect(self._open)
        row.addWidget(self.btn_open)
        row.addWidget(muted("…or drop one on this tab. WAV, MP3, M4A, OGG, FLAC, WebM."), 1)
        b.addLayout(row)
        lay.addWidget(box)

        # -- transcript
        box, b = card("Transcript")
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("Transcripts land here, and you can edit them. New ones are "
                                     "added at the end. Long recordings get a paragraph for "
                                     "roughly every 30 seconds, split at a pause.")
        self.text.setStyleSheet("font-size: 14px;")
        b.addWidget(self.text, 1)
        row = QHBoxLayout()
        self.pbar = QProgressBar(maximum=1000)
        self.pbar.setFormat("Transcribing… %p%")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(lambda: self.cancel and self.cancel.set())
        row.addWidget(self.pbar, 1)
        row.addWidget(self.btn_cancel)
        b.addLayout(row)
        row = QHBoxLayout()
        for label, fn, name in (("Copy", self._copy, "copy"), ("Save…", self._save, "save"),
                                ("Save recording…", self._save_audio, "save_audio"),
                                ("Clear", self._clear, "clear")):
            btn = QPushButton(label)
            btn.clicked.connect(fn)
            setattr(self, f"btn_{name}", btn)
            row.addWidget(btn)
        row.addStretch(1)
        self.words = muted()
        row.addWidget(self.words)
        b.addLayout(row)
        self.text.textChanged.connect(self._count)
        lay.addWidget(box, 1)

        self._tick = QTimer(self, interval=100, timeout=self._update_meter)
        self._busy(False)
        self._count()

    # -- recording -------------------------------------------------------------------
    def _fill_mics(self):
        cur = self.cfg["audio_device"]
        self.mic.blockSignals(True)
        self.mic.clear()
        self.mic.addItem("System default", "")
        for name in audio.input_devices():
            self.mic.addItem(name, name)
        self.mic.setCurrentIndex(max(0, self.mic.findData(cur)))
        self.mic.blockSignals(False)

    def _record(self):
        if self.ctl.state == "recording":
            self.ctl.stop()                 # finish the hotkey take first
        try:
            self.rec.start(self.mic.currentData())
        except Exception as e:
            QMessageBox.warning(self, "Microphone", str(e))
            return
        self._tick.start()
        self._sync_buttons()

    def _pause(self):
        self.rec.resume() if self.rec.paused else self.rec.pause()
        self._sync_buttons()

    def _stop(self):
        self._tick.stop()
        samples = self.rec.stop()
        self.meter.setValue(0)
        self._sync_buttons()
        self.last_audio = samples
        self.btn_save_audio.setEnabled(len(samples) > 0)
        self.transcribe(samples)

    def _update_meter(self):
        self.clock.setText(_clock(self.rec.seconds))
        self.meter.setValue(int(self.rec.level * 100))
        if self.rec.full:
            self._stop()
            self.ctl.notify("Recording stopped", "Reached the 3-hour limit; transcribing.")

    def _sync_buttons(self):
        active, busy = self.rec.active, self.cancel is not None
        self.btn_rec.setEnabled(not active and not busy)
        self.btn_pause.setEnabled(active)
        self.btn_pause.setText("Resume" if self.rec.paused else "Pause")
        self.btn_stop.setEnabled(active)
        self.btn_open.setEnabled(not active and not busy)
        self.mic.setEnabled(not active)

    # -- files -----------------------------------------------------------------------
    def _open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open audio", str(Path.home()),
                                              f"{audio.AUDIO_FILTER};;All files (*)")
        if path:
            self.transcribe_file(path)

    def transcribe_file(self, path: str):
        if self.cancel is not None or self.rec.active:
            return
        self.ctl.win.status(f"Reading {Path(path).name}…")

        def work():
            try:
                self.sig.loaded.emit(audio.load_file(path), Path(path).name)
            except Exception as e:
                self.sig.loaded.emit(e, Path(path).name)
        threading.Thread(target=work, daemon=True).start()

    def _file_loaded(self, samples, name):
        if isinstance(samples, Exception):
            QMessageBox.warning(self, "Couldn't open the file", f"{name}: {samples}")
            return
        self.ctl.win.status(f"{name}: {_clock(len(samples) / audio.SAMPLE_RATE)} of audio.")
        self.last_audio = None
        self.btn_save_audio.setEnabled(False)
        self.transcribe(samples)

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        urls = [u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile()]
        if urls:
            self.transcribe_file(urls[0])

    # -- transcription ---------------------------------------------------------------
    def transcribe(self, samples):
        if len(samples) < audio.SAMPLE_RATE // 2:
            self.ctl.win.status("Nothing to transcribe: under half a second of audio.")
            return
        if self.ctl.engine.loaded_dir is None:
            QMessageBox.information(self, "Model not ready",
                                    "The model is still downloading or loading. Try again in a moment.")
            return
        self.cancel = threading.Event()
        cancel = self.cancel
        self._busy(True)
        started = time.monotonic()

        def work():
            try:
                for text in self.ctl.engine.transcribe_chunks(samples, cancel):
                    self.sig.chunk.emit(text)
                    done, total = self.ctl.engine.last_progress
                    self.sig.progress.emit(done / total)
                self.sig.done.emit((len(samples) / audio.SAMPLE_RATE, time.monotonic() - started,
                                    cancel.is_set()))
            except Exception as e:
                self.sig.done.emit(e)
        threading.Thread(target=work, daemon=True).start()

    def _append(self, text):
        sep = "\n\n" if self.text.toPlainText().strip() else ""
        self.text.moveCursor(self.text.textCursor().MoveOperation.End)
        self.text.insertPlainText(sep + text)
        self.text.ensureCursorVisible()

    def _finished(self, result):
        self.cancel = None
        self._busy(False)
        if isinstance(result, Exception):
            QMessageBox.warning(self, "Transcription failed", str(result))
            return
        audio_s, took, cancelled = result
        msg = f"Transcribed {_clock(audio_s)} of audio in {took:.1f} s"
        self.ctl.win.status(msg + (" (cancelled part-way)." if cancelled else "."))

    def _busy(self, on: bool):
        self.pbar.setVisible(on)
        self.btn_cancel.setVisible(on)
        self.pbar.setValue(0)
        self._sync_buttons()

    # -- output ----------------------------------------------------------------------
    def _count(self):
        t = self.text.toPlainText()
        n = len(t.split())
        self.words.setText(f"{n} word{'s' if n != 1 else ''}" if n else "")
        for b in (self.btn_copy, self.btn_save, self.btn_clear):
            b.setEnabled(bool(t.strip()))

    def _copy(self):
        copy_to_clipboard(self.text.toPlainText())
        self.ctl.win.status("Transcript copied.")

    def _save(self):
        name = time.strftime("transcript-%Y-%m-%d-%H%M.txt")
        path, _ = QFileDialog.getSaveFileName(self, "Save transcript", str(Path.home() / name),
                                              "Text (*.txt);;Markdown (*.md);;All files (*)")
        if path:
            Path(path).write_text(self.text.toPlainText() + "\n", encoding="utf-8")
            self.ctl.win.status(f"Saved {path}")

    def _save_audio(self):
        if self.last_audio is None:
            return
        name = time.strftime("recording-%Y-%m-%d-%H%M.wav")
        path, _ = QFileDialog.getSaveFileName(self, "Save recording", str(Path.home() / name),
                                              "WAV audio (*.wav)")
        if path:
            audio.save_wav(path, self.last_audio)
            self.ctl.win.status(f"Saved {path}")

    def _clear(self):
        if QMessageBox.question(self, "Clear transcript", "Clear the text box?") == QMessageBox.Yes:
            self.text.clear()
