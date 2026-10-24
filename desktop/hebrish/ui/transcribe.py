"""File tab: transcribe an audio file. Drop or pick one, and the transcript fills an editable
text box piece by piece. Recording (hotkey or button) is the Dictate tab; up to 0.4.0 this tab
also recorded, with its own 3-hour recorder."""

import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from .. import audio, dictionary, disfluency
from ..inserter import copy_to_clipboard

PARAGRAPH_S = 30


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

        # -- source: half the tab is the drop zone (0.5.0: recording moved to the Dictate tab)
        self.drop = QPushButton(objectName="dropZone")
        self.drop.setText("Drop an audio file here\n\nor click to choose one\n\n"
                          "WAV, MP3, M4A, OGG, OPUS, FLAC, WebM")
        self.drop.setCursor(Qt.PointingHandCursor)
        self.drop.setMinimumHeight(160)
        self.drop.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.drop.clicked.connect(self._open)
        lay.addWidget(self.drop, 1)
        self.btn_open = self.drop

        # -- transcript
        box, b = card("Transcript")
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("The file's transcript lands here, and you can edit it. "
                                     "Another file is added at the end. Long recordings get a "
                                     "paragraph for roughly every 30 seconds, split at a pause.")
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

        self._busy(False)
        self._count()

    # -- files -----------------------------------------------------------------------
    def _open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open audio", str(Path.home()),
                                              f"{audio.AUDIO_FILTER};;All files (*)")
        if path:
            self.transcribe_file(path)

    def transcribe_file(self, path: str):
        if self.cancel is not None:
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
                fix = dictionary.compile(dictionary.load())     # personal dictionary, as in dictation
                para_at = None     # pieces are ~10-25 s; start a paragraph every ~30 s of audio
                for text in self.ctl.engine.transcribe_chunks(samples, cancel, vad=self.cfg["vad"]):
                    done, total = self.ctl.engine.last_progress
                    new = para_at is None or done - para_at >= PARAGRAPH_S * audio.SAMPLE_RATE
                    para_at = done if new else para_at
                    self.sig.chunk.emit(("\n\n" if new else " ") + fix(disfluency.chop(text)))
                    self.sig.progress.emit(done / total)
                self.sig.done.emit((len(samples) / audio.SAMPLE_RATE, time.monotonic() - started,
                                    cancel.is_set()))
            except Exception as e:
                self.sig.done.emit(e)
        threading.Thread(target=work, daemon=True).start()

    def _append(self, text):
        if not self.text.toPlainText().strip():
            text = text.lstrip()
        self.text.moveCursor(self.text.textCursor().MoveOperation.End)
        self.text.insertPlainText(text)
        self.text.ensureCursorVisible()

    def _finished(self, result):
        self.cancel = None
        self._busy(False)
        if isinstance(result, Exception):
            QMessageBox.warning(self, "Transcription failed", str(result))
            return
        audio_s, took, cancelled = result
        if not cancelled:
            self.ctl.remember(self.text.toPlainText(), source="file", seconds=audio_s)
        msg = f"Transcribed {_clock(audio_s)} of audio in {took:.1f} s"
        self.ctl.win.status(msg + (" (cancelled part-way)." if cancelled else "."))

    def _busy(self, on: bool):
        self.pbar.setVisible(on)
        self.btn_cancel.setVisible(on)
        self.pbar.setValue(0)
        self.drop.setEnabled(not on)

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

    def _clear(self):
        if QMessageBox.question(self, "Clear transcript", "Clear the text box?") == QMessageBox.Yes:
            self.text.clear()
