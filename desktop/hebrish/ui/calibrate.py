"""The Noise filter calibration dialog (calibrate.py has the method). Voice Typing tab > Calibrate."""

import threading
import time

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QHeaderView, QLabel, QProgressBar, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from .. import audio, calibrate, mics

STEPS = (("Stay quiet", "Don't speak. Hebrish is listening to your room.", calibrate.QUIET_S),
         ("Speak normally", "Talk the way you do when you dictate, at your usual distance from the mic. "
                            "Say anything: what you did today will do.", calibrate.SPEECH_S))
HEADERS = ("Date", "Microphone", "Room", "Speech", "Safe", "Optimized", "Applied")


def summary(r: calibrate.Result) -> str:
    """The plain-words verdict shown over the two options."""
    if not r.heard_speech:
        return "Hebrish couldn't hear enough speech over the room. Move closer to the mic or check that it's the right one, then try again."
    if not r.noise_beaten:
        return ("Hebrish heard something like speech during the quiet part, and the filter can't keep it out at any "
                "setting. If a TV or someone talking was on, try again without it. Your setting hasn't changed.")
    if r.clean:
        return "Your speech stands clear of the room, so either option should work well."
    if r.clips:
        return ("Your speech and the room are close together here, so no setting does both jobs. "
                "Optimized will clip some of your words.")
    return "Your speech and the room are fairly close, so choose which risk you prefer."


def option(r: calibrate.Result, kept: float, noise_s: float) -> str:
    return f"Keeps {kept:.0%} of your speech. Room noise heard as speech: {noise_s:.1f} of {calibrate.QUIET_S} seconds."


class CalibrateDialog(QDialog):
    measured = Signal(object, object)        # Result or None, error

    def __init__(self, parent, ctl, on_apply):
        super().__init__(parent)
        self.ctl, self.on_apply = ctl, on_apply
        self.rec = audio.Recorder()
        self.takes, self.step, self.started, self.row = [], 0, 0.0, None
        self.setWindowTitle("Calibrate the noise filter")
        self.setMinimumWidth(720)
        lay = QVBoxLayout(self)
        self.title = QLabel("Find the right Noise filter for this mic and room")
        self.title.setStyleSheet("font-weight: 600; font-size: 15px;")
        lay.addWidget(self.title)
        self.text = QLabel(f"This takes {calibrate.QUIET_S + calibrate.SPEECH_S} seconds: first stay quiet, then speak "
                           "normally. The recordings are measured and then thrown away. Nothing changes until you apply a setting.")
        self.text.setWordWrap(True)
        lay.addWidget(self.text)
        self.bar = QProgressBar(textVisible=False)
        self.bar.hide()
        lay.addWidget(self.bar)
        self.btn_safe = QPushButton()
        self.btn_opt = QPushButton()
        self.safe_note, self.opt_note = QLabel(), QLabel()
        for b, note, tip in ((self.btn_safe, self.safe_note, "Lower: less chance of losing words, more chance of stray words from noise."),
                             (self.btn_opt, self.opt_note, "Closer to your speech: fewer stray words, more chance of clipping soft words.")):
            b.setToolTip(tip)
            note.setWordWrap(True)
            note.setStyleSheet("color: gray; font-size: 12px;")
            b.hide()
            note.hide()
            lay.addWidget(b)
            lay.addWidget(note)
        row = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_start.clicked.connect(self.begin)
        row.addWidget(self.btn_start)
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        lay.addLayout(row)
        lay.addWidget(QLabel("Past calibrations"))
        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeToContents)
        head.setSectionResizeMode(1, QHeaderView.Stretch)      # the mic's name takes what's left
        lay.addWidget(self.table)
        self.timer = QTimer(self, interval=100)
        self.timer.timeout.connect(self._tick)
        self.measured.connect(self._show)
        self.btn_safe.clicked.connect(lambda: self._apply(self.result.safe))
        self.btn_opt.clicked.connect(lambda: self._apply(self.result.optimized))
        self.fill()

    def fill(self):
        rows = self.ctl.history.calibrations()
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            cells = (time.strftime("%Y-%m-%d %H:%M", time.localtime(r["at"])), r["mic"] or "System default",
                     f"{r['noise_db']:.0f} dB", f"{r['speech_db']:.0f} dB", str(r["safe"]), str(r["optimized"]),
                     "" if r["applied"] is None else str(r["applied"]))
            for j, c in enumerate(cells):
                self.table.setItem(i, j, QTableWidgetItem(c))

    def begin(self):
        if getattr(self.ctl, "state", "idle") != "idle":
            self.text.setText("Finish the current take first, then start again.")
            return
        self.ctl.stop_monitor()
        for w in (self.btn_safe, self.btn_opt, self.safe_note, self.opt_note):
            w.hide()
        self.takes, self.step = [], 0
        self.btn_start.setEnabled(False)
        self._next()

    def _next(self):
        title, text, seconds = STEPS[self.step]
        self.title.setText(title)
        self.text.setText(text)
        self.bar.setRange(0, seconds * 10)
        self.bar.setValue(0)
        self.bar.show()
        try:
            self.rec.start(mics.resolve(self.ctl.cfg)[0])
        except Exception as e:
            self._stopped(f"Couldn't open the microphone: {e}")
            return
        self.started = time.monotonic()
        self.timer.start()

    def _tick(self):
        title, _, seconds = STEPS[self.step]
        left = seconds - (time.monotonic() - self.started)
        self.bar.setValue(int((seconds - left) * 10))
        self.title.setText(f"{title}: {max(0, int(left + 0.99))}")
        if left > 0:
            return
        self.timer.stop()
        self.takes.append(self.rec.stop())
        self.step += 1
        if self.step < len(STEPS):
            self._next()
            return
        self.title.setText("Measuring…")
        self.text.setText("Trying each setting on your recordings.")
        self.bar.setRange(0, 0)
        threading.Thread(target=self._measure, args=tuple(self.takes), daemon=True).start()
        self.takes = []

    def _measure(self, quiet, speech):
        try:
            self.measured.emit(calibrate.run(quiet, speech), None)
        except Exception as e:
            self.measured.emit(None, e)

    def _stopped(self, message):
        self.title.setText("Calibrate the noise filter")
        self.text.setText(message)
        self.bar.hide()
        self.btn_start.setText("Try again")
        self.btn_start.setEnabled(True)

    def _show(self, r, error):
        if error is not None or r is None:
            self._stopped(f"Calibration needs Silero VAD, which isn't available: {error}" if error else
                          "Calibration needs Silero VAD, which isn't available here.")
            return
        self.result = r
        self._stopped(summary(r))
        self.title.setText("Your result")
        self.btn_start.setText("Run it again")
        if not r.usable:
            return
        name = mics.resolve(self.ctl.cfg)[1] or audio.default_input_name()
        self.row = self.ctl.history.add_calibration(name, r.noise_db, r.speech_db, r.safe, r.optimized)
        self.fill()
        self.btn_safe.setText(f"Apply Safe: {r.safe}")
        self.safe_note.setText(option(r, r.safe_kept, r.safe_noise_s))
        self.btn_opt.setText(f"Apply Optimized: {r.optimized}")
        self.opt_note.setText(option(r, r.optimized_kept, r.optimized_noise_s))
        for w in (self.btn_safe, self.safe_note):
            w.show()
        if r.optimized != r.safe:
            self.btn_opt.show()
            self.opt_note.show()

    def _apply(self, level):
        self.on_apply(level)
        if self.row is not None:
            self.ctl.history.set_calibration_applied(self.row, level)
        self.fill()
        self.title.setText(f"Noise filter set to {level}")

    def done(self, code):
        self.timer.stop()
        if self.rec.active:
            self.rec.stop()
        super().done(code)
