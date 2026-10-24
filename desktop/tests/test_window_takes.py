"""1.000: takes in the Dictate tab's text box are separated by one blank line."""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPlainTextEdit  # noqa: E402

from hebrish.ui.window import MainWindow  # noqa: E402

app = QApplication.instance() or QApplication([])


class Box:
    """Just enough of the window for new_take / _append_piece."""
    new_take = MainWindow.new_take
    _append_piece = MainWindow._append_piece
    _take_break = False

    def __init__(self):
        self.text = QPlainTextEdit()


def test_blank_line_between_takes():
    w = Box()
    w.new_take(False)
    w._append_piece("First thought.")
    w._append_piece("More of it.")
    w.new_take(False)
    w._append_piece("Second thought. ")
    w.new_take(False)
    w._append_piece(" Third.")
    assert w.text.toPlainText() == "First thought. More of it.\n\nSecond thought.\n\nThird."


def test_clear_each_take_still_clears():
    w = Box()
    w.new_take(True)
    w._append_piece("One.")
    w.new_take(True)
    w._append_piece("Two.")
    assert w.text.toPlainText() == "Two."
