"""Transcription tab (Transcription Mode, R-2026-10-24-5): record a long take, or drop or pick an
audio file, and the finished transcript lands in an editable text box in one go (2026-10-31, Daniel:
no piece-by-piece filling; a "Transcribing… m:ss" bar appears only when the job runs past
SHOW_PROGRESS_S).

The recorder (longform.TapeRecorder) has its own mic, a Levels panel (digital gain + level meter:
docked = hidden by default, shown in the card, or floating in its own small window; B-45), and
Record / Pause / Retake / Stop / Transcribe; Transcribe goes straight from recording to the
transcript. The audio is on disk while it records and is deleted once the transcript is in
History; a recording that wasn't transcribed is offered again. Hotkey dictation is the Dictate
tab's; up to 1.000 this tab was "File" and only opened files (up to 0.4.0 it also recorded).

Paragraphs (B-44, ../shared/paragraphs.md): None, Time-based (a paragraph about every PARAGRAPH_S of
audio) or Paragraph model (paragraphs.Breaker, run once when the transcript is done). The last
transcript's pieces are kept (paragraphs.Pieces), so changing the setting lays it out again as long
as the box still holds exactly what the app wrote.

Clean-up (B-40, cleanup.py): with the chosen clean-up model (cleanup.chosen: S1-mini by Superwhisper
by default, or the experimental fine-tune S1-ASR-Cleanup; picked in Models → Utilities) downloaded
and *Clean up* on (`tm_cleanup`, off by default), the finished transcript (after the disfluency chop
and the personal dictionary, laid out as one block) is cleaned once, on the worker thread. The model
writes its own paragraphs, so while clean-up is on the Paragraphs setting is greyed out and applies
only when clean-up fails; a cleaned transcript is not re-flowed. Any failure keeps the text as
transcribed (cleanup.clean), and the status line says so.

Long sessions (2026-10-29): a small Recording light and timer by the controls, Voice detection for
this tab (`tm_vad`, on by default, also in the tray menu), Save audio (`tm_save_audio`: the recording
is moved to <Hebrish folder>/recordings instead of deleted; the folder is set in Settings),
"Transcripts are saved to: <folder>" with Open and Change… under the text box (2026-10-31), and the recorder's disk and stalled-stream checks in
`_tick` (longform.py).

Next recording (2026-10-31, `tm_next`): a new recording or file is either added to the end of the
transcript in the box (append, the default) or replaces it (new; the old one is in History).

Saving (B-74, B-75, 2026-10-31): Save writes Markdown with YAML front matter, the title as H1 and
the time as H2 (transcripts.py). With the title model downloaded (Models → Utilities; `titles`
on) it writes the title first (titles.py, cut to `title_max_chars`). The transcript's raw text (as
transcribed, before clean-up and edits) is kept beside it when it differs. *Save cleaned copy*
runs the chosen clean-up model over the box and saves the result as another version
(<stem>.cleaned.md), saving the original first if needed; <stem>.json links the versions."""

import threading
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSlider,
                               QToolButton, QVBoxLayout, QWidget)

from .. import (__version__, audio, cleanup, config, dictionary, disfluency, longform, mics, model_store,
               paragraphs, titles, transcripts)
from .icons import line_icon
from .mics import fill_combo
from .meter import LevelMeter, verdict

PARAGRAPH_S = 30
SHOW_PROGRESS_S = 5      # the progress bar shows only once a transcription has run this long
NEXT_MODES = (("Adds to this transcript", "append"), ("Starts a new transcript", "new"))
CONFIRM_DROP_S = 60      # Retake / Discard ask first when the recording is longer than this
LEVELS = ("docked", "shown", "floating")     # cfg tm_levels (B-45)
LIGHT = {"rec": ("● Recording", "#c0392b"), "paused": ("❚❚ Paused", "#b7791f")}


class _Sig(QObject):
    saved = Signal(object, object)     # Save: (path, title) or exception; what was saved
    copied = Signal(object)            # Save cleaned copy: (path, Result) or exception
    progress = Signal(float)
    done = Signal(object)
    loaded = Signal(object, str)       # samples or exception, file name
    tape = Signal(object, object)      # samples or exception, recording path
    flowed = Signal(int, object)       # re-flow generation, transcript text or exception
    dl_progress = Signal(object, object)   # bytes done, total
    dl_done = Signal(object)           # None or exception
    stage = Signal(str)                # a status line from the worker ("Cleaning up…")


PARAGRAPH_MODES = (("None", paragraphs.NONE), ("Time-based", paragraphs.TIME),
                   ("Paragraph model", paragraphs.MODEL))


class _LevelsWindow(QWidget):
    """The floating Levels panel: a tool window over the Hebrish window (Qt.Tool, so it stays
    above its parent and has no taskbar entry, but not above other apps). Closing it docks the
    panel (hidden); the page hides it while the main window is hidden."""
    closed = Signal()

    def __init__(self, parent):
        super().__init__(parent, Qt.Tool)
        self.setObjectName("levelsWindow")
        self.setWindowTitle("Levels: Hebrish")
        self.setMinimumWidth(380)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(14, 12, 14, 12)

    def closeEvent(self, ev):
        super().closeEvent(ev)
        self.closed.emit()


# Transcription recorder buttons: kind -> line icon. Colours are in style.TAPE_COLOURS.
TAPE_KINDS = {"record": "record", "pause": "pause", "stop": "stop", "retake": "undo",
              "discard": "trash", "transcribe": "send"}


def _tape_button(kind: str, label: str, tip: str) -> QToolButton:
    b = QToolButton(objectName="tapeButton", text=label)
    b.setProperty("kind", kind)
    b.setIcon(line_icon(TAPE_KINDS[kind], "white"))
    b.setIconSize(QSize(20, 20))
    b.setToolButtonStyle(Qt.ToolButtonIconOnly)
    b.setFixedSize(40, 40)
    b.setCursor(Qt.PointingHandCursor)
    b.setAccessibleName(label)
    if tip:
        b.setToolTip(f"{label}: {tip[0].lower()}{tip[1:]}")
    return b


def _clock(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


class TranscribePage(QWidget):
    def __init__(self, ctl, card, muted):
        super().__init__()
        self.ctl, self.cfg = ctl, ctl.cfg
        self.cancel = None
        self.sig = _Sig()
        self.sig.saved.connect(self._saved)
        self.sig.copied.connect(self._copied)
        self.sig.progress.connect(lambda f: self.pbar.setValue(int(f * 1000)))
        self.sig.done.connect(self._finished)
        self.sig.loaded.connect(self._file_loaded)
        self.sig.tape.connect(self._tape_loaded)
        self.sig.flowed.connect(self._flowed)
        self.sig.dl_progress.connect(self._dl_progress)
        self.sig.dl_done.connect(self._dl_done)
        self.sig.stage.connect(lambda t: self.ctl.win.status(t))
        self._last = None                # the last transcript, while it can be re-flowed (see _finished)
        self._doc = None                 # the transcript in the box, for Save (_new_doc)
        self._saving = False
        self._t0 = None                  # when the running transcription started
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
        self.btn_levels = QToolButton(text="Levels", checkable=True)
        self.btn_levels.setIcon(line_icon("mic"))
        self.btn_levels.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_levels.setToolTip("Show or hide the gain and the level meter. Hidden, recording "
                                   "still uses the gain you set.")
        self.btn_levels.clicked.connect(
            lambda: self._set_levels("docked" if self._levels_state != "docked" else "shown"))
        head.addWidget(self.btn_levels)
        b.addLayout(head)

        row = QHBoxLayout()
        self.mic = QComboBox()
        self.mic.setMinimumWidth(120)
        self.mic.setToolTip("The microphone for Transcription Mode (Voice Typing keeps its own). "
                            "Changing it while recording switches at once; the recording carries on.")
        row.addWidget(self.mic, 1)
        refresh = QToolButton()
        refresh.setIcon(line_icon("refresh"))
        refresh.setText("↻")
        refresh.setToolTip("Rescan microphones")
        refresh.clicked.connect(self._fill_mics)
        row.addWidget(refresh)
        b.addLayout(row)
        self._fill_mics()
        self.mic.currentIndexChanged.connect(self._on_mic)

        # Levels panel (B-45): one set of widgets, moved between the card and a floating window.
        self.levels = QWidget()
        lv = QVBoxLayout(self.levels)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(8)
        row = QHBoxLayout()
        row.addWidget(QLabel("Gain"))
        self.gain = QSlider(Qt.Horizontal, minimum=longform.GAIN_MIN_DB, maximum=longform.GAIN_MAX_DB,
                            value=int(self.cfg["tm_gain_db"]))
        self.gain.setToolTip("Digital gain on what is recorded. The meter shows the result: aim "
                             "for the green zone, and turn it down if the clip lamp lights.")
        self.gain.valueChanged.connect(self._on_gain)
        # _on_gain skips saving mid-drag: save where the drag ended (up to 1.012 a dragged gain was
        # applied but never saved, so it was lost at the next start)
        self.gain.sliderReleased.connect(lambda: self.cfg.set("tm_gain_db", self.gain.value()))
        row.addWidget(self.gain, 1)
        self.gain_label = QLabel()
        self.gain_label.setMinimumWidth(48)
        row.addWidget(self.gain_label)
        reset = QToolButton(text="Reset")
        reset.setToolTip("No gain")
        reset.clicked.connect(lambda: self.gain.setValue(0))
        row.addWidget(reset)
        self.btn_undock = QToolButton()
        self.btn_undock.clicked.connect(
            lambda: self._set_levels("shown" if self._levels_state == "floating" else "floating"))
        row.addWidget(self.btn_undock)
        lv.addLayout(row)
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
        lv.addWidget(self.meter_box)
        self._levels_home = b            # the card's layout; the panel sits after the mic row
        self._levels_at = b.count()
        b.addWidget(self.levels)
        self._float = None               # _LevelsWindow, made the first time it floats
        self._watched = None             # the main window, watched for show/hide
        state = self.cfg["tm_levels"]
        self._levels_state = state if state in LEVELS else "docked"

        row = QHBoxLayout()
        # Round icon buttons (1.012, Daniel): the overlay's and Android's record controls, one
        # colour per action (TAPE_KINDS), white line icons; the label is the tooltip and the
        # accessible name. Transcribe is a send arrow in the brand green.
        self.btn_rec = _tape_button("record", "Record", "Start a recording")
        self.btn_rec.clicked.connect(self._record)
        self.btn_pause = _tape_button("pause", "Pause", "")
        self.btn_pause.clicked.connect(self._pause)
        self.btn_retake = _tape_button("retake", "Retake", "Throw this recording away and start again")
        self.btn_retake.clicked.connect(self._retake)
        self.btn_stop = _tape_button("stop", "Stop", "Stop recording and keep the audio, to transcribe when you're ready")
        self.btn_stop.clicked.connect(self._stop)
        self.btn_go = _tape_button("transcribe", "Transcribe", "Stop (if recording) and transcribe")
        self.btn_go.clicked.connect(self._transcribe_tape)
        self.btn_drop_tape = _tape_button("discard", "Discard", "Discard this recording")
        self.btn_drop_tape.clicked.connect(self._discard)
        for w in (self.btn_rec, self.btn_pause, self.btn_stop, self.btn_retake, self.btn_drop_tape, self.btn_go):
            row.addWidget(w)
        row.addStretch(1)
        # Light and elapsed time: small, at the end of the controls, so they are there when you
        # look but don't pull the eye while you talk. The light is a steady colour, not a blink.
        self.light = QLabel()
        self.light.setStyleSheet("font-size: 12px;")
        row.addWidget(self.light)
        self.elapsed = muted()
        self.elapsed.setToolTip("Recorded so far. A recording can run up to "
                                f"{longform.MAX_S // 3600} hours; {longform.RECOMMENDED_S // 60}-minute "
                                "sessions are what it is tested for.")
        row.addWidget(self.elapsed)
        b.addLayout(row)

        row = QHBoxLayout()
        self.chk_vad = QCheckBox("Voice detection")
        self.chk_vad.setToolTip("Skip the silent stretches and trim long pauses before transcribing. "
                                "On by default here; Voice Typing has its own switch. Also in the tray menu.")
        self.chk_vad.setChecked(bool(self.cfg["tm_vad"]))
        self.chk_vad.toggled.connect(self.set_vad)
        row.addWidget(self.chk_vad)
        self.chk_keep = QCheckBox("Save audio")
        self.chk_keep.setChecked(bool(self.cfg["tm_save_audio"]))
        self.chk_keep.toggled.connect(lambda on: (self.cfg.set("tm_save_audio", on), self._keep_tip()))
        row.addWidget(self.chk_keep)
        row.addStretch(1)
        b.addLayout(row)
        self._keep_tip()

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
        head.addWidget(QLabel("Next recording"))
        self.next = QComboBox()
        for label, mode in NEXT_MODES:
            self.next.addItem(label, mode)
        self.next.setCurrentIndex(max(0, self.next.findData(self.cfg["tm_next"])))
        self.next.setToolTip("What a new recording or file does with the transcript in the box: add to "
                             "the end of it, or replace it (the earlier one stays in History).")
        self.next.currentIndexChanged.connect(lambda _i: self.cfg.set("tm_next", self.next.currentData()))
        head.addWidget(self.next)
        head.addSpacing(8)
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
        self.tidy = QCheckBox("Clean up", checked=bool(self.cfg["tm_cleanup"]))
        self.tidy.toggled.connect(self._on_tidy)
        head.addWidget(self.tidy)
        b.addLayout(head)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("The transcript lands here, and you can edit it. "
                                     "Another recording or file is added at the end. Paragraphs "
                                     "follow the Paragraphs setting above.")
        self.text.setStyleSheet("font-size: 14px;")
        b.addWidget(self.text, 1)
        self.sync_cleanup()
        # Voice Typing's paste at the cursor stays out of this box (1.012): read from the decode
        # thread, so a plain bool kept by focusChanged (focus goes to None when the window loses it).
        self.box_focused = False
        QApplication.instance().focusChanged.connect(
            lambda _old, new: setattr(self, "box_focused", new is self.text))
        row = QHBoxLayout()
        self.pbar = QProgressBar(maximum=1000)
        self.pbar.setFormat("Transcribing…")
        self._pbar_timer = QTimer(self, interval=500, timeout=self._pbar_tick)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(lambda: self.cancel and self.cancel.set())
        row.addWidget(self.pbar, 1)
        row.addWidget(self.btn_cancel)
        b.addLayout(row)
        row = QHBoxLayout()
        for label, fn, name in (("Copy", self._copy, "copy"), ("Save", self._save, "save"),
                                ("Save cleaned copy", self._clean_copy, "clean_copy"),
                                ("Clear", self._clear, "clear")):
            btn = QPushButton(label)
            btn.clicked.connect(fn)
            setattr(self, f"btn_{name}", btn)
            row.addWidget(btn)
            if name == "clean_copy":
                self.copy_model = QComboBox()
                self.copy_model.setMaximumWidth(240)
                self.copy_model.setToolTip("The clean-up model for Save cleaned copy")
                row.addWidget(self.copy_model)
        self.btn_save.setToolTip("Save to the transcripts folder as Markdown (title, date and the model "
                                 "in the header). With the title model downloaded, it writes a title first.")
        self.btn_clean_copy.setToolTip("Run the clean-up model chosen here over the transcript and save the "
                                       "result as a separate file beside the original, which is kept as it is "
                                       "(saved first if it isn't yet).")
        row.addStretch(1)

        self.words = muted()
        row.addWidget(self.words)
        b.addLayout(row)
        # Where Save writes (Daniel, 2026-10-31): the folder, with Open and Change…; the same
        # setting as Settings → Your data.
        row = QHBoxLayout()
        self.saved_to = muted()
        self.saved_to.setTextFormat(Qt.PlainText)
        self.saved_to.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.saved_to, 1)
        self.btn_open_saved = QPushButton(line_icon("folder"), "Open")
        self.btn_open_saved.setToolTip("Open the transcripts folder")
        self.btn_open_saved.clicked.connect(lambda: self.ctl.win._open_transcripts())
        row.addWidget(self.btn_open_saved)
        self.btn_change_saved = QPushButton("Change…")
        self.btn_change_saved.setToolTip("Save transcripts somewhere else (also in Settings → Your data)")
        self.btn_change_saved.clicked.connect(lambda: self.ctl.win._change_transcripts())
        row.addWidget(self.btn_change_saved)
        b.addLayout(row)
        self.sync_saved_to()
        self._fill_copy_models()
        self.text.textChanged.connect(self._count)
        lay.addWidget(box, 1)

        self._busy(False)
        self._count()
        self._place_levels()
        self._sync()
        self._show_leftover()

    # -- recorder --------------------------------------------------------------------
    def _fill_mics(self):
        fill_combo(self.mic, self.cfg, "tm_audio_device")

    def _on_mic(self, _i):
        self.cfg.set("tm_audio_device", self.mic.currentData())
        try:
            self.tape.switch_device(mics.resolve(self.cfg, "tm_audio_device")[0])
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

    def set_vad(self, on: bool):
        """The checkbox and the tray menu both land here."""
        self.cfg.set("tm_vad", bool(on))
        if self.chk_vad.isChecked() != bool(on):
            self.chk_vad.setChecked(bool(on))
        self.ctl.sync_tray_vad()

    def _keep_dir(self) -> Path:
        return config.recordings_folder(self.cfg)

    def sync_saved_to(self):
        """The 'Transcripts are saved to' line; the window calls it when a folder setting changes."""
        self.saved_to.setText(f"Transcripts are saved to: {config.transcripts_folder(self.cfg)}")
        self._keep_tip()

    def _keep_tip(self):
        tip = (f"Keep each recording once it is transcribed, in {self._keep_dir()}. It is saved as "
               "the model hears it: 16 kHz mono WAV with your gain applied (about 170 MB for 90 "
               "minutes). Off: the audio is deleted once the transcript is in History.")
        self.chk_keep.setToolTip(tip + " The folder is set in Settings → Your data.")

    # -- levels panel (B-45) ----------------------------------------------------------
    def _set_levels(self, state: str):
        """docked: hidden (the gain still applies); shown: in the card; floating: its own
        window. Remembered in tm_levels."""
        self._levels_state = state if state in LEVELS else "docked"
        if self.cfg["tm_levels"] != self._levels_state:
            self.cfg.set("tm_levels", self._levels_state)
        self._place_levels()

    def _on_screen(self) -> bool:
        win = self.window()
        return win is not self and win.isVisible()

    def _place_levels(self):
        st = self._levels_state
        floating = st == "floating" and self._on_screen()
        if floating:
            if self._float is None:
                self._float = _LevelsWindow(self.window())
                self._float.closed.connect(lambda: self._set_levels("docked"))
            if self.levels.parent() is not self._float:
                self._levels_home.removeWidget(self.levels)     # explicit: Qt may not do it
                self._float.lay.addWidget(self.levels)
            self.levels.show()
            self._float.show()
            self._float.raise_()
        else:
            if self._float is not None:
                self._float.hide()       # hide(), not close(): close means "dock it"
            if self._float is not None and self.levels.parent() is self._float:
                self._float.lay.removeWidget(self.levels)
                self._levels_home.insertWidget(self._levels_at, self.levels)
            # floating while the main window is hidden: kept here, hidden, until it shows
            self.levels.setVisible(st == "shown")
        self.btn_levels.setChecked(st != "docked")
        self.btn_undock.setText("Dock" if st == "floating" else "Undock")
        self.btn_undock.setIcon(line_icon("window" if st == "floating" else "window-out"))
        self.btn_undock.setToolTip("Put the levels back in the Record card" if st == "floating" else
                                   "Pop the levels out into a small window of their own")
        self._tick()                     # fill the readout now, not at the next timer tick

    def showEvent(self, ev):
        super().showEvent(ev)
        win = self.window()
        if win is not self and self._watched is not win:
            self._watched = win
            win.installEventFilter(self)
        if self._levels_state == "floating":
            self._place_levels()

    def eventFilter(self, obj, ev):
        if obj is self._watched and self._levels_state == "floating" and \
                ev.type() in (QEvent.Show, QEvent.Hide):
            QTimer.singleShot(0, self._place_levels)     # after the window's own show/hide
        return False

    # -- recorder controls -------------------------------------------------------------
    def _record(self):
        """Start a recording. Record is disabled while one is running: Pause/Resume is its own
        button (B-45; up to 1.002 Record turned into Pause)."""
        t = self.tape
        if t.active:
            return
        if self.ctl.state != "idle":
            self.ctl.win.status("Voice Typing is recording: stop it first.")
            return
        self.ctl.stop_monitor()
        try:
            room = longform.free_seconds()
        except OSError:
            room = None
        if room is not None and room < longform.RECOMMENDED_S and QMessageBox.question(
                self, "Low disk space", f"The disk has room for about {_clock(room)} of recording. "
                "Record anyway?") != QMessageBox.Yes:
            return
        try:
            t.start(mics.resolve(self.cfg, "tm_audio_device")[0])
        except Exception as e:
            QMessageBox.warning(self, "Couldn't open the microphone", str(e))
            return
        self._sync()

    def _pause(self):
        t = self.tape
        if not t.active:
            return
        try:
            t.resume() if t.paused else t.pause()
        except Exception as e:           # resume reopens the mic, which may be gone
            QMessageBox.warning(self, "Couldn't open the microphone",
                                f"{e}\n\nThe recording is paused; pick another mic and press Resume.")
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
        self._record()
        self._sync()

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
        if t.active and t.error:
            self._stop()
            self.ctl.notify("Transcription Mode", f"Couldn't write the recording ({t.error.strerror or t.error}). "
                            f"It stopped at {_clock(self._held_seconds())}; what was recorded is kept.")
            return
        if t.stalled:
            self._restart_stream()
        if t.active:
            self.elapsed.setText(_clock(t.seconds))
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

    def _restart_stream(self):
        """The mic stopped sending audio (unplugged, sound server restarted, back from suspend):
        reopen it. If it can't be opened, pause, so the file is kept and Resume tries again."""
        t = self.tape
        try:
            t.reopen()
            self.ctl.win.status("The microphone dropped out and was reconnected; the recording carries on.")
        except Exception as e:
            t.pause()
            self._sync()
            self.ctl.notify("Transcription Mode", f"The microphone dropped out ({e}). The recording is "
                            "paused: pick a mic and press Resume.")

    def _sync(self):
        """Buttons and the timer for the recorder's state: idle, recording, paused, stopped
        (a recording held for Transcribe), or busy transcribing."""
        t, busy = self.tape, self.cancel is not None
        rec, held = t.active, self._held is not None and not t.active
        paused = rec and t.paused
        self.btn_rec.setEnabled(not busy and not held and not rec)
        self.btn_rec.setToolTip("Wait for the transcription to finish" if busy else
                                "Transcribe or discard the stopped recording first" if held else
                                "Start a recording")
        for b in (self.btn_left_go, self.btn_left_del):     # did nothing while a job ran
            b.setEnabled(not busy)
            b.setToolTip("Wait for the transcription to finish" if busy else "")
        self.btn_pause.setText("Resume" if paused else "Pause")
        self.btn_pause.setIcon(line_icon("play" if paused else "pause", "white"))
        self.btn_pause.setAccessibleName(self.btn_pause.text())
        self.btn_pause.setToolTip("Carry on recording" if paused else
                                  "Pause the recording: the mic goes off until you press Resume")
        self.btn_pause.setEnabled(rec)
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
        light = LIGHT.get("paused" if paused else "rec" if rec else "")
        self.light.setVisible(light is not None)
        if light:
            self.light.setText(light[0])
            self.light.setStyleSheet(f"font-size: 12px; color: {light[1]};")
        self._tick()
        self.ctl.sync_tray_tape()

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
        self._busy(True)
        if self.cfg["tm_vad"] and len(samples) > 10 * 60 * audio.SAMPLE_RATE:
            self.ctl.win.status(f"Finding the speech in {_clock(len(samples) / audio.SAMPLE_RATE)} of "
                                "audio (about a minute for 90 minutes)…")
        started = time.monotonic()
        mode = self._asked = self._para_mode()
        tidy = self._cleanup_on()
        tidy_id = tidy["id"] if tidy else None
        note = ""
        if mode == paragraphs.MODEL and paragraphs.installed() is None and not tidy:
            mode = paragraphs.TIME
            note = (" The paragraph model is still downloading" if self._dl else
                    " The paragraph model isn't downloaded") + ", so paragraphs are time-based."

        def work():
            try:
                words = dictionary.load()
                fix = dictionary.compile(words)                  # personal dictionary, as in dictation
                # pieces are ~10-25 s; Time-based starts a paragraph every ~30 s of audio. With
                # the Paragraph model they are joined with spaces until the end.
                pieces = paragraphs.Pieces(PARAGRAPH_S * audio.SAMPLE_RATE)
                for text in self.ctl.engine.transcribe_chunks(samples, cancel, vad=self.cfg["tm_vad"]):
                    done, total = self.ctl.engine.last_progress
                    text = fix(disfluency.chop(text))
                    pieces.add(text, done, mode)     # shown when it is all done (2026-10-31)
                    self.sig.progress.emit(done / total)
                body, err, tidied = None, None, None
                if tidy and pieces.items and not cancel.is_set():
                    self.sig.stage.emit("Cleaning up the transcript…")
                    tidied = cleanup.run(pieces.text(paragraphs.NONE), keep=tuple(e["word"] for e in words),
                                         aid=tidy_id)
                    if tidied.cleaned:
                        body = tidied.text
                if body is None and mode == paragraphs.MODEL and pieces.items:
                    try:
                        body = pieces.text(paragraphs.MODEL, paragraphs.breaker())
                    except Exception as e:   # fall back, never lose text
                        body, err = pieces.text(paragraphs.TIME), e
                self.sig.done.emit((len(samples) / audio.SAMPLE_RATE, time.monotonic() - started,
                                    cancel.is_set(), pieces, mode, body, err, note, tidied))
            except Exception as e:
                self.sig.done.emit(e)
        threading.Thread(target=work, daemon=True).start()

    def _finished(self, result):
        self.cancel = None
        source, self._source = self._source, None
        if source is not None and source == self._held:
            self._held = None                # transcribed or not, it's no longer "stopped"
        self._busy(False)
        if isinstance(result, Exception):
            self._show_leftover()            # the recording stays on disk, offered again
            QMessageBox.warning(self, "Transcription failed", str(result))
            return
        audio_s, took, cancelled, pieces, mode, body, err, note, tidied = result
        cleaned = tidied is not None and tidied.cleaned
        flow = mode
        if mode == paragraphs.MODEL and pieces.items:
            flow = paragraphs.TIME if (err or body is None or cleaned) else paragraphs.MODEL
        raw = pieces.text(paragraphs.TIME if flow == paragraphs.MODEL and cleaned else flow) if pieces.items else ""
        if cleaned:
            shown = body
        elif mode == paragraphs.MODEL and pieces.items and body is not None:
            shown = body
        else:
            shown = pieces.text(mode if mode != paragraphs.MODEL else paragraphs.TIME) if pieces.items else ""
        extra = None
        if cleaned:
            extra = {"cleanup": f"{tidied.model} {tidied.version}",     # id and version that ran
                     "cleanup_kept_raw": tidied.kept_raw}
            note += (f" Cleaned up with {tidied.name}." if not tidied.kept_raw else
                     f" Cleaned up, except {tidied.kept_raw} of {tidied.chunks} parts kept as "
                     f"transcribed ({tidied.error}).")
        elif tidied is not None:
            note += f" Clean-up failed ({tidied.error}), so the transcript is as transcribed."
        if not cleaned and mode == paragraphs.MODEL and err:
            note += f" The paragraph model failed ({err}), so paragraphs are time-based."
        self._from = self._place(shown)
        if pieces.items and not cleaned:     # the model's own words and paragraphs: never re-flowed
            self._last = {"from": self._from, "pieces": pieces, "mode": flow,
                          "shown": self.text.toPlainText(), "rid": None}
        if shown.strip():
            self._note_doc(raw, audio_s, "recording" if source else "file",
                           f"{tidied.name} {tidied.version}" if cleaned else None)
        if not cancelled:
            rid = self.ctl.remember(self.text.toPlainText()[self._from:].strip(),
                                    source="record" if source else "file",
                                    seconds=audio_s, extra=extra)
            if self._last:
                self._last["rid"] = rid
            if source is not None:
                note += self._dispose(source)
        self._show_leftover()
        msg = f"Transcribed {_clock(audio_s)} of audio in {took:.1f} s"
        self.ctl.win.status(msg + (" (cancelled part-way)." if cancelled else ".") + note)
        if self._last and (self._para_mode() != self._asked or (     # changed while transcribing,
                mode != self._asked and err is None and paragraphs.installed() is not None)):
            self._reflow()                   # or the model finished downloading meanwhile

    def _place(self, text: str) -> int:
        """Put a finished transcript in the box, in one go: after what is there (Next recording:
        append) or in its place (new). Returns where it starts, for History and re-flowing."""
        box = self.text.toPlainText()
        text = text.strip()
        if not text:                         # nothing transcribed (cancelled early): box untouched
            return len(box)
        new = self.cfg["tm_next"] == "new" or not box.strip()
        if new:
            self._doc = None
            start, full = 0, text
        else:
            head = box.rstrip()
            start, full = len(head) + 2, head + "\n\n" + text
        c = self.text.textCursor()
        c.select(QTextCursor.SelectionType.Document)
        c.insertText(full)                   # one undo step
        c.movePosition(QTextCursor.MoveOperation.End)
        self.text.setTextCursor(c)
        self.text.ensureCursorVisible()
        return min(start, len(self.text.toPlainText()))

    def _note_doc(self, raw: str, seconds: float, source: str, cleanup_model: str | None):
        """Remember what Save needs about the transcript in the box: its time (the first part's),
        the raw text of each part, the speech model, audio length, source and clean-up model."""
        cur = model_store.active()
        model = cur[1].version if cur else ""
        d = self._doc
        if d is None:
            d = self._doc = {"when": time.time(), "raw": [], "models": [], "sources": [], "cleanup": [],
                             "seconds": 0.0, "saved": None}
        d["raw"].append(raw.strip())
        d["seconds"] += seconds
        for key, v in (("models", model), ("sources", source), ("cleanup", cleanup_model)):
            if v and v not in d[key]:
                d[key].append(v)

    def _meta(self) -> dict:
        d = self._doc or {}
        meta = {"generator": f"Hebrish {__version__}"}
        if d.get("models"):
            meta["model"] = ", ".join(d["models"])
        else:
            cur = model_store.active()
            if cur:
                meta["model"] = cur[1].version
        if d.get("seconds"):
            meta["audio_seconds"] = round(d["seconds"], 1)
        if d.get("sources"):
            meta["source"] = ", ".join(d["sources"])
        if d.get("cleanup"):
            meta["cleanup_model"] = ", ".join(d["cleanup"])
        return meta

    def _dispose(self, source: Path) -> str:
        """A transcribed recording: moved to the Save audio folder when that is on, else deleted.
        Returns a note for the status line."""
        if not self.cfg["tm_save_audio"]:
            source.unlink(missing_ok=True)
            return ""
        try:
            return f" Audio saved: {longform.keep(source, str(config.recordings_folder(self.cfg)))}"
        except OSError as e:                 # left where it is: offered again as a leftover
            return f" Couldn't save the audio ({e}); it is still in {source.parent}."

    # -- clean-up (B-40) --------------------------------------------------------------
    def _cleanup_on(self) -> dict | None:
        """The clean-up model's catalogue entry when *Clean up* is on and it is downloaded."""
        return cleanup.ready(self.cfg["tm_cleanup_model"]) if self.cfg["tm_cleanup"] else None

    def sync_cleanup(self):
        """Show *Clean up* only once the chosen model is downloaded, name it in the tooltip, and
        grey out Paragraphs while it is on (the model writes the paragraphs). Called at start,
        after a download or delete, and when the Utilities checkbox or choice changes."""
        model = cleanup.ready(self.cfg["tm_cleanup_model"])
        have = model is not None
        self.tidy.blockSignals(True)
        self.tidy.setChecked(bool(self.cfg["tm_cleanup"]))
        self.tidy.blockSignals(False)
        self.tidy.setVisible(have)
        self.tidy.setToolTip(
            f"Clean up each finished transcript with {cleanup.label(model) if have else 'the clean-up model'}"
            + (" (experimental)" if have and model.get("experimental") else "") +
            ": punctuation, capitals, filler and repeated words, numbers, and paragraphs (they replace "
            "the Paragraphs setting).\nRuns on this computer after the transcript is done. If it fails, "
            "the transcript stays as transcribed. Choose and download the model in Models → Utilities.")
        self._fill_copy_models()
        on = self._cleanup_on() is not None
        self.para.setEnabled(not on)
        self.para.setToolTip(self.para.toolTip().split("\n\nClean-up is on")[0] +
                             ("\n\nClean-up is on, so the clean-up model sets the paragraphs; this "
                              "applies only if it fails." if on else ""))

    def _fill_copy_models(self):
        """Save cleaned copy: the downloaded clean-up models, the chosen one first selected."""
        if not hasattr(self, "copy_model"):        # sync_cleanup runs once before the row exists
            return
        have = [e for e in cleanup.entries() if cleanup.installed(e["id"]) is not None]
        cur = self.copy_model.currentData() or (cleanup.ready(self.cfg["tm_cleanup_model"]) or {}).get("id")
        self.copy_model.blockSignals(True)
        self.copy_model.clear()
        for e in have:
            self.copy_model.addItem(cleanup.label(e), e["id"])
        i = self.copy_model.findData(cur)
        self.copy_model.setCurrentIndex(i if i >= 0 else 0)
        self.copy_model.blockSignals(False)
        for w in (self.btn_clean_copy, self.copy_model):
            w.setVisible(bool(have))
        self.copy_model.setVisible(len(have) > 1)

    def _on_tidy(self, on: bool):
        self.cfg.set("tm_cleanup", on)
        self.sync_cleanup()
        use = getattr(self.ctl.win, "cleanup_check", None)      # the Utilities checkbox
        if use is not None and use.isChecked() != on:
            use.blockSignals(True)
            use.setChecked(on)
            use.blockSignals(False)

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
        self._t0 = time.monotonic() if on else None
        self.pbar.setVisible(False)          # _pbar_tick shows it after SHOW_PROGRESS_S
        self.btn_cancel.setVisible(on)
        self.pbar.setValue(0)
        if on:
            self._pbar_timer.start()
            self.ctl.win.status("Transcribing…")
        else:
            self._pbar_timer.stop()
        if hasattr(self, "btn_rec"):
            self._sync()

    def _pbar_tick(self):
        if self._t0 is None:
            return
        took = time.monotonic() - self._t0
        if took >= SHOW_PROGRESS_S:
            self.pbar.setFormat(f"Transcribing… {_clock(took)}")
            self.pbar.setVisible(True)

    # -- output ----------------------------------------------------------------------
    def _count(self):
        t = self.text.toPlainText()
        n = len(t.split())
        self.words.setText(f"{n} word{'s' if n != 1 else ''}" if n else "")
        for b in (self.btn_copy, self.btn_save, self.btn_clean_copy, self.btn_clear):
            b.setEnabled(bool(t.strip()) and not (self._saving and b in (self.btn_save, self.btn_clean_copy)))

    def _copy(self):
        self.ctl.win._copy(self.text.toPlainText(), "Transcript copied.")

    def _save_now(self, text: str) -> tuple[Path, str | None]:
        """Worker thread: save `text` (title first, when the title model is there), or return the
        file it was already saved as, unchanged. Raises OSError."""
        d = self._doc
        if d and d["saved"] and d["saved"][1] == text:
            return d["saved"][0], d["saved"][2]
        title = None
        if self.cfg["titles"] and titles.ready() is not None:
            self.sig.stage.emit("Writing a title…")
            title = titles.title(text, titles.limit(self.cfg["title_max_chars"]))
        raw = "\n\n".join(r for r in d["raw"] if r) if d else None
        path = transcripts.save(text, str(config.transcripts_folder(self.cfg)), title=title,
                                when=d["when"] if d else None, meta=self._meta(), raw=raw)
        if d is not None:
            d["saved"] = (path, text, title)
        else:
            self._doc = {"when": time.time(), "raw": [], "models": [], "sources": [], "cleanup": [],
                         "seconds": 0.0, "saved": (path, text, title)}
        return path, title

    def _set_saving(self, on: bool):
        self._saving = on
        self._count()

    def _save(self):
        """B-74/B-75: straight to the transcripts folder (shown under the box), as Markdown."""
        if self._saving:
            return
        text = self.text.toPlainText()
        d = self._doc
        if d and d["saved"] and d["saved"][1] == text:
            self.ctl.win.status(f"Already saved: {d['saved'][0]}")
            return
        self._set_saving(True)

        def work():
            try:
                self.sig.saved.emit(*self._save_now(text))
            except Exception as e:
                self.sig.saved.emit(e, None)
        threading.Thread(target=work, daemon=True).start()

    def _saved(self, path, title):
        self._set_saving(False)
        if isinstance(path, Exception):
            QMessageBox.warning(self, "Couldn't save", f"Couldn't save the transcript:\n{path}")
            return
        self.ctl.win.status(f"Saved {path}" + (f" ({title})" if title else ""))

    def _clean_copy(self):
        """Save cleaned copy: the original saved (or already saved), then the clean-up model's
        version of it as <stem>.cleaned.md beside it. The box is left as it is."""
        aid = self.copy_model.currentData()
        if self._saving or not aid:
            return
        text = self.text.toPlainText()
        keep = tuple(e["word"] for e in dictionary.load())
        self._set_saving(True)

        def work():
            try:
                path, _title = self._save_now(text)
                self.sig.stage.emit("Cleaning up a copy…")
                r = cleanup.run(text, keep=keep, aid=aid)
                if not r.cleaned:
                    raise RuntimeError(f"the clean-up model failed ({r.error})")
                extra = {"cleanup_model": f"{r.name} {r.version}"}
                if r.kept_raw:
                    extra["cleanup_kept_raw"] = f"{r.kept_raw} of {r.chunks} parts"
                self.sig.copied.emit((transcripts.add_version(path, "cleaned", r.text, extra), r))
            except Exception as e:
                self.sig.copied.emit(e)
        threading.Thread(target=work, daemon=True).start()

    def _copied(self, result):
        self._set_saving(False)
        if isinstance(result, Exception):
            QMessageBox.warning(self, "Couldn't save a cleaned copy", str(result))
            return
        path, r = result
        self.ctl.win.status(f"Cleaned copy saved: {path}" + (
            f" ({r.kept_raw} of {r.chunks} parts kept as transcribed)" if r.kept_raw else ""))

    def _clear(self):
        if QMessageBox.question(self, "Clear transcript", "Clear the text box?") == QMessageBox.Yes:
            self.text.clear()
            self._last = None
            self._doc = None
