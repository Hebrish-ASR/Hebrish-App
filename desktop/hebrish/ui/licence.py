"""How Hebrish is licensed: one wording for About and the one-time notice (Daniel, 2026-11-05).

Not an end user licence agreement: the app is MIT, and the limits are on the models, under
hebrish.app/terms. So this tells people the terms once, on first show of the window, and stays in
About. Keep it in step with the site's /licensing and Android's licence_notice_body.
"""

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ..config import STATE_PATH, load_json, save_json

DATA = Path(__file__).resolve().parent.parent / "data"
SEEN_FLAG = "licence_notice_seen"
ACCESS = "access@hebrish.app"
LICENSING = "https://hebrish.app/licensing"
TERMS = "https://hebrish.app/terms"

LICENCE_HTML = (
    f"The models are CC BY-NC 4.0 plus the <a href='{TERMS}'>Hebrish terms of use</a>: free for personal "
    "use, research, education and small non-profits, with credit.<br><br>"
    "Commercial use needs a paid licence, and so do health funds and public bodies. Using Hebrish in a "
    f"commercial project, or not sure? Check first: <a href='mailto:{ACCESS}'>{ACCESS}</a>.<br><br>"
    f"The app itself is open source under MIT. Details: <a href='{LICENSING}'>hebrish.app/licensing</a>.")


def cc_icons() -> QHBoxLayout:
    """The Creative Commons icons for the models' licence: CC, BY, NC."""
    row = QHBoxLayout()
    row.setSpacing(6)
    for name, tip in (("cc", "Creative Commons"), ("by", "Attribution"), ("nc", "NonCommercial")):
        label = QLabel()
        label.setPixmap(QPixmap(str(DATA / "licence" / f"{name}.png")).scaled(
            32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        label.setToolTip(tip)
        row.addWidget(label)
    row.addStretch(1)
    return row


class LicenceNotice(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("How Hebrish is licensed")
        self.setMinimumWidth(460)
        lay = QHBoxLayout(self)
        lay.setSpacing(18)
        corn = QLabel()
        corn.setPixmap(QPixmap(str(DATA / "corn" / "corn.png")).scaledToHeight(150, Qt.SmoothTransformation))
        corn.setAlignment(Qt.AlignTop)
        lay.addWidget(corn)
        col = QVBoxLayout()
        col.addLayout(cc_icons())
        text = QLabel(LICENCE_HTML)
        text.setWordWrap(True)
        text.setOpenExternalLinks(True)
        col.addWidget(text)
        ok = QPushButton("Got it")
        ok.clicked.connect(self.accept)
        col.addWidget(ok, alignment=Qt.AlignRight)
        lay.addLayout(col, 1)


def mark_seen():
    state = load_json(STATE_PATH)
    state[SEEN_FLAG] = True
    save_json(STATE_PATH, state)


class NoticeOnFirstShow(QObject):
    """Shows the notice once, the first time the window appears, so never over the splash or
    on a --hidden start."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        win.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if obj is self.win and ev.type() == QEvent.Show:
            self.win.removeEventFilter(self)
            QTimer.singleShot(400, self.show)
        return False

    def show(self):
        mark_seen()
        LicenceNotice(self.win).exec()


def install(win):
    if not load_json(STATE_PATH).get(SEEN_FLAG):
        NoticeOnFirstShow(win)
