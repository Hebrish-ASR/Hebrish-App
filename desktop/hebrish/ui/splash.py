"""Start-up screen: the mark, the name, what is loading, and a thin moving bar.

Shown by main() before the Controller is built (not with --hidden), and closed by the
Controller once the model is loaded, or straight away when there is no model to load.
On Wayland the compositor places it (a client can't), normally centred.
"""

import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from .. import __version__
from ..config import APP_NAME, TAGLINE
from .style import BRAND_GREEN, INK, MUTED, PAPER, display_font

W, H = 420, 260
MIN_S = 0.9                   # long enough to read, so it doesn't just flash


class Splash(QWidget):
    def __init__(self, icon):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(W, H)
        self.setWindowTitle(APP_NAME)
        self._logo = icon.pixmap(176, 176)          # drawn at 88 px, sharp on HiDPI
        self._logo.setDevicePixelRatio(2.0)
        self.message = "Starting…"
        self._t0 = time.monotonic()
        self._phase = 0.0
        self._anim = QTimer(self, interval=16, timeout=self._tick)
        self._anim.start()
        scr = QApplication.primaryScreen()
        if scr:                                 # honoured on X11 and Windows
            self.move(scr.availableGeometry().center() - self.rect().center())

    def _tick(self):
        self._phase = (self._phase + 0.012) % 1.0
        self.update()

    def set_message(self, text: str):
        self.message = text
        self.update()
        QApplication.processEvents()

    def finish(self, then=None):
        """Close once MIN_S has passed since it appeared, then call `then`."""
        def done():
            self._anim.stop()
            self.close()
            if then:
                then()
        QTimer.singleShot(max(0, int((MIN_S - (time.monotonic() - self._t0)) * 1000)), done)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        for i in range(8, 0, -1):                       # soft shadow
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 6))
            p.drawRoundedRect(r.adjusted(-i, -i + 3, i, i + 3), 16 + i, 16 + i)
        p.setBrush(QColor(PAPER))
        p.setPen(QPen(QColor("#e2dccf"), 1))
        p.drawRoundedRect(r, 16, 16)

        p.drawPixmap(int(r.center().x() - 44), int(r.top() + 26), self._logo)
        p.setFont(display_font(30))
        p.setPen(QColor(INK))
        p.drawText(QRectF(r.left(), r.top() + 120, r.width(), 40), Qt.AlignCenter, APP_NAME)
        f = QFont(self.font())
        f.setPixelSize(13)
        p.setFont(f)
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(r.left(), r.top() + 158, r.width(), 20), Qt.AlignCenter, TAGLINE)
        f.setPixelSize(12)
        p.setFont(f)
        line = QRectF(r.left() + 22, r.bottom() - 44, r.width() - 44, 18)
        p.drawText(line, Qt.AlignLeft | Qt.AlignVCenter, self.message)
        p.drawText(line, Qt.AlignRight | Qt.AlignVCenter, f"v{__version__}")

        track = QRectF(r.left() + 22, r.bottom() - 20, r.width() - 44, 3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#e2dccf"))
        p.drawRoundedRect(track, 1.5, 1.5)
        seg = track.width() * 0.28                       # indeterminate: a segment sweeping across
        x = track.left() - seg + (track.width() + seg) * self._phase
        bar = QRectF(max(track.left(), x), track.top(), 0, track.height())
        bar.setRight(min(track.right(), x + seg))
        if bar.width() > 0:
            p.setBrush(QColor(BRAND_GREEN))
            p.drawRoundedRect(bar, 1.5, 1.5)
