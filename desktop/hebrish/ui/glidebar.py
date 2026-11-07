"""The download bar: a slim rounded track whose fill glides to each new value.

A download reports in jumps (1 MiB reads, whole files on resume), so the fill eases towards the
latest figure instead of stepping there, and a soft sheen crosses it while it is on screen, so a
stalled moment still looks alive. Android's twin is GlideBar.kt: keep the height, timings and
colours the same.
"""

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from .style import colours

HEIGHT = 6
GLIDE_MS = 350
SHEEN_MS = 1600
SHEEN_WIDTH = 0.3             # of the bar's width


class GlideBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(HEIGHT)
        self.shown = 0.0
        self._glide = QVariantAnimation(self, duration=GLIDE_MS, easingCurve=QEasingCurve.OutCubic)
        self._glide.valueChanged.connect(self._move)
        self._sheen = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=SHEEN_MS, loopCount=-1)
        self._sheen.valueChanged.connect(lambda _v: self.update())

    def set_fraction(self, frac: float):
        """Glide from wherever the fill is now to `frac` (0 to 1)."""
        self._glide.stop()
        self._glide.setStartValue(self.shown)
        self._glide.setEndValue(max(0.0, min(1.0, float(frac))))
        self._glide.start()

    def _move(self, value):
        self.shown = float(value)
        self.update()

    def showEvent(self, ev):
        super().showEvent(ev)
        self._sheen.start()

    def hideEvent(self, ev):
        """Hidden means that download is over: the next one starts from empty."""
        super().hideEvent(ev)
        self._sheen.stop()
        self._glide.stop()
        self.shown = 0.0

    def paintEvent(self, _ev):
        c = colours()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        r = QRectF(self.rect())
        radius = r.height() / 2
        p.setBrush(QColor(c["line"]))
        p.drawRoundedRect(r, radius, radius)
        fill = QRectF(r.left(), r.top(), r.width() * self.shown, r.height())
        if fill.width() < r.height():             # too short to round: wait for the first few pixels
            return
        path = QPainterPath()
        path.addRoundedRect(fill, radius, radius)
        p.fillPath(path, QColor(c["accent"]))
        band = r.width() * SHEEN_WIDTH
        x = -band + (fill.width() + band) * float(self._sheen.currentValue() or 0.0)
        grad = QLinearGradient(x, 0, x + band, 0)
        clear, soft = QColor(255, 255, 255, 0), QColor(255, 255, 255, 90)
        grad.setColorAt(0, clear)
        grad.setColorAt(0.5, soft)
        grad.setColorAt(1, clear)
        p.fillPath(path, grad)
