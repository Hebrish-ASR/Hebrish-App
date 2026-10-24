"""Transcription tab (Transcription Mode, R-2026-10-24-5): record a long take, or drop or pick an
audio file, and the transcript fills an editable text box piece by piece.

The recorder (longform.TapeRecorder) has its own mic, a digital gain, a level meter that can be
hidden, and Record / Pause / Retake / Stop / Transcribe; Transcribe goes straight from recording
to the transcript. The audio is on disk while it records and is deleted once the transcript is in
History; a recording that wasn't transcribed is offered again. Hotkey dictation is the Dictate
tab's; up to 1.000 this tab was "File" and only opened files (up to 0.4.0 it also recorded).

Paragraphs (B-44, ../shared/paragraphs.md): None, Time-based (a paragraph about every PARAGRAPH_S of
audio) or Paragraph model (paragraphs.Breaker, run once when the transcript is done). The last
transcript's pieces are kept (paragraphs.Pieces), so changing the setting lays it out again as long
as the box still holds exactly what the app wrote."""

import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QTextCursor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSlider,
                               QToolButton, QVBoxLayout, QWidget)

from .. import audio, dictionary, disfluency, longform, paragraphs
from ..inserter import copy_to_clipboard
from .meter import LevelMeter, verdict

PARAGRAPH_S = 30
CONFIRM_DROP_S = 60      # Retake / Discard ask first when the recording is longer than this


class _Sig(QObject):
    chunk = Signal(str)
    progress = Signal(float)
    done = Signal(object)
    loaded = Signal(object, str)       # samples or exception, file name
    tape = Signal(object, object)      # samples or exception, recording path
    flowed = Signal(int, object)       # re-flow generation, transcript text or exception
    dl_progress = Signal(object, object)   # bytes done, total
    dl_done = Signal(object)           # None or exception


PARAGRAPH_MODES = (("None", paragraphs.NONE), ("Time-based", paragraphs.TIME),
                   ("Paragraph model", paragraphs.MODEL))


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
        self.sig.tape.connect(self._tape_loaded)
        self.sig.flowed.connect(self._flowed)
        self.sig.dl_progress.connect(self._dl_progress)
        self.sig.dl_done.connect(self._dl_done)
        self._last = None                # the last transcript, while it can be re-flowed (see _finished)
        self._live = None                # the box as the app last wrote it, while transcribing
        self._edited = False             # the user typed in the box while it was transcribing
        self._flow_gen = 0
        self._dl = None                  # cancel event of a paragraph-model download
        self.setAcceptDrops(True)
        self.tape = longform.TapeRecorder()
        self.tape.gain_db = float(self.cfg["tm_gain_db"])
        self._source = None              # recording being transcribed (deleted on success)
        self._held = None                # a stopped recording waiting for Transcribe
        self._timer = QTimer(self, interval=60, timeout=self._tick)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 8)
        lay.setSpacing(12)

        self.leftover = QLabel(objectName="banner")
        self.leftover.setWordWrap(True)
        self.leftover_row = QWidget()
        r = QHBoxLayout(self.leftover_row)
        r.setContentsMargins(0, 0, 0, 0)
        r.addWidget(self.leftover, 1)
        self.btn_left_go = QPushButton("Transcribe it")
        self.btn_left_go.clicked.connect(self._transcribe_leftover)
        self.btn_left_del = QPushButton("Delete")
        self.btn_left_del.clicked.connect(self._delete_leftover)
        r.addWidget(self.btn_left_go)
        r.addWidget(self.btn_left_del)
        lay.addWidget(self.leftover_row)

        # -- recorder
        box, b = card()
        head = QHBoxLayout()
        head.addWidget(QLabel("Record", objectName="cardTitle"))
        head.addStretch(1)
        self.show_meter = QCheckBox("Show level", checked=bool(self.cfg["tm_show_meter"]))
        self.show_meter.toggled.connect(self._on_show_meter)
        head.addWidget(self.show_meter)
        b.addLayout(head)

        row = QHBoxLayout()
        self.mic = QComboBox()
        self.mic.setMinimumWidth(120)
        self.mic.setToolTip("The microphone for Transcription Mode (Dictate keeps its own). "
                            "Changing it while recording switches at once; the recording carries on.")
        row.addWidget(self.mic, 1)
        refresh = QToolButton()
        refresh.setIcon(QIcon.fromTheme("view-refresh"))
        refresh.setText("↻")
        refresh.setToolTip("Rescan microphones")
        refresh.clicked.connect(self._fill_mics)
        row.addWidget(refresh)
        b.addLayout(row)
        self._fill_mics()
        self.mic.currentIndexChanged.connect(self._on_mic)

        row = QHBoxLayout()
        row.addWidget(QLabel("Gain"))
        self.gain = QSlider(Qt.Horizontal, minimum=longform.GAIN_MIN_DB, maximum=longform.GAIN_MAX_DB,
                            value=int(self.cfg["tm_gain_db"]))
        self.gain.setToolTip("Digital gain on what is recorded. The meter shows the result: aim "
                             "for the green zone, and turn it down if the clip lamp lights.")
        self.gain.valueChanged.connect(self._on_gain)
        row.addWidget(self.gain, 1)
        self.gain_label = QLabel()
        self.gain_label.setMinimumWidth(48)
        row.addWidget(self.gain_label)
        reset = QToolButton(text="Reset")
        reset.setToolTip("No gain")
        reset.clicked.connect(lambda: self.gain.setValue(0))
        row.addWidget(reset)
        b.addLayout(row)
        self._on_gain(self.gain.value())

        self.meter_box = QWidget()
        m = QVBoxLayout(self.meter_box)
        m.setContentsMargins(0, 0, 0, 0)
        m.setSpacing(4)
        self.meter = LevelMeter()
        m.addWidget(self.meter)
        self.meter_label = QLabel()
        self.meter_label.setStyleSheet("font-size: 12px;")
        m.addWidget(self.meter_label)
        b.addWidget(self.meter_box)
        self.meter_box.setVisible(self.show_meter.isChecked())

        row = QHBoxLayout()
        self.btn_rec = QPushButton(QIcon.fromTheme("media-record"), "Record")
        self.btn_rec.clicked.connect(self._rec_or_pause)
        self.btn_retake = QPushButton(QIcon.fromTheme("edit-undo"), "Retake")
        self.btn_retake.setToolTip("Throw this recording away and start again")
        self.btn_retake.clicked.connect(self._retake)
        self.btn_stop = QPushButton(QIcon.fromTheme("media-playback-stop"), "Stop")
        self.btn_stop.setToolTip("Stop recording and keep the audio, to transcribe when you're ready")
        self.btn_stop.clicked.connect(self._stop)
        self.btn_go = QPushButton("Transcribe", objectName="primary")
        self.btn_go.setToolTip("Stop (if recording) and transcribe")
        self.btn_go.clicked.connect(self._transcribe_tape)
        self.btn_drop_tape = QToolButton()
        self.btn_drop_tape.setIcon(QIcon.fromTheme("edit-delete"))
        self.btn_drop_tape.setText("✕")
        self.btn_drop_tape.setToolTip("Discard this recording")
        self.btn_drop_tape.clicked.connect(self._discard)
        for w in (self.btn_rec, self.btn_retake, self.btn_stop, self.btn_go, self.btn_drop_tape):
            row.addWidget(w)
        row.addStretch(1)
        # Elapsed time: small and grey, at the end of the controls, so it is there when you look
        # but doesn't pull the eye while you talk.
        self.elapsed = muted()
        self.elapsed.setToolTip("Recorded so far")
        row.addWidget(self.elapsed)
        b.addLayout(row)

        row = QHBoxLayout()
        self.drop = QPushButton("Open an audio file…")
        self.drop.setToolTip("Or drop one anywhere on this tab: " + audio.AUDIO_FILTER.split("(")[1].rstrip(")"))
        self.drop.clicked.connect(self._open)
        row.addWidget(self.drop)
        row.addWidget(muted("or drop one on this tab"), 1)
        b.addLayout(row)
        self.btn_open = self.drop
        lay.addWidget(box)

        # -- transcript
        box, b = card()
        head = QHBoxLayout()
        head.addWidget(QLabel("Transcript", objectName="cardTitle"))
        head.addStretch(1)
        self.dl_bar = QProgressBar(maximum=1000)
        self.dl_bar.setFormat("Downloading… %p%")
        self.dl_bar.setMaximumWidth(160)
        self.dl_bar.setVisible(False)
        head.addWidget(self.dl_bar)
        head.addWidget(QLabel("Paragraphs"))
        self.para = QComboBox()
        for label, mode in PARAGRAPH_MODES:
            self.para.addItem(label, mode)
        self.para.setToolTip(
            "How the transcript is split into paragraphs.\n"
            "None: one block of text.\n"
            "Time-based: a new paragraph about every 30 seconds of audio, at a pause.\n"
            "Paragraph model: a small model reads the finished transcript and starts a paragraph "
            "where the topic moves on (downloaded once, 34 MB).\n"
            "Changing it re-flows the last transcript, unless you have edited it.")
        self.para.setCurrentIndex(self.para.findData(self._para_mode()))
        self.para.currentIndexChanged.connect(self._on_paragraphs)
        head.addWidget(self.para)
        b.addLayout(head)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("The transcript lands here, and you can edit it. "
                                     "Another recording or file is added at the end. Paragraphs "
                                     "follow the Paragraphs setting above.")
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
        self._sync()
        self._show_leftover()

    # -- recorder --------------------------------------------------------------------
    def _fill_mics(self):
        cur = self.cfg["tm_audio_device"]
        self.mic.blockSignals(True)
        self.mic.clear()
        self.mic.addItem("System default", "")
        for name in audio.input_devices():
            self.mic.addItem(name, name)
        if cur and self.mic.findData(cur) < 0:
            self.mic.addItem(f"{cur} (not found)", cur)
        self.mic.setCurrentIndex(max(0, self.mic.findData(cur)))
        self.mic.blockSignals(False)

    def _on_mic(self, _i):
        dev = self.mic.currentData()
        self.cfg.set("tm_audio_device", dev)
        try:
            self.tape.switch_device(dev)
        except Exception as e:
            self.tape.pause()
            QMessageBox.warning(self, "Couldn't open the microphone",
                                f"{e}\n\nThe recording is paused; pick another mic and press Resume.")
        self._sync()

    def _on_gain(self, v):
        self.tape.gain_db = float(v)
        self.gain_label.setText(f"{v:+d} dB" if v else "0 dB")
        if self.gain.isSliderDown():
            return
        self.cfg.set("tm_gain_db", v)

    def _on_show_meter(self, on):
        self.meter_box.setVisible(on)
        self.cfg.set("tm_show_meter", on)

    def _rec_or_pause(self):
        t = self.tape
        if t.active:
            t.resume() if t.paused else t.pause()
        else:
            if self.ctl.state != "idle":
                self.ctl.win.status("Dictation is running: stop it first.")
                return
            self.ctl.stop_monitor()
            try:
                t.start(self.cfg["tm_audio_device"])
            except Exception as e:
                QMessageBox.warning(self, "Couldn't open the microphone", str(e))
                return
        self._sync()

    def _confirm_drop(self, what: str) -> bool:
        s = self.tape.seconds if self.tape.active else self._held_seconds()
        return s < CONFIRM_DROP_S or QMessageBox.question(
            self, what, f"Throw away {_clock(s)} of recording?") == QMessageBox.Yes

    def _held_seconds(self) -> float:
        return longform.recover(self._held) if self._held and self._held.exists() else 0.0

    def _drop_held(self):
        if self._held:
            self._held.unlink(missing_ok=True)
            self._held = None

    def _retake(self):
        if not self._confirm_drop("Retake"):
            return
        self.tape.discard()
        self._drop_held()
        self._rec_or_pause()

    def _discard(self):
        if not self._confirm_drop("Discard recording"):
            return
        self.tape.discard()
        self._drop_held()
        self.ctl.win.status("Recording discarded.")
        self._sync()

    def _stop(self):
        self._held = self.tape.stop() or self._held
        if self._held:
            self.ctl.win.status(f"Stopped: {_clock(self._held_seconds())} recorded. "
                                "Transcribe when you're ready.")
        self._sync()

    def _transcribe_tape(self):
        if self.tape.active:
            self._held = self.tape.stop() or self._held
        self._sync()
        if self._held:
            self._transcribe_path(self._held)

    def _transcribe_path(self, path: Path):
        if self.cancel is not None:
            return
        self.ctl.win.status("Reading the recording…")

        def work():
            try:
                self.sig.tape.emit(longform.load(path), path)
            except Exception as e:
                self.sig.tape.emit(e, path)
        threading.Thread(target=work, daemon=True).start()

    def _tape_loaded(self, samples, path):
        if isinstance(samples, Exception):
            QMessageBox.warning(self, "Couldn't read the recording", f"{path.name}: {samples}")
            return
        self.transcribe(samples, source=path)

    def _tick(self):
        t = self.tape
        if t.active and t.full:
            self._stop()
            self.ctl.notify("Transcription Mode", "The recording reached its limit and stopped.")
            return
        if t.active:
            self.elapsed.setText(("❚❚ " if t.paused else "● ") + _clock(t.seconds))
        if not self.meter_box.isVisible():
            return
        self.meter.set_source(t if t.active else None)
        if not t.active:
            self.meter_label.setText("<span style='color:gray'>Level: shows while recording</span>")
        elif t.paused:
            self.meter_label.setText("Paused")
        else:
            text, col = verdict(self.meter.rms_db, self.meter.clipping)
            self.meter_label.setText(f"<b style='color:{col}'>{text}</b> &nbsp;"
                                     f"<span style='color:gray'>{self.meter.rms_db:.0f} dB · peak "
                                     f"{self.meter.peak_db:.0f} dB</span>")

    def _sync(self):
        """Buttons and the timer for the recorder's state: idle, recording, paused, stopped
        (a recording held for Transcribe), or busy transcribing."""
        t, busy = self.tape, self.cancel is not None
        rec, held = t.active, self._held is not None and not t.active
        self.btn_rec.setText("Resume" if rec and t.paused else "Pause" if rec else "Record")
        self.btn_rec.setIcon(QIcon.fromTheme("media-playback-start" if rec and t.paused else
                                             "media-playback-pause" if rec else "media-record"))
        self.btn_rec.setEnabled(not busy and not held)
        self.btn_retake.setEnabled(not busy and (rec or held))
        self.btn_stop.setEnabled(rec)
        self.btn_go.setEnabled(not busy and (rec or held))
        self.btn_drop_tape.setEnabled(not busy and (rec or held))
        self.drop.setEnabled(not busy and not rec)
        if rec:
            self._timer.start()
        else:
            self._timer.stop()
            self.elapsed.setText(f"■ {_clock(self._held_seconds())}" if held else "")
        self._tick()

    def _show_leftover(self):
        """A recording from an earlier run (the app quit or crashed, or its transcription failed
        or was cancelled): offer it, oldest first."""
        mine = {self._held, self._source, self.tape.path}
        rest = [p for p in longform.leftovers() if p not in mine]
        self._leftover = rest[0] if rest else None
        self.leftover_row.setVisible(bool(rest))
        if rest:
            p = rest[0]
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime))
            more = f" ({len(rest) - 1} more after it)" if len(rest) > 1 else ""
            self.leftover.setText(f"A recording from {when} ({_clock(longform.recover(p))}) "
                                  f"hasn't been transcribed{more}.")

    def _transcribe_leftover(self):
        if self._leftover and self.cancel is None:
            self._transcribe_path(self._leftover)

    def _delete_leftover(self):
        p = self._leftover
        if p and QMessageBox.question(self, "Delete recording",
                                      f"Delete the recording from {p.name}?") == QMessageBox.Yes:
            p.unlink(missing_ok=True)
            self._show_leftover()

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
    def transcribe(self, samples, source=None):
        """source: the recording's path (Transcription Mode), deleted once the transcript is in
        History; None for a file."""
        if len(samples) < audio.SAMPLE_RATE // 2:
            self.ctl.win.status("Nothing to transcribe: under half a second of audio.")
            return
        if self.ctl.engine.loaded_dir is None:
            QMessageBox.information(self, "Model not ready",
                                    "The model is still downloading or loading. Try again in a moment.")
            return
        self.cancel = threading.Event()
        cancel = self.cancel
        self._source = source
        self._last = None
        self._live, self._edited = self.text.toPlainText(), False
        self._from = len(self._live)     # History gets this transcript, not the whole box
        self._busy(True)
        started = time.monotonic()
        mode = self._asked = self._para_mode()
        note = ""
        if mode == paragraphs.MODEL and paragraphs.installed() is None:
            mode = paragraphs.TIME
            note = (" The paragraph model is still downloading" if self._dl else
                    " The paragraph model isn't downloaded") + ", so paragraphs are time-based."

        def work():
            try:
                fix = dictionary.compile(dictionary.load())     # personal dictionary, as in dictation
                # pieces are ~10-25 s; Time-based starts a paragraph every ~30 s of audio. With
                # the Paragraph model they are joined with spaces until the end.
                pieces = paragraphs.Pieces(PARAGRAPH_S * audio.SAMPLE_RATE)
                for text in self.ctl.engine.transcribe_chunks(samples, cancel, vad=self.cfg["vad"]):
                    done, total = self.ctl.engine.last_progress
                    text = fix(disfluency.chop(text))
                    sep = pieces.add(text, done, mode)
                    if sep is not None:      # the first piece is set off from what's in the box
                        self.sig.chunk.emit(("\n\n" if len(pieces.items) == 1 else sep) + text)
                    self.sig.progress.emit(done / total)
                body, err = None, None
                if mode == paragraphs.MODEL and pieces.items:
                    try:
                        body = pieces.text(paragraphs.MODEL, paragraphs.breaker())
                    except Exception as e:   # fall back, never lose text
                        body, err = pieces.text(paragraphs.TIME), e
                self.sig.done.emit((len(samples) / audio.SAMPLE_RATE, time.monotonic() - started,
                                    cancel.is_set(), pieces, mode, body, err, note))
            except Exception as e:
                self.sig.done.emit(e)
        threading.Thread(target=work, daemon=True).start()

    def _append(self, text):
        if self._live is not None and self.text.toPlainText() != self._live:
            self._edited = True
        if not self.text.toPlainText().strip():
            text = text.lstrip()
        self.text.moveCursor(self.text.textCursor().MoveOperation.End)
        self.text.insertPlainText(text)
        self.text.ensureCursorVisible()
        if self._live is not None:
            self._live = self.text.toPlainText()

    def _finished(self, result):
        self.cancel = None
        source, self._source = self._source, None
        if source is not None and source == self._held:
            self._held = None                # transcribed or not, it's no longer "stopped"
        self._busy(False)
        live, self._live = self._live, None
        if isinstance(result, Exception):
            self._show_leftover()            # the recording stays on disk, offered again
            QMessageBox.warning(self, "Transcription failed", str(result))
            return
        audio_s, took, cancelled, pieces, mode, body, err, note = result
        unedited = not self._edited and self.text.toPlainText() == live
        if unedited and pieces.items:
            self._last = {"from": self._from, "pieces": pieces, "mode": mode,
                          "shown": self.text.toPlainText(), "rid": None}
        if mode == paragraphs.MODEL and pieces.items:
            if self._last:
                self._show_body(body, paragraphs.TIME if err else mode)
                if err:
                    note += f" The paragraph model failed ({err}), so paragraphs are time-based."
            else:
                note += " You edited the transcript while it was transcribing, so the paragraph model wasn't applied."
        if not cancelled:
            rid = self.ctl.remember(self.text.toPlainText()[self._from:].strip(),
                                    source="record" if source else "file",
                                    seconds=audio_s)
            if self._last:
                self._last["rid"] = rid
            if source is not None:
                source.unlink(missing_ok=True)
        self._show_leftover()
        msg = f"Transcribed {_clock(audio_s)} of audio in {took:.1f} s"
        self.ctl.win.status(msg + (" (cancelled part-way)." if cancelled else ".") + note)
        if self._last and (self._para_mode() != self._asked or (     # changed while transcribing,
                mode != self._asked and err is None and paragraphs.installed() is not None)):
            self._reflow()                   # or the model finished downloading meanwhile

    # -- paragraphs (B-44) -----------------------------------------------------------
    def _para_mode(self) -> str:
        """The Paragraphs setting; not chosen yet: Paragraph model if it is installed, else
        Time-based (../shared/paragraphs.md)."""
        m = self.cfg.get("tm_paragraphs")
        if m in paragraphs.MODES:
            return m
        return paragraphs.MODEL if paragraphs.installed() is not None else paragraphs.TIME

    def _on_paragraphs(self, _i):
        mode = self.para.currentData()
        self.cfg.set("tm_paragraphs", mode)
        if mode == paragraphs.MODEL and paragraphs.installed() is None:
            self._download()                 # re-flows when it is done
            return
        self._reflow()

    def _reflow(self):
        """Lay out the last transcript again in the current mode, if the box is as the app left it."""
        last = self._last
        if not last or self.cancel is not None:
            return
        if self.text.toPlainText() != last["shown"]:
            self._last = None
            self.ctl.win.status("The transcript has been edited, so its paragraphs were left as they are.")
            return
        mode = self._para_mode()
        self._flow_gen += 1
        if mode != paragraphs.MODEL:
            self._flowed(self._flow_gen, last["pieces"].text(mode))
            return
        if paragraphs.installed() is None:
            return
        gen, pieces = self._flow_gen, last["pieces"]
        self.ctl.win.status("Finding paragraphs…")

        def work():
            try:
                self.sig.flowed.emit(gen, pieces.text(paragraphs.MODEL, paragraphs.breaker()))
            except Exception as e:
                self.sig.flowed.emit(gen, e)
        threading.Thread(target=work, daemon=True).start()

    def _flowed(self, gen, body):
        last = self._last
        if gen != self._flow_gen or not last or self.cancel is not None:
            return                           # superseded, or a new transcription started
        if self.text.toPlainText() != last["shown"]:
            self._last = None
            self.ctl.win.status("The transcript has been edited, so its paragraphs were left as they are.")
            return
        mode = self._para_mode()
        if isinstance(body, Exception):
            self.ctl.win.status(f"The paragraph model failed ({body}), so paragraphs are time-based.")
            body, mode = last["pieces"].text(paragraphs.TIME), paragraphs.TIME
        elif mode == paragraphs.MODEL:
            self.ctl.win.status("Paragraphs found.")
        self._show_body(body, mode)
        if last["rid"]:                      # History stores what is shown
            self.ctl.relayout_history(last["rid"], self.text.toPlainText()[last["from"]:].strip())

    def _show_body(self, body: str, mode: str):
        """Put `body` in place of the last transcript (the box is known to be unedited)."""
        last = self._last
        box = self.text.toPlainText()
        region = box[last["from"]:]
        new = box[:last["from"]] + region[:len(region) - len(region.lstrip())] + body
        if new != box:
            c = self.text.textCursor()
            c.select(QTextCursor.SelectionType.Document)
            c.insertText(new)                # one undo step
            self.text.setTextCursor(c)
        last["shown"], last["mode"] = self.text.toPlainText(), mode

    def _download(self):
        if self._dl is not None:
            return
        self._dl = cancel = threading.Event()
        self.dl_bar.setValue(0)
        self.dl_bar.setVisible(True)
        self.ctl.win.status("Downloading the paragraph model (34 MB)…")

        def work():
            try:
                paragraphs.download(lambda d, t, _n: self.sig.dl_progress.emit(d, t), cancel)
                self.sig.dl_done.emit(None)
            except Exception as e:
                self.sig.dl_done.emit(e)
        threading.Thread(target=work, daemon=True).start()

    def _dl_progress(self, done, total):
        self.dl_bar.setValue(int(done * 1000 / max(1, total)))

    def _dl_done(self, err):
        self._dl = None
        self.dl_bar.setVisible(False)
        if err is not None:
            self.ctl.win.status(f"Couldn't download the paragraph model ({err}). Paragraphs are "
                                "time-based; choose Paragraph model again to retry.")
            self.para.blockSignals(True)
            self.para.setCurrentIndex(self.para.findData(paragraphs.TIME))
            self.para.blockSignals(False)
            self.cfg.set("tm_paragraphs", paragraphs.TIME)
            self._reflow()
            return
        self.ctl.win.status("Paragraph model downloaded.")
        if self._para_mode() == paragraphs.MODEL:
            self._reflow()

    def _busy(self, on: bool):
        self.pbar.setVisible(on)
        self.btn_cancel.setVisible(on)
        self.pbar.setValue(0)
        if hasattr(self, "btn_rec"):
            self._sync()

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
            self._last = None
