"""Floating overlay: a small always-on-top pill for the hotkey take, like the Android
floating mic. The mic turns red while listening (click = Stop) and a bar beside it shows the
timer, a level meter, Pause/Resume, Retake and Discard; then "Transcribing…" and "Inserted".
Drag it anywhere; the position is saved. The bar opens towards the middle of the screen.

It must never take keyboard focus, because the transcript is pasted into whatever has it.
- Windows and X11 sessions: an in-process window, Tool + StaysOnTop + WindowDoesNotAcceptFocus
  (WS_EX_NOACTIVATE on Windows; on xcb also X11BypassWindowManagerHint = override-redirect).
- Wayland: xdg-shell gives a client no way to place a window, keep it above others, or map it
  without focus (Mutter focuses new toplevels). So the overlay runs in a child process forced
  onto the xcb platform (XWayland) as an override-redirect window: compositors put those where
  they ask, stack them above managed windows and never give them focus. The main app stays
  native Wayland. With no XWayland ($DISPLAY unset) the overlay is unavailable.
"No text field" (state `nofield`, 1.000): after a take that found no text field to paste into
(hebrish.focus), a label, a Paste button and ×: click into the right field, then Paste. It
works because the overlay never takes the focus; the mic does the same as Paste.
Parent and child talk JSON lines over the child's stdin/stdout: the parent sends
{"visible", "state", "seconds", "level", "paused", "opacity", "pos"}, the child sends
{"action": "toggle|pause|retake|discard|paste_last|dismiss_no_field"} and {"pos": [x, y]} after a drag.
"""

import json
import math
import os
import sys
from collections import deque

from PySide6.QtCore import QObject, QPoint, QPointF, QProcess, QProcessEnvironment, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QToolTip, QWidget

from .style import AMBER, BLUE, RED

GREEN = "#2E8B57"
PANEL = QColor(20, 28, 38, 238)
H = 56                    # pill height = the mic's square
MIC = 46                  # mic circle diameter
BTN = 32
BARS = 14

TIPS = {"mic": {"idle": "Start dictation", "recording": "Stop and transcribe",
                "busy": "Transcribing", "done": ""},
        "pause": "Pause", "resume": "Resume", "retake": "Retake: discard and start again",
        "discard": "Discard this take",
        "paste": "Paste the last transcription where the cursor is now",
        "dismiss": "Dismiss"}
TIPS["mic"]["nofield"] = TIPS["paste"]


def mode() -> tuple[str, str]:
    """('inproc' | 'child' | '', reason when unavailable), for the running QGuiApplication."""
    plat = QGuiApplication.platformName()
    if plat.startswith("wayland"):
        if os.environ.get("DISPLAY"):
            return "child", ""
        return "", "The overlay needs XWayland, and this session has none ($DISPLAY is not set)."
    if plat in ("offscreen", "minimal"):
        return "", "No display."
    return "inproc", ""


class Overlay(QWidget):
    action = Signal(str)
    moved = Signal(int, int)

    def __init__(self):
        flags = (Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                 | Qt.WindowDoesNotAcceptFocus)
        if QGuiApplication.platformName() == "xcb":
            flags |= Qt.X11BypassWindowManagerHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)
        self.setWindowTitle("Hebrish overlay")
        self.state, self.seconds, self.paused, self.opacity = "idle", 0.0, False, 0.85
        self.levels = deque([0.0] * BARS, maxlen=BARS)
        self.anchor: QPoint | None = None       # the mic square's top-left, screen coords
        self._sent_pos = None
        self.mirrored = False
        self.items: dict[str, QRect] = {}
        self.hover = ""
        self._press: QPoint | None = None
        self._grab = QPoint()
        self._dragging = False
        self._phase = 0.0
        self._anim = QTimer(self, interval=33, timeout=self._tick)
        f = QFont(self.font())
        f.setPointSizeF(max(9.5, f.pointSizeF()))
        f.setBold(True)
        self.setFont(f)
        self._relayout()

    # -- state ---------------------------------------------------------------------
    def apply(self, m: dict):
        if "opacity" in m:
            self.opacity = max(0.25, min(1.0, m["opacity"] / 100))
        relayout = False
        if "pos" in m and not self._dragging:
            # compared with the last value sent, not self.anchor, which _relayout clamps
            if m["pos"] != self._sent_pos or self.anchor is None:
                self._sent_pos = m["pos"]
                self.anchor = QPoint(*m["pos"]) if m["pos"] else None
                relayout = True
        if m.get("state", self.state) != self.state or m.get("paused", self.paused) != self.paused:
            self.state, self.paused = m.get("state", self.state), m.get("paused", self.paused)
            if self.state != "recording":
                self.levels.extend([0.0] * BARS)
            relayout = True
        if relayout:
            self._relayout()
        self.seconds = m.get("seconds", self.seconds)
        if self.state == "recording" and not self.paused and "level" in m:
            self.levels.append(float(m["level"]))
        if "visible" in m:
            if m["visible"] and not self.isVisible():
                self._relayout()
                self.show()
            elif not m["visible"] and self.isVisible():
                self.hide()
        running = self.isVisible() and self.state in ("recording", "busy")
        if not running:
            self._anim.stop()
        elif not self._anim.isActive():
            self._anim.start()
        self.update()

    def _tick(self):
        self._phase = (self._phase + 0.033) % 60
        self.update()

    def _text(self) -> str:
        return {"busy": "Transcribing…", "done": "Inserted", "nofield": "No text field"}.get(self.state, "")

    # -- geometry ------------------------------------------------------------------
    def _screen_rect(self) -> QRect:
        scr = QGuiApplication.screenAt(self.anchor) if self.anchor else None
        return (scr or QGuiApplication.primaryScreen()).availableGeometry()

    def _relayout(self):
        fm = QFontMetrics(self.font())
        if self.state == "recording":
            parts = [("timer", fm.horizontalAdvance("00:00") + 10), ("bars", BARS * 5 + 6),
                     ("resume" if self.paused else "pause", BTN), ("retake", BTN), ("discard", BTN)]
        elif self.state == "nofield":
            parts = [("label", fm.horizontalAdvance(self._text()) + 14),
                     ("paste", fm.horizontalAdvance("Paste") + 24), ("dismiss", BTN)]
        elif self._text():
            parts = [("label", fm.horizontalAdvance(self._text()) + 14)]
        else:
            parts = []
        width = H + sum(w for _, w in parts) + (10 if parts else 0)
        area = self._screen_rect()
        a = self.anchor or QPoint(area.center().x() - H // 2, area.bottom() - H - 72)
        a = QPoint(max(area.left(), min(a.x(), area.right() - H)),
                   max(area.top(), min(a.y(), area.bottom() - H)))
        self.anchor = a
        self.mirrored = bool(parts) and a.x() + H // 2 > area.center().x()
        x0 = a.x() - (width - H) if self.mirrored else a.x()
        self.setGeometry(x0, a.y(), width, H)
        pad = (H - MIC) // 2
        self.items = {"mic": QRect(width - H + pad if self.mirrored else pad, pad, MIC, MIC)}
        x = width - H if self.mirrored else H
        for name, w in parts:
            if self.mirrored:
                x -= w
                self.items[name] = QRect(x, 0, w, H)
            else:
                self.items[name] = QRect(x, 0, w, H)
                x += w
        self.update()

    # -- painting ------------------------------------------------------------------
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        idle = self.state == "idle"
        p.setOpacity(self.opacity if idle and self.hover != "mic" else 1.0)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(PANEL)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        self._paint_mic(p, QRectF(self.items["mic"]))
        white = QColor(255, 255, 255)
        for name, rect in self.items.items():
            if name == "timer":
                s = int(self.seconds)
                p.setPen(white if not self.paused else QColor(255, 255, 255, 150))
                p.drawText(rect, Qt.AlignCenter, f"{s // 60}:{s % 60:02d}")
            elif name == "bars":
                self._paint_bars(p, rect)
            elif name == "label":
                p.setPen(white)
                p.drawText(rect, Qt.AlignCenter, self._text())
            elif name in ("pause", "resume", "retake", "discard"):
                self._paint_button(p, name, QRectF(rect))
            elif name == "dismiss":
                self._paint_button(p, "discard", QRectF(rect), hover=self.hover == name)
            elif name == "paste":
                pill = QRectF(rect).adjusted(3, 12, -3, -12)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(GREEN).lighter(125 if self.hover == name else 100))
                p.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
                p.setPen(white)
                p.drawText(pill, Qt.AlignCenter, "Paste")

    def _paint_mic(self, p: QPainter, r: QRectF):
        st = self.state
        col = QColor({"idle": BLUE, "recording": RED, "busy": AMBER, "done": GREEN, "nofield": AMBER}[st])
        if st == "recording" and self.paused:
            col = QColor("#6B7785")
        if self.hover == "mic" and st in ("idle", "recording", "nofield"):
            col = col.lighter(115)
        c = r.center()
        if st == "recording" and not self.paused:     # a halo that follows the voice
            lvl = self.levels[-1] if self.levels else 0.0
            halo = QColor(RED)
            halo.setAlpha(70)
            p.setPen(Qt.NoPen)
            p.setBrush(halo)
            g = 2 + 5 * min(1.0, lvl * 1.6)
            p.drawEllipse(r.adjusted(-g, -g, g, g).intersected(QRectF(self.rect())))
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawEllipse(r)
        white = QColor(255, 255, 255)
        if st == "recording":                          # Stop
            s = r.width() * 0.30
            p.setBrush(white)
            p.drawRoundedRect(QRectF(c.x() - s / 2, c.y() - s / 2, s, s), 3, 3)
        elif st == "busy":                             # spinner
            p.setPen(QPen(white, 3, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            a = int(-self._phase * 360 * 1.2 * 16) % (360 * 16)
            p.drawArc(r.adjusted(12, 12, -12, -12), a, 100 * 16)
        elif st == "done":                             # check
            p.setPen(QPen(white, 3.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            path = QPainterPath(QPointF(c.x() - 8, c.y()))
            path.lineTo(c.x() - 2.5, c.y() + 6)
            path.lineTo(c.x() + 9, c.y() - 6)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        else:
            draw_mic(p, c, r.width() / 46, white)

    def _paint_bars(self, p: QPainter, rect: QRect):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 120 if self.paused else 220))
        x = rect.left() + 3
        cy = rect.center().y()
        for lvl in self.levels:
            h = 3 + 22 * min(1.0, math.sqrt(max(0.0, lvl)) * 1.2)
            p.drawRoundedRect(QRectF(x, cy - h / 2, 3, h), 1.5, 1.5)
            x += 5

    def _paint_button(self, p: QPainter, name: str, r: QRectF, hover: bool | None = None):
        c = r.center()
        if self.hover == name if hover is None else hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 38))
            p.drawEllipse(c, 14, 14)
        white = QColor(255, 255, 255, 235)
        pen = QPen(white, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if name == "pause":
            p.drawLine(QPointF(c.x() - 3.5, c.y() - 6), QPointF(c.x() - 3.5, c.y() + 6))
            p.drawLine(QPointF(c.x() + 3.5, c.y() - 6), QPointF(c.x() + 3.5, c.y() + 6))
        elif name == "resume":
            path = QPainterPath(QPointF(c.x() - 4, c.y() - 6.5))
            path.lineTo(c.x() + 6.5, c.y())
            path.lineTo(c.x() - 4, c.y() + 6.5)
            path.closeSubpath()
            p.setBrush(white)
            p.drawPath(path)
        elif name == "retake":
            box = QRectF(c.x() - 6.5, c.y() - 6.5, 13, 13)
            p.drawArc(box, 100 * 16, 290 * 16)
            tip = QPointF(c.x() - 1, c.y() - 6.5)
            path = QPainterPath(tip + QPointF(-4.5, -3.5))
            path.lineTo(tip)
            path.lineTo(tip + QPointF(-3.5, 4.5))
            p.drawPath(path)
        elif name == "discard":
            p.drawLine(QPointF(c.x() - 5.5, c.y() - 5.5), QPointF(c.x() + 5.5, c.y() + 5.5))
            p.drawLine(QPointF(c.x() + 5.5, c.y() - 5.5), QPointF(c.x() - 5.5, c.y() + 5.5))

    # -- mouse: click a part, or drag the whole thing ----------------------------------
    def _hit(self, pos: QPoint) -> str:
        for name, rect in self.items.items():
            if name in ("mic", "pause", "resume", "retake", "discard", "paste", "dismiss") and rect.contains(pos):
                return name
        return ""

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._press = ev.globalPosition().toPoint()
            self._grab = self._press - self.anchor
            self._dragging = False

    def mouseMoveEvent(self, ev):
        g = ev.globalPosition().toPoint()
        if self._press is not None and (self._dragging or (g - self._press).manhattanLength() > 5):
            self._dragging = True
            self.anchor = g - self._grab
            self._relayout()
            return
        hit = self._hit(ev.position().toPoint())
        if hit != self.hover:
            self.hover = hit
            tip = TIPS["mic"][self.state] if hit == "mic" else TIPS.get(hit, "")
            QToolTip.showText(ev.globalPosition().toPoint(), tip, self) if tip else QToolTip.hideText()
            self.setCursor(Qt.PointingHandCursor if hit else Qt.OpenHandCursor)
            self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.LeftButton or self._press is None:
            return
        self._press = None
        if self._dragging:
            self._dragging = False
            self.moved.emit(self.anchor.x(), self.anchor.y())
            return
        hit = self._hit(ev.position().toPoint())
        if self.state == "nofield" and hit in ("mic", "paste"):
            self.action.emit("paste_last")
        elif self.state == "nofield" and hit == "dismiss":
            self.action.emit("dismiss_no_field")
        elif hit == "mic" and self.state in ("idle", "recording"):
            self.action.emit("toggle")
        elif hit in ("pause", "resume", "retake", "discard"):
            self.action.emit("pause" if hit == "resume" else hit)

    def leaveEvent(self, _ev):
        self.hover = ""
        self.update()


def draw_mic(p: QPainter, c: QPointF, k: float, color: QColor):
    """A microphone glyph centred on c, k = scale (1.0 for a 46 px circle)."""
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(QRectF(c.x() - 4.5 * k, c.y() - 12 * k, 9 * k, 15 * k), 4.5 * k, 4.5 * k)
    p.setPen(QPen(color, 2.2 * k, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(c.x() - 8 * k, c.y() - 7 * k, 16 * k, 14 * k), 180 * 16, 180 * 16)
    p.drawLine(QPointF(c.x(), c.y() + 7 * k), QPointF(c.x(), c.y() + 11 * k))
    p.drawLine(QPointF(c.x() - 4.5 * k, c.y() + 11.5 * k), QPointF(c.x() + 4.5 * k, c.y() + 11.5 * k))


class OverlayHost(QObject):
    """What the Controller talks to: the same calls whether the overlay lives in this
    process or in an XWayland child."""
    action = Signal(str)
    moved = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind, self.reason = mode()
        self._w: Overlay | None = None
        self._proc: QProcess | None = None
        self._buf = b""
        self._restarts = 0
        self._last: dict = {}

    @property
    def available(self) -> bool:
        return bool(self.kind)

    def send(self, msg: dict):
        """Changed keys only reach the child; the in-process widget gets them directly."""
        if not self.kind or (not msg.get("visible") and not self._last.get("visible")
                             and self._w is None and self._proc is None):
            self._last.update(msg)
            return
        if self.kind == "inproc":
            if self._w is None:
                self._w = Overlay()
                self._w.action.connect(self.action)
                self._w.moved.connect(self.moved)
                self._w.apply(self._last)
            self._w.apply(msg)
        else:
            diff = {k: v for k, v in msg.items() if self._last.get(k) != v}
            if self._ensure_child() and diff:
                self._proc.write((json.dumps(diff) + "\n").encode())
        self._last.update(msg)

    def _ensure_child(self) -> bool:
        if self._proc and self._proc.state() != QProcess.NotRunning:
            return True
        if self._restarts > 3:
            return False
        self._restarts += 1
        env = QProcessEnvironment.systemEnvironment()
        env.insert("QT_QPA_PLATFORM", "xcb")
        env.insert("PYTHONPATH", os.pathsep.join(p for p in sys.path if p))
        proc = QProcess(self)
        proc.setProcessEnvironment(env)
        proc.setProcessChannelMode(QProcess.ForwardedErrorChannel)
        proc.readyReadStandardOutput.connect(self._read)
        proc.start(sys.executable, ["-m", "hebrish.ui.overlay"])
        if not proc.waitForStarted(3000):
            return False
        self._proc = proc
        proc.write((json.dumps(self._last) + "\n").encode())    # replay the full state
        return True

    def _read(self):
        self._buf += bytes(self._proc.readAllStandardOutput())
        *lines, self._buf = self._buf.split(b"\n")
        for line in lines:
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if "action" in m:
                self.action.emit(m["action"])
            if m.get("pos"):
                self.moved.emit(*m["pos"])

    def close(self):
        if self._proc:
            self._proc.closeWriteChannel()          # the child quits on EOF
            if not self._proc.waitForFinished(1000):
                self._proc.kill()
        if self._w:
            self._w.close()


def _child():
    """`python -m hebrish.ui.overlay`, started by OverlayHost with QT_QPA_PLATFORM=xcb.
    POSIX only: QSocketNotifier can't watch a pipe on Windows (the CI test timed out there,
    2026-10-20), and Windows never needs the child."""
    from PySide6.QtCore import QSocketNotifier
    app = QApplication([sys.argv[0]])
    app.setApplicationName("hebrish-overlay")
    app.setQuitOnLastWindowClosed(False)
    w = Overlay()

    def out(m):
        sys.stdout.write(json.dumps(m) + "\n")
        sys.stdout.flush()
    w.action.connect(lambda a: out({"action": a}))
    w.moved.connect(lambda x, y: out({"pos": [x, y]}))
    fd, buf = sys.stdin.fileno(), [b""]

    def readable():
        chunk = os.read(fd, 65536)
        if not chunk:
            app.quit()
            return
        *lines, buf[0] = (buf[0] + chunk).split(b"\n")
        for line in lines:
            try:
                w.apply(json.loads(line))
            except ValueError:
                pass
    note = QSocketNotifier(fd, QSocketNotifier.Read)
    note.activated.connect(readable)
    sys.exit(app.exec())


if __name__ == "__main__":
    _child()
