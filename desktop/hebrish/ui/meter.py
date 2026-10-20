"""The Dictate tab's level meter: is the mic quiet, in the good zone, loud, or clipping?

Reads a Recorder's `rms`, `peak` and `clipped_at` (set in its audio callback) on a timer.
The bar is block RMS in dBFS over -60..0, drawn on zone bands: too quiet below
audio.QUIET_DB, good up to audio.LOUD_DB, loud above it, and the last 3 dB red. A tick marks
the peak, and the clip lamp stays lit for CLIP_HOLD_S after a block reaches audio.CLIP_PEAK.
"""

import time

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from .. import audio

FLOOR_DB = -60.0
CLIP_HOLD_S = 1.5
ZONES = [(FLOOR_DB, audio.QUIET_DB, "#9aa3a0"), (audio.QUIET_DB, audio.LOUD_DB, "#2e9e5b"),
         (audio.LOUD_DB, -3.0, "#E8A317"), (-3.0, 0.0, "#D62828")]


def _x(db: float, w: float) -> float:
    return max(0.0, min(1.0, (db - FLOOR_DB) / -FLOOR_DB)) * w


def verdict(rms_db: float, clipping: bool) -> tuple[str, str]:
    """(short label, colour) for the readout next to the meter."""
    if clipping:
        return "Clipping: turn the input down or move back", ZONES[3][2]
    if rms_db < audio.QUIET_DB:
        return "Too quiet (or not talking)", "#7a8481"
    if rms_db <= audio.LOUD_DB:
        return "Good level", ZONES[1][2]
    return "Loud: fine, but close to clipping", "#b07a0c"


class LevelMeter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(16)
        self.setMaximumHeight(16)
        self.rms_db = self.peak_db = FLOOR_DB
        self.clipping = False

    def set_source(self, rec):
        """rec: an audio.Recorder, or None for an empty meter."""
        if rec is None or rec.paused:
            self.rms_db = self.peak_db = FLOOR_DB
            self.clipping = False
        else:
            self.rms_db, self.peak_db = audio.db(rec.rms), audio.db(rec.peak)
            self.clipping = time.monotonic() - rec.clipped_at < CLIP_HOLD_S
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        lamp = 22
        w, h = self.width() - lamp - 6, self.height()
        for lo, hi, col in ZONES:           # faint zone bands
            c = QColor(col)
            c.setAlpha(55)
            p.fillRect(QRectF(_x(lo, w), 0, _x(hi, w) - _x(lo, w), h), c)
        level = _x(self.rms_db, w)
        for lo, hi, col in ZONES:           # the bar, coloured by zone
            a, b = _x(lo, w), min(_x(hi, w), level)
            if b > a:
                p.fillRect(QRectF(a, 3, b - a, h - 6), QColor(col))
        if self.peak_db > FLOOR_DB:
            px = _x(self.peak_db, w)
            p.fillRect(QRectF(px - 1, 0, 2, h), self.palette().text())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(ZONES[3][2] if self.clipping else "#c9cfcc"))
        p.drawRoundedRect(QRectF(w + 6, 0, lamp, h), 4, 4)
        p.setPen(QColor("white"))
        f = p.font()
        f.setPixelSize(9)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(w + 6, 0, lamp, h), Qt.AlignCenter, "CLIP")
