"""The floating overlay: layout per state, clicks -> actions, and the XWayland child's
JSON-lines protocol. Off-screen only; skipped where PySide6 isn't installed (Linux CI)."""

import json
import os
import subprocess
import sys

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hebrish.ui.overlay import Overlay  # noqa: E402

app = QApplication.instance() or QApplication([])


def mouse(w, kind, pos: QPoint):
    """QtTest isn't in Ubuntu's PySide6 packages, so events are built by hand."""
    t = {"press": QEvent.MouseButtonPress, "move": QEvent.MouseMove,
         "release": QEvent.MouseButtonRelease}[kind]
    held = Qt.NoButton if kind == "release" else Qt.LeftButton
    ev = QMouseEvent(t, QPointF(pos), QPointF(w.mapToGlobal(pos)),
                     Qt.NoButton if kind == "move" else Qt.LeftButton, held, Qt.NoModifier)
    QApplication.sendEvent(w, ev)


def click(w, pos):
    mouse(w, "press", pos)
    mouse(w, "release", pos)


def test_parts_per_state():
    w = Overlay()
    w.apply({"state": "idle"})
    assert set(w.items) == {"mic"} and w.width() == w.height()
    w.apply({"state": "recording"})
    assert list(w.items) == ["mic", "timer", "bars", "pause", "retake", "discard"]
    w.apply({"paused": True})
    assert "resume" in w.items and "pause" not in w.items
    w.apply({"state": "busy", "paused": False})
    assert set(w.items) == {"mic", "label"}


def test_bar_opens_towards_the_middle():
    w = Overlay()
    area = w._screen_rect()
    w.apply({"state": "recording", "pos": [area.right() - 100, area.top() + 50]})
    assert w.mirrored and w.items["mic"].right() > w.items["discard"].right()
    assert w.geometry().right() <= area.right()
    w.apply({"pos": [area.left() + 10, area.top() + 50]})
    assert not w.mirrored and w.items["mic"].left() < w.items["timer"].left()


def test_clicks_become_actions():
    w = Overlay()
    got = []
    w.action.connect(got.append)
    w.apply({"state": "recording", "pos": [10, 10]})
    for part in ("mic", "pause", "retake", "discard"):
        click(w, w.items[part].center())
    w.apply({"paused": True})
    click(w, w.items["resume"].center())
    assert got == ["toggle", "pause", "retake", "discard", "pause"]


def test_drag_moves_and_reports_position():
    w = Overlay()
    moved = []
    w.moved.connect(lambda x, y: moved.append((x, y)))
    w.apply({"state": "idle", "pos": [200, 200]})
    c = w.items["mic"].center()
    start = w.anchor
    mouse(w, "press", c)
    mouse(w, "move", c + QPoint(40, 30))
    mouse(w, "release", c + QPoint(40, 30))
    assert moved == [(start.x() + 40, start.y() + 30)]


@pytest.mark.skipif(sys.platform == "win32", reason="the child exists only on Linux Wayland; "
                    "QSocketNotifier can't watch a stdin pipe on Windows")
def test_child_process_protocol():
    """What OverlayHost runs on Wayland (there with QT_QPA_PLATFORM=xcb)."""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
               PYTHONPATH=os.pathsep.join(p for p in sys.path if p))
    p = subprocess.Popen([sys.executable, "-m", "hebrish.ui.overlay"], env=env,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    msgs = [{"visible": True, "state": "recording", "seconds": 3, "level": 0.4, "pos": [50, 50]},
            {"paused": True}, {"state": "done"}, {"visible": False}]
    out, err = p.communicate(("\n".join(json.dumps(m) for m in msgs) + "\nnot json\n").encode(),
                             timeout=20)
    assert p.returncode == 0, err.decode()           # EOF on stdin = quit, bad lines ignored
