"""The download bar glides to a value and starts from empty after being hidden."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from hebrish.ui.glidebar import GLIDE_MS, GlideBar


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def settle(_app, _bar, ms=GLIDE_MS + 150):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_glides_to_the_value_not_past_it(app):
    bar = GlideBar()
    bar.show()
    bar.set_fraction(0.4)
    assert bar.shown < 0.4, "it eases there rather than jumping"
    settle(app, bar)
    assert bar.shown == pytest.approx(0.4)
    bar.set_fraction(1.7)
    settle(app, bar)
    assert bar.shown == pytest.approx(1.0)


def test_hidden_bar_starts_again_from_empty(app):
    bar = GlideBar()
    bar.show()
    bar.set_fraction(0.8)
    settle(app, bar)
    bar.hide()
    assert bar.shown == 0.0
