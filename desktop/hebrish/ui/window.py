"""Main window: header, then Dictate / File / [History] / Dictionary / Models / Settings / About tabs.
History is there only while "Keep a history" is on (on by default again since 0.7.0, now
every transcript in a searchable SQLite file: hebrish.history)."""

import os
import time

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTime, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
                               QAbstractItemView, QHeaderView, QProgressBar, QPushButton, QScrollArea,
                               QSlider, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QTimeEdit,
                               QToolButton, QVBoxLayout, QWidget)

from .. import __version__, audio, autostart, dictionary, model_store
from ..config import APP_NAME, CONFIG_PATH, MODELS_DIR, STATE_PATH, TAGLINE, load_json, threads
from ..hotkey import ACTIONS, SLOTS, describe, pretty
from ..inserter import copy_to_clipboard, parse_chord
from . import about
from .app import ICONS, icon
from .meter import LevelMeter, verdict
from .style import BLUE, BRAND_GREEN

OVERLAY = [("off", "Off"), ("active", "While dictating"), ("always", "Always (a mic button)")]
# Insert-as-you-go presets (0.7.1: Fast 3, Normal 5, Relaxed 8 s; 0.7.0 had 5/7/10).
# Any other value is Custom; -1 is the Custom entry's own data.
LIVE = [(0, "Off: everything when you stop"), (3, "Fast: every ~3 seconds"),
        (5, "Normal: every ~5 seconds"), (8, "Relaxed: every ~8 seconds"), (-1, "Custom…")]
STREAM = [("phrase", "A phrase at a time"),
          ("sentence", "A sentence at a time"), ("word", "Every word")]
# Outputs (1.000): config switches, any combination; at least one stays on.
OUTPUT = [("out_cursor", "At the cursor"), ("out_clipboard", "Clipboard"), ("out_window", "This window")]
OUTPUT_TIPS = {"out_cursor": "Paste each piece where your cursor is, as you talk",
               "out_clipboard": "Put the whole take on the clipboard when it ends",
               "out_window": "Show takes in the text box above, a blank line between them"}
PASTE_CHORDS = [("ctrl+v", "Paste with Ctrl+V"), ("ctrl+shift+v", "Paste with Ctrl+Shift+V (terminals)")]
FEEDBACK = [("beeps", "Beeps (start and stop)"), ("voice", "Voice (“Recording”, “Paused”, “Transcribing”…)"),
            ("off", "Off")]
# Saved silently, so no toast: moving the overlay
NO_TOAST = {"overlay_pos"}


def card(title: str = "") -> tuple[QFrame, QVBoxLayout]:
    f = QFrame(objectName="card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 12, 16, 14)
    lay.setSpacing(8)
    if title:
        lay.addWidget(QLabel(title, objectName="cardTitle"))
    return f, lay


def muted(text="") -> QLabel:
    lbl = QLabel(text, objectName="muted")
    lbl.setWordWrap(True)
    return lbl


def dots(n: int, colour: str) -> str:
    n = max(0, min(5, int(n or 0)))
    return f"<span style='color:{colour}'>{'●' * n}</span><span style='color:#bbb'>{'●' * (5 - n)}</span>"


def tiers_html(m) -> str:
    """The speed/accuracy gradient as two five-dot meters (estimates, catalogue `tiers`)."""
    return (f"Speed {dots(m.speed, '#2e7dd1')} &nbsp; Accuracy {dots(m.accuracy, BRAND_GREEN)}"
            " <small style='color:gray'>(estimates)</small>")


def ago(ts: float) -> str:
    d = time.time() - ts
    if d < 60:
        return "just now"
    if d < 3600:
        return f"{int(d // 60)} min ago"
    if d < 86400:
        return time.strftime("%H:%M", time.localtime(ts))
    return time.strftime("%d %b %H:%M", time.localtime(ts))


def human_size(n: float) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024


def stat_tile(title: str) -> tuple[QFrame, QLabel, QLabel]:
    """A small card: a big number (words) and a muted line under it (dictations, time)."""
    box, b = card(title)
    big = QLabel("0", objectName="statBig")
    small = muted()
    b.addWidget(big)
    b.addWidget(small)
    return box, big, small


HISTORY_PAGE = 100      # rows shown at a time in the History tab; "Show more" adds another page
CHANGELOG_URL = "https://hebrish.app/changelog"


class MainWindow(QMainWindow):
    def __init__(self, ctl):
        super().__init__()
        self.ctl, self.cfg = ctl, ctl.cfg
        self.quitting = False
        self.setWindowTitle(APP_NAME)
        self.resize(600, 720)

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._header())
        outer.addWidget(self._app_update_bar())

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.pages = {}
        self.pages["dictate"] = self._dictate_page()
        from .transcribe import TranscribePage
        self.transcribe = self.pages["file"] = TranscribePage(ctl, card, muted)
        self.pages["history"] = self._history_page()
        self.pages["dictionary"] = self._dictionary_page()
        self.pages["model"] = self._scroll(self._model_page())
        self.pages["settings"] = self._scroll(self._settings_page())
        self.pages["settings"].setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)   # labels wrap, never scroll sideways
        from .diagnostics import DiagnosticsPage
        self.pages["diagnostics"] = DiagnosticsPage(ctl, card, muted)
        self.pages["about"] = self._about_page()
        for key, label in (("dictate", "Dictate"), ("file", "File"), ("history", "History"),
                           ("dictionary", "Dictionary"), ("model", "Models"), ("settings", "Settings"),
                           ("diagnostics", "Diagnostics"), ("about", "About")):
            self.tabs.addTab(self.pages[key], label)
        self.tabs.setTabVisible(self.tabs.indexOf(self.pages["history"]), self.cfg["keep_history"])
        self.ctl.sig.piece.connect(self._append_piece)
        self._meter_timer = QTimer(self, interval=60, timeout=self._update_meter)
        self._meter_timer.start()
        outer.addWidget(self.tabs, 1)

        # Footer: status on the left, the app version always visible on the right (0.6.3,
        # Daniel 2026-10-21: "more prominently displayed at the bottom"). It links to the changelog.
        footer = QWidget(objectName="footer")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 4, 12, 8)
        self.status_label = muted()
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        fl.addWidget(self.status_label, 1)
        self.version_label = QLabel(f'<a href="{CHANGELOG_URL}" style="color:{BLUE}; text-decoration:none">'
                                    f'{APP_NAME} {__version__}</a>',
                                    objectName="version")
        self.version_label.setOpenExternalLinks(True)
        self.version_label.setToolTip("What changed in this version")
        fl.addWidget(self.version_label, 0, Qt.AlignRight | Qt.AlignVCenter)
        outer.addWidget(footer)
        self.setCentralWidget(root)

        self._pulse = QTimer(self, interval=550, timeout=self._do_pulse)
        self.update_state()
        self.show_history()

        # Settings apply as they change; this says so.
        self.toast_label = QLabel("Settings saved", root, objectName="toast")
        self.toast_label.setAlignment(Qt.AlignCenter)
        self.toast_label.hide()
        self._toast_timer = QTimer(self, singleShot=True, interval=1600, timeout=self.toast_label.hide)
        self.cfg.on_set = lambda key: key not in NO_TOAST and self.toast()

    # -- frame ---------------------------------------------------------------------
    def _header(self):
        h = QWidget(objectName="header")
        h.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(h)
        lay.setContentsMargins(18, 14, 18, 14)
        logo = QLabel()
        logo.setPixmap(icon("hebrish").pixmap(48, 48))
        lay.addWidget(logo)
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(QLabel(APP_NAME, objectName="title"))
        text.addWidget(QLabel(TAGLINE, objectName="tagline"))
        lay.addLayout(text, 1)
        return h

    def _app_update_bar(self):
        """A new Hebrish app (0.6.2, app_update): a strip under the header with one action and
        "Not now". Unlike banner(), it never raises the window or switches tab."""
        bar = QFrame(objectName="updateBar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 8, 12, 8)
        self.app_update_label = QLabel()
        self.app_update_label.setWordWrap(True)
        self.app_update_label.setTextFormat(Qt.RichText)
        lay.addWidget(self.app_update_label, 1)
        self.app_update_btn = QPushButton(objectName="primary")
        self.app_update_btn.clicked.connect(self.ctl.app_update_action)
        later = QPushButton("Not now")
        later.clicked.connect(self.ctl.dismiss_app_update)
        lay.addWidget(self.app_update_btn, 0, Qt.AlignVCenter)
        lay.addWidget(later, 0, Qt.AlignVCenter)
        bar.hide()
        self.app_update_frame = bar
        return bar

    def show_app_update(self, rel, method, busy=False, error=""):
        head = f"<b>{APP_NAME} {rel.version} is available</b> (you have {__version__})."
        if method == "apt":
            text = head + " It installs from the Hebrish repository and asks for your password."
            btn = "Updating…" if busy else ("Try again" if error else "Update now")
        elif method == "deb-manual":
            text = (head + " Get the new .deb from hebrish.app. Installing it also adds the Hebrish "
                    "repository, so later updates install from here.")
            btn = "Download page"
        elif method == "windows":
            text = head + " Download the new zip from hebrish.app and replace this folder with it."
            btn = "Download page"
        else:
            text = head + " You're running from source: pull the repository to update."
            btn = ""
        if error:
            text += f"<br><span style='color:#a12020'>{error}</span>"
        self.app_update_label.setText(text)
        self.app_update_btn.setText(btn)
        self.app_update_btn.setVisible(bool(btn))
        self.app_update_btn.setEnabled(not busy)
        self.app_update_frame.show()

    def hide_app_update(self):
        self.app_update_frame.hide()

    def app_update_status(self, text):
        self.app_status_label.setText(text)
        self.btn_restart.setVisible(bool(self.ctl.app_installed))

    def ask_restart(self, msg) -> bool:
        return QMessageBox.question(
            self, f"{APP_NAME} updated", f"{msg}\n\nRestart {APP_NAME} now to use the new version?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes

    @staticmethod
    def _scroll(w):
        s = QScrollArea()
        s.setWidgetResizable(True)
        s.setFrameShape(QFrame.NoFrame)
        s.setWidget(w)
        return s

    def present_tab(self, name: str = ""):
        if name:
            self.tabs.setCurrentWidget(self.pages[name])
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, ev):
        if not self.quitting:            # close = back to the tray
            ev.ignore()
            self.hide()

    # -- dictate -------------------------------------------------------------------
    def _dictate_page(self):
        """Record into the text box (and wherever Output sends it), with the mic, voice
        detection and a level meter on the same screen. 0.5.0 replaced the history list here."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 14, 16, 8)
        lay.setSpacing(10)

        self.banner_label = QLabel(objectName="banner")
        self.banner_label.setWordWrap(True)
        self.banner_label.hide()
        lay.addWidget(self.banner_label)

        top = QHBoxLayout()
        top.setSpacing(16)
        col = QVBoxLayout()
        col.setSpacing(4)
        self.rec = QPushButton("Talk", objectName="record")
        self.rec.setFixedSize(104, 104)
        self.rec.setCursor(Qt.PointingHandCursor)
        self.rec.clicked.connect(self.ctl.toggle)
        col.addWidget(self.rec, 0, Qt.AlignHCenter)
        self.state_label = QLabel(alignment=Qt.AlignHCenter)
        self.state_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        col.addWidget(self.state_label)
        row = QHBoxLayout()
        self.btn_pause = QPushButton("Pause")
        self.btn_pause.clicked.connect(self.ctl.pause)
        self.btn_discard = QPushButton("Discard")
        self.btn_discard.clicked.connect(lambda: self.ctl.cancel())
        row.addWidget(self.btn_pause)
        row.addWidget(self.btn_discard)
        col.addLayout(row)
        col.addStretch(1)
        top.addLayout(col)

        box, b = card("Microphone")
        row = QHBoxLayout()
        self.mic = QComboBox()
        self.mic.setMinimumWidth(120)
        self.mic.setToolTip("The microphone in use. Changing it applies from the next take.")
        row.addWidget(self.mic, 1)
        refresh = QToolButton()
        refresh.setIcon(QIcon.fromTheme("view-refresh"))
        refresh.setText("↻")
        refresh.setToolTip("Rescan microphones")
        refresh.clicked.connect(self._fill_mics)
        row.addWidget(refresh)
        b.addLayout(row)
        self.mic_in_use = muted()
        b.addWidget(self.mic_in_use)
        self._fill_mics()
        self.mic.currentIndexChanged.connect(self._on_mic)
        self.meter = LevelMeter()
        b.addWidget(self.meter)
        row = QHBoxLayout()
        self.meter_label = QLabel()
        self.meter_label.setStyleSheet("font-size: 12px;")
        row.addWidget(self.meter_label, 1)
        self.btn_test = QPushButton("Test mic")
        self.btn_test.setCheckable(True)
        self.btn_test.setToolTip("Watch the level without recording anything")
        self.btn_test.toggled.connect(self._on_test)
        row.addWidget(self.btn_test)
        b.addLayout(row)
        b.addWidget(self._check("vad", "Voice detection: skip silent takes, trim long pauses"))
        top.addWidget(box, 1)
        lay.addLayout(top)

        self.hint_label = muted()
        lay.addWidget(self.hint_label)

        box, b = card()
        head = QHBoxLayout()
        head.addWidget(QLabel("Text", objectName="cardTitle"))
        head.addStretch(1)
        self.words = muted()
        head.addWidget(self.words)
        b.addLayout(head)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("Takes appear here when Output has \"This window\" on, each "
                                     "after a blank line, and you can edit them. Every take is in "
                                     "History either way.")
        # 16 px since 1.000 (was 14; Daniel, 2026-10-24: "the size of the text in the window just a bit" larger)
        self.text.setStyleSheet("font-size: 16px;")
        b.addWidget(self.text, 1)
        row = QHBoxLayout()
        self.btn_copy_text = QPushButton(QIcon.fromTheme("edit-copy"), "Copy")
        self.btn_copy_text.clicked.connect(lambda: (copy_to_clipboard(self.text.toPlainText()),
                                                    self.status("Text copied.")))
        self.btn_save_text = QPushButton(QIcon.fromTheme("document-save"), "Save…")
        self.btn_save_text.clicked.connect(self._save_text)
        self.btn_clear_text = QPushButton(QIcon.fromTheme("edit-clear"), "Clear")
        self.btn_clear_text.clicked.connect(self.text.clear)
        for w in (self.btn_copy_text, self.btn_save_text, self.btn_clear_text):
            row.addWidget(w)
        row.addStretch(1)
        row.addWidget(QLabel("Output"))
        self.output_buttons = {}
        for key, label in OUTPUT:
            btn = QPushButton(label, checkable=True, checked=bool(self.cfg[key]))
            btn.setToolTip(OUTPUT_TIPS[key])
            btn.setStyleSheet(f"QPushButton:checked {{ background: {BRAND_GREEN}; color: white; "
                              f"border-color: {BRAND_GREEN}; }}")
            btn.toggled.connect(lambda on, k=key: self._on_output(k, on))
            self.output_buttons[key] = btn
            row.addWidget(btn)
        b.addLayout(row)
        self.text.textChanged.connect(self._count)
        lay.addWidget(box, 1)
        self._count()
        return page

    def _fill_mics(self):
        cur = self.cfg["audio_device"]
        self.mic.blockSignals(True)
        self.mic.clear()
        self.mic.addItem("System default", "")
        for name in audio.input_devices():
            self.mic.addItem(name, name)
        if cur and self.mic.findData(cur) < 0:
            self.mic.addItem(f"{cur} (not found)", cur)
        self.mic.setCurrentIndex(max(0, self.mic.findData(cur)))
        self.mic.blockSignals(False)
        self._show_mic()

    def _show_mic(self):
        name = self.cfg["audio_device"]
        if not name:
            real = audio.default_input_name()
            name = f"{real} (system default)" if real else "System default"
        self.mic_in_use.setText(f"In use: {name}")

    def _on_mic(self, _i):
        self.cfg.set("audio_device", self.mic.currentData())
        self._show_mic()
        if self.ctl.monitor.active:                 # re-open the test on the new mic
            self.ctl.stop_monitor()
            self._on_test(True)

    def _on_test(self, on):
        if on:
            try:
                self.ctl.start_monitor()
            except Exception as e:
                self.btn_test.setChecked(False)
                self.banner(f"Couldn't open the microphone: {e}")
        else:
            self.ctl.stop_monitor()

    def _update_meter(self):
        if not self.isVisible():
            return
        src = self.ctl.meter_source
        self.meter.set_source(src)
        if src is None:
            self.meter_label.setText("<span style='color:gray'>Level: talk, or press Test mic</span>")
        elif src.paused:
            self.meter_label.setText("Paused")
        else:
            text, col = verdict(self.meter.rms_db, self.meter.clipping)
            self.meter_label.setText(f"<b style='color:{col}'>{text}</b> &nbsp;"
                                     f"<span style='color:gray'>{self.meter.rms_db:.0f} dB · peak "
                                     f"{self.meter.peak_db:.0f} dB</span>")

    def new_take(self, clear: bool):
        """A take is starting. With `clear_each_take` the text box starts empty (0.7.0, Daniel
        2026-10-22: it used to collect every take into one long blob); otherwise (the default
        since 1.000) the take starts after a blank line, so takes read as separate blocks
        (Daniel, 2026-10-24: "natural segments between the transcription"). Text is in History."""
        if clear:
            self.text.clear()
        self._take_break = True

    def _on_output(self, key, on):
        """An Output button. The last one on can't be turned off: with none, a take would go
        only to History, which looks like nothing happened."""
        if not on and not any(self.cfg[k] for k, _ in OUTPUT if k != key):
            self.output_buttons[key].blockSignals(True)
            self.output_buttons[key].setChecked(True)
            self.output_buttons[key].blockSignals(False)
            self.status("At least one output stays on.")
            return
        self.cfg.set(key, on)
        self.update_state()

    _take_break = False

    def _append_piece(self, text):
        cur = self.text.toPlainText()
        if self._take_break:
            # A take's first piece: a blank line after whatever earlier takes left in the box.
            self._take_break = False
            # Exactly one blank line, whatever trailing spaces or breaks the box ends with.
            body = cur.rstrip()
            self.text.setPlainText(body + "\n\n" + text.lstrip() if body else text.lstrip())
            self.text.moveCursor(self.text.textCursor().MoveOperation.End)
            self.text.ensureCursorVisible()
            return
        # streaming pieces and held full stops (0.7.1) carry their own leading space or mark
        sep = "" if not cur or cur.endswith((" ", "\n")) or text.startswith((" ", ".", ",", ";", ":", "?", "!")) else " "
        self.text.moveCursor(self.text.textCursor().MoveOperation.End)
        self.text.insertPlainText(sep + text)
        self.text.ensureCursorVisible()

    def _count(self):
        t = self.text.toPlainText()
        n = len(t.split())
        self.words.setText(f"{n} word{'s' if n != 1 else ''}" if n else "")
        for w in (self.btn_copy_text, self.btn_save_text, self.btn_clear_text):
            w.setEnabled(bool(t.strip()))

    def _save_text(self):
        name = time.strftime("dictation-%Y-%m-%d-%H%M.txt")
        path, _ = QFileDialog.getSaveFileName(self, "Save text", str(Path.home() / name),
                                              "Text (*.txt);;Markdown (*.md);;All files (*)")
        if path:
            Path(path).write_text(self.text.toPlainText() + "\n", encoding="utf-8")
            self.status(f"Saved {path}")

    # -- history -----------------------------------------------------------------------
    def _history_page(self):
        """Search box, word counts (today / 7 days / all time), the transcripts, and where they
        are stored. Everything comes from ctl.history (hebrish.history, SQLite + FTS5)."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 14, 16, 8)
        lay.setSpacing(10)

        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.stat_tiles = {}
        for key, title in (("today", "Today"), ("week", "Last 7 days"), ("all", "All time")):
            box, big, small = stat_tile(title)
            self.stat_tiles[key] = (big, small)
            tiles.addWidget(box, 1)
        lay.addLayout(tiles)

        box, blay = card()
        head = QHBoxLayout()
        self.hist_search = QLineEdit()
        self.hist_search.setPlaceholderText("Search your dictations (all words, beginnings match: “shak” finds Shakshuka)")
        self.hist_search.setClearButtonEnabled(True)
        self._search_timer = QTimer(self, singleShot=True, interval=250, timeout=self.show_history)
        self.hist_search.textChanged.connect(lambda _t: self._search_timer.start())
        head.addWidget(self.hist_search, 1)
        self.btn_clear = QPushButton(QIcon.fromTheme("edit-clear-history"), "Clear history")
        self.btn_clear.clicked.connect(self._confirm_clear)
        head.addWidget(self.btn_clear)
        blay.addLayout(head)
        self.hist_count = muted()
        blay.addWidget(self.hist_count)
        self.hist_box = QVBoxLayout()
        self.hist_box.setSpacing(6)
        inner = QWidget()
        inner.setLayout(self.hist_box)
        sc = self._scroll(inner)
        sc.setMinimumHeight(180)
        blay.addWidget(sc, 1)
        lay.addWidget(box, 1)

        box, b = card("Stored on this computer")
        self.hist_where = muted()
        self.hist_where.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.hist_where.setWordWrap(True)
        b.addWidget(self.hist_where)
        row = QHBoxLayout()
        opn = QPushButton(QIcon.fromTheme("folder-open"), "Open folder")
        opn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.ctl.history.path.parent))))
        exp = QPushButton(QIcon.fromTheme("document-export"), "Export…")
        exp.setToolTip("Every transcript as JSON Lines, oldest first")
        exp.clicked.connect(self._export_history)
        row.addWidget(opn)
        row.addWidget(exp)
        row.addStretch(1)
        b.addLayout(row)
        lay.addWidget(box)
        self._hist_limit = HISTORY_PAGE
        return page

    # -- personal dictionary (0.8.0) ---------------------------------------------------------
    def _dictionary_page(self):
        """The personal dictionary (hebrish.dictionary; rules in ../shared/personal-dictionary.md):
        a table of entries, a row to add one, Remove. Every change is saved at once."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 14, 16, 8)
        lay.setSpacing(10)

        box, b = card("Add a word")
        b.addWidget(muted("Words you want written your way: names, brands, Hebrew terms. Hebrish corrects "
                          "the model's text after it is written, from the next take; it can't teach the "
                          "model new sounds. “Heard as” is what the model writes instead (optional; "
                          "separate several with commas)."))
        row = QHBoxLayout()
        self.dict_word = QLineEdit()
        self.dict_word.setPlaceholderText("Word, e.g. Hebrish")
        self.dict_heard = QLineEdit()
        self.dict_heard.setPlaceholderText("Heard as, e.g. hebrew ish")
        add = QPushButton(QIcon.fromTheme("list-add"), "Add")
        add.clicked.connect(self._dict_add)
        for e in (self.dict_word, self.dict_heard):
            e.returnPressed.connect(self._dict_add)
        row.addWidget(self.dict_word, 1)
        row.addWidget(self.dict_heard, 1)
        row.addWidget(add)
        b.addLayout(row)
        lay.addWidget(box)

        box, b = card("Your words")
        self.dict_table = t = QTableWidget(0, 2)
        t.setHorizontalHeaderLabels(["Word", "Heard as"])
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.verticalHeader().hide()
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        b.addWidget(t, 1)
        row = QHBoxLayout()
        self.dict_count = muted()
        row.addWidget(self.dict_count, 1)
        rm = QPushButton(QIcon.fromTheme("list-remove"), "Remove")
        rm.clicked.connect(self._dict_remove)
        row.addWidget(rm)
        b.addLayout(row)
        lay.addWidget(box, 1)
        self._dict_show()
        return page

    def _dict_show(self):
        self.dict_entries = dictionary.load()
        t = self.dict_table
        t.setRowCount(len(self.dict_entries))
        for i, e in enumerate(self.dict_entries):
            t.setItem(i, 0, QTableWidgetItem(e["word"]))
            t.setItem(i, 1, QTableWidgetItem(", ".join(e["heard"])))
        n = len(self.dict_entries)
        self.dict_count.setText(f"{n} word{'s' if n != 1 else ''} · {dictionary.PATH}" if n
                                else "No words yet.")

    def _dict_add(self):
        word = self.dict_word.text().strip()
        if not word:
            return
        heard = [h.strip() for h in self.dict_heard.text().split(",") if h.strip()]
        entries = [e for e in self.dict_entries if e["word"] != word]   # adding a word again replaces it
        entries.append({"word": word, "heard": heard})
        dictionary.save(entries)
        self.dict_word.clear()
        self.dict_heard.clear()
        self._dict_show()
        self.toast("Dictionary saved")

    def _dict_remove(self):
        rows = {i.row() for i in self.dict_table.selectedIndexes()}
        if rows:
            dictionary.save([e for i, e in enumerate(self.dict_entries) if i not in rows])
            self._dict_show()
            self.toast("Dictionary saved")

    def _on_history_setting(self):
        on = self.cfg["keep_history"]
        self.tabs.setTabVisible(self.tabs.indexOf(self.pages["history"]), on)
        if not on and self.ctl.history.count() and QMessageBox.question(
                self, "History", "Also delete the saved history?") == QMessageBox.Yes:
            self.ctl.clear_history()

    def _confirm_clear(self):
        n = self.ctl.history.count()
        if n and QMessageBox.question(
                self, "Clear history", f"Delete all {n:,} transcript{'s' if n > 1 else ''}"
                "? This can't be undone."
        ) == QMessageBox.Yes:
            self.ctl.clear_history()

    def _export_history(self):
        """CSV (0.7.3: timestamp, transcription, model version and exact weights, for a
        spreadsheet or your own analysis) or JSON Lines (every column)."""
        name = time.strftime("hebrish-history-%Y-%m-%d.csv")
        path, chosen = QFileDialog.getSaveFileName(self, "Export history", str(Path.home() / name),
                                                   "CSV (*.csv);;JSON Lines (*.jsonl);;All files (*)")
        if path:
            jsonl = path.endswith(".jsonl") or (chosen.startswith("JSON") and not path.endswith(".csv"))
            n = (self.ctl.history.export_jsonl if jsonl else self.ctl.history.export_csv)(Path(path))
            self.status(f"Exported {n:,} transcripts to {path}")

    def _edit_entry(self, h):
        text, ok = QInputDialog.getMultiLineText(
            self, "Correct the transcript",
            "Fix any words the model got wrong. The original is kept alongside, so corrections "
            "can become training data.", h["text"])
        if ok and text.strip() and text.strip() != h["text"]:
            self.ctl.history.update_text(h["id"], text)
            self.show_history()

    def _delete_entry(self, h):
        self.ctl.history.delete(h["id"])
        self.show_history()

    def _more(self):
        self._hist_limit += HISTORY_PAGE
        self.show_history(keep_limit=True)

    def _show_stats(self):
        st = self.ctl.history.stats()
        for key, (big, small) in self.stat_tiles.items():
            a = st[key]
            big.setText(f"{a['words']:,} words")
            mins = a["seconds"] / 60
            spoken = f" · {mins / 60:.1f} h" if mins >= 90 else f" · {mins:.0f} min" if mins >= 1 else ""
            small.setText(f"{a['dictations']:,} dictation{'s' if a['dictations'] != 1 else ''}{spoken}")
        if st["since"]:
            self.stat_tiles["all"][1].setToolTip(
                f"Since {time.strftime('%d %b %Y', time.localtime(st['since']))}, "
                f"on {st['days_active']} day{'s' if st['days_active'] != 1 else ''}")

    def show_history(self, keep_limit=False):
        hist = self.ctl.history
        while self.hist_box.count():
            w = self.hist_box.takeAt(0).widget()
            if w:
                w.hide()                # deleteLater waits for the event loop; don't paint it meanwhile
                w.deleteLater()
        if not keep_limit:
            self._hist_limit = HISTORY_PAGE
        q = self.hist_search.text().strip()
        rows = hist.search(q, self._hist_limit + 1) if q else hist.recent(self._hist_limit + 1)
        more = len(rows) > self._hist_limit
        rows = rows[:self._hist_limit]
        total = hist.count()
        if q:
            self.hist_count.setText(f"{len(rows)}{'+' if more else ''} match{'es' if len(rows) != 1 else ''} "
                                    f"for “{q}”, best first")
        else:
            self.hist_count.setText(f"{total:,} transcript{'s' if total != 1 else ''}, newest first"
                                    if total else "")
        if not rows:
            empty = muted("No matches." if q else "Nothing yet. Every transcript is added here from now on.")
            empty.setAlignment(Qt.AlignCenter)
            self.hist_box.addWidget(empty)
        for h in rows:
            row = QFrame()
            row.setStyleSheet("QFrame { border-bottom: 1px solid palette(midlight); }"
                              "QLabel, QToolButton { border: none; }")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(4, 6, 4, 6)
            col = QVBoxLayout()
            col.setSpacing(2)
            shown = h.get("snippet") or h["text"]
            t = QLabel(objectName="transcript")
            if h.get("snippet"):
                esc = shown.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                t.setText(esc.replace("[", f"<b style='color:{BLUE}'>").replace("]", "</b>"))
            else:
                t.setTextFormat(Qt.PlainText)
                t.setText(shown)
            t.setWordWrap(True)
            t.setTextInteractionFlags(Qt.TextSelectableByMouse)
            col.addWidget(t)
            bits = [ago(h["at"]), f"{h['words']} words"]
            if h["seconds"]:
                bits.append(f"{h['seconds']:.0f} s")
            if h["source"] != "dictate":
                bits.append({"file": "from a file", "import": "imported"}.get(h["source"], h["source"]))
            if h["original"]:
                bits.append("corrected")
            if h["audio"]:
                bits.append("audio kept")
            col.addWidget(muted(" · ".join(bits)))
            rl.addLayout(col, 1)
            for name, label, fn in (("edit-copy", "Copy", lambda _=False, s=h["text"]: copy_to_clipboard(s)),
                                    ("document-edit", "Correct", lambda _=False, e=h: self._edit_entry(e)),
                                    ("edit-delete", "Delete", lambda _=False, e=h: self._delete_entry(e))):
                b = QToolButton()
                b.setIcon(QIcon.fromTheme(name))
                b.setText(label)
                b.setToolTip(label)
                b.setToolButtonStyle(Qt.ToolButtonIconOnly if QIcon.hasThemeIcon(name)
                                     else Qt.ToolButtonTextOnly)
                b.setIconSize(QSize(16, 16))
                b.clicked.connect(fn)
                rl.addWidget(b, 0, Qt.AlignTop)
            self.hist_box.addWidget(row)
        if more:
            b = QPushButton("Show more")
            b.clicked.connect(self._more)
            self.hist_box.addWidget(b, 0, Qt.AlignHCenter)
        self.hist_box.addStretch(1)
        self.btn_clear.setEnabled(bool(total))
        self._show_stats()
        self.hist_where.setText(f"{hist.path} ({human_size(hist.size_bytes())}). Text only, no audio. "
                                "Nothing leaves this computer.")

    def _do_pulse(self):
        self.rec.setProperty("pulse", not self.rec.property("pulse"))
        self.rec.style().unpolish(self.rec)
        self.rec.style().polish(self.rec)

    def update_state(self):
        st = self.ctl.state
        self.rec.setProperty("state", st)
        self.rec.setProperty("pulse", False)
        self.rec.setText({"idle": "Talk", "recording": "Stop", "busy": "…"}[st])
        self.rec.setEnabled(st != "busy")
        rec = st == "recording"
        self.btn_pause.setEnabled(rec)
        self.btn_pause.setText("Resume" if rec and self.ctl.recorder.paused else "Pause")
        self.btn_discard.setEnabled(rec)
        self.mic.setEnabled(not rec)
        if rec and self.btn_test.isChecked():
            self.btn_test.setChecked(False)
        self.btn_test.setEnabled(st == "idle")
        self.rec.style().unpolish(self.rec)
        self.rec.style().polish(self.rec)
        self._pulse.start() if st == "recording" else self._pulse.stop()
        self.state_label.setText("Paused" if st == "recording" and self.ctl.recorder.paused else
                                 {"idle": "Ready", "recording": "Listening…", "busy": "Working…"}[st])
        self.hint_label.setText(describe(self.cfg))
        for slot, lbl in getattr(self, "hk_labels", {}).items():
            lbl.setText(pretty(self.cfg[slot]))
        self.update_model()

    # -- models --------------------------------------------------------------------
    def _model_page(self):
        """One row per catalogue model, each with its own Download / Use / Delete, so a model can
        be downloaded without switching to it (0.5.0; before, a combo box picked the model and
        the one Download button acted on it). Then updates and the storage folder. One version per
        model since 0.5.1: an update replaces the old version, so there is no versions list."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)
        box, b = card("Models")
        top = QHBoxLayout()
        self.models_intro = muted()
        self.models_intro.setTextFormat(Qt.RichText)
        top.addWidget(self.models_intro, 1)
        helper = QPushButton(QIcon.fromTheme("help-contents"), "Help me choose…")
        helper.clicked.connect(self._help_choose)
        top.addWidget(helper, 0, Qt.AlignTop)
        b.addLayout(top)
        self.model_rows_box = QVBoxLayout()
        self.model_rows_box.setSpacing(0)
        b.addLayout(self.model_rows_box)
        self.model_rows: dict[str, dict] = {}
        lay.addWidget(box)

        box, b = card("Updates")
        self.model_label = QLabel()
        self.model_label.setWordWrap(True)
        self.model_label.setTextFormat(Qt.RichText)
        self.model_label.setOpenExternalLinks(True)
        b.addWidget(self.model_label)
        row = QHBoxLayout()
        self.btn_check = QPushButton("Check for updates")
        self.btn_check.clicked.connect(lambda: self.ctl.check_updates(manual=True))
        self.btn_update = QPushButton("Update", objectName="primary")
        self.btn_update.clicked.connect(lambda: self.ctl.latest and self.ctl.download(self.ctl.latest))
        self.btn_cancel = QPushButton("Cancel download")
        self.btn_cancel.clicked.connect(lambda: self.ctl.downloading and self.ctl.downloading.set())
        for w in (self.btn_check, self.btn_update, self.btn_cancel):
            row.addWidget(w)
        row.addStretch(1)
        b.addLayout(row)
        lay.addWidget(box)

        box, b = card("Where the models are stored")
        self.store_label = QLabel()
        self.store_label.setWordWrap(True)
        self.store_label.setTextFormat(Qt.RichText)
        self.store_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        b.addWidget(self.store_label)
        row = QHBoxLayout()
        change = QPushButton(QIcon.fromTheme("folder-open"), "Change folder…")
        change.clicked.connect(self._change_store)
        self.btn_store_default = QPushButton("Use the default folder")
        self.btn_store_default.clicked.connect(lambda: self._set_store(""))
        opener = QPushButton("Open folder")
        opener.clicked.connect(self._open_store)
        for w in (change, self.btn_store_default, opener):
            row.addWidget(w)
        row.addStretch(1)
        b.addLayout(row)
        lay.addWidget(box)
        lay.addStretch(1)
        return page

    def _line_header(self, ln) -> QFrame:
        """A line (Sabich, Jachnun, Shakshuka, stock): its mark, name, what it is trained for."""
        f = QFrame(objectName="lineHead")
        outer = QHBoxLayout(f)
        outer.setContentsMargins(4, 14, 4, 2)
        outer.setSpacing(10)
        pic = QLabel()
        name = f"model-{ln.variants[0].id}" if ln.variants else ""
        pic.setPixmap(icon(name if name and (ICONS / f"{name}.svg").exists() else "hebrish").pixmap(40, 40))
        pic.setFixedSize(42, 42)
        outer.addWidget(pic, 0, Qt.AlignTop)
        text = QLabel()
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        text.setOpenExternalLinks(True)
        link = f" <a href='{ln.card}'>About {ln.name}</a>" if ln.card else ""
        terms = (f" · <small>Free for personal and non-commercial use: <a href='{about.TERMS}'>terms</a></small>"
                 if ln.id != "stock" else "")
        text.setText(f"<b style='font-size:16px'>{ln.name}</b><br>"
                     f"<span style='color:gray'>{ln.summary}</span>{link}{terms}")
        outer.addWidget(text, 1)
        self.model_rows_box.addWidget(f)
        return f

    def _model_row(self, m) -> dict:
        """One variant of a line: name, who it is for, the speed/accuracy tiers, size and hardware,
        its state and Download / Use / Delete. A variant this build can't run (another engine, or
        planned) is shown greyed with where it runs instead, and has no buttons (0.6.0)."""
        f = QFrame(objectName="modelRow")
        outer = QHBoxLayout(f)
        outer.setContentsMargins(52, 8, 10, 8)
        outer.setSpacing(12)
        f.setStyleSheet("#modelRow { border: none; border-bottom: 1px solid palette(midlight); }"
                        " #modelRow QLabel { border: none; background: transparent; }")
        col = QVBoxLayout()
        col.setSpacing(3)
        head = QHBoxLayout()
        grey = "" if m.supported else "color: gray;"
        name = QLabel(f"<b style='font-size:14px; {grey}'>{m.name}</b>"
                      f" <small style='color:gray'>{m.base_model}</small>")
        head.addWidget(name)
        chip = QLabel(objectName="chip")
        chip.setStyleSheet(f"background: {BRAND_GREEN}; color: white; border-radius: 9px; padding: 1px 8px;"
                           " font-size: 11px; font-weight: 600;")
        chip.hide()
        head.addWidget(chip)
        is_rec = m.id == model_store.recommended_id()
        rec = QLabel("Recommended")
        rec.setStyleSheet("color: #0f6b5c; border: 1px solid #0f6b5c; border-radius: 9px;"
                          " padding: 0 7px; font-size: 11px;")
        rec.setVisible(is_rec)
        head.addWidget(rec)
        head.addStretch(1)
        col.addLayout(head)
        if m.recommendation:
            words = QLabel(m.recommendation)
            words.setWordWrap(True)
            words.setStyleSheet(grey)
            col.addWidget(words)
        facts = muted()
        facts.setTextFormat(Qt.RichText)
        facts.setOpenExternalLinks(True)
        size = f"{m.download_mb} MB" if m.download_mb else "size: see the card"
        facts.setText(f"{tiers_html(m)}<br><small>{size} · {m.hardware}"
                      + (f" · <a href='{m.card}'>Model card</a>" if m.card else "") + "</small>")
        col.addWidget(facts)
        status = QLabel()
        status.setStyleSheet("font-size: 12px;")
        status.setWordWrap(True)
        status.setTextFormat(Qt.RichText)
        if not m.supported:
            status.setText(f"<span style='color:gray'><b>Not in this app yet.</b> Runs on: {m.runs_on}</span>")
        elif not m.available:
            status.setText("<span style='color:gray'>Coming soon</span>")
        col.addWidget(status)
        pbar = QProgressBar(maximum=1000)
        pbar.hide()
        col.addWidget(pbar)
        outer.addLayout(col, 1)
        btns = QVBoxLayout()
        btns.setSpacing(4)
        dl = QPushButton(QIcon.fromTheme("download"), "Download", objectName="primary")
        dl.clicked.connect(lambda _=False, mid=m.id: self._download_model(mid))
        use = QPushButton(f"Switch to {m.name}")
        use.clicked.connect(lambda _=False, mid=m.id: self.ctl.use_model(mid))
        rm = QPushButton("Delete")
        rm.clicked.connect(lambda _=False, mid=m.id: self._delete_model(mid))
        for w in (dl, use, rm):
            w.setVisible(m.available)
            btns.addWidget(w)
        btns.addStretch(1)
        outer.addLayout(btns)
        self.model_rows_box.addWidget(f)
        return {"frame": f, "chip": chip, "status": status, "pbar": pbar, "dl": dl, "use": use, "rm": rm,
                "rec": is_rec}

    def _help_choose(self):
        from .choose import ChooseDialog
        ChooseDialog(self, self.ctl).exec()
        self.update_model()

    def _download_model(self, mid):
        m = model_store.get_model(mid)
        if m and m.available:
            self.ctl.download_model(mid)
            self.update_model()

    def _delete_model(self, mid):
        m = model_store.get_model(mid)
        if mid == model_store.current_id():
            self.banner("That's the model in use. Use another one first.")
            return
        if QMessageBox.question(self, "Delete model", f"Delete {m.name} "
                                f"({model_store.disk_usage(mid) >> 20} MB)? You can download it "
                                "again later.") == QMessageBox.Yes:
            model_store.remove_model(mid)
            self.update_model()

    def _change_store(self):
        start = str(model_store.ROOT if model_store.ROOT.exists() else Path.home())
        path = QFileDialog.getExistingDirectory(self, "Folder for the model weights", start)
        if path:
            self._set_store(path)

    def _set_store(self, path: str):
        new = Path(path).expanduser() if path else MODELS_DIR
        if new.resolve() == model_store.ROOT.resolve():
            return
        if self.ctl.state != "idle" or self.ctl.downloading:
            self.banner("Wait until dictation or the download has finished, then change the folder.")
            return
        on_disk = model_store.installed_ids()
        move = False
        if on_disk:
            names = ", ".join(model_store.get_model(m).name for m in on_disk)
            ans = QMessageBox.question(
                self, "Model folder", f"Move the downloaded models ({names}) to {new}?\n\n"
                "Yes moves them. No leaves them where they are; the app then looks only in the "
                "new folder, so they would need downloading again.",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if ans == QMessageBox.Cancel:
                return
            move = ans == QMessageBox.Yes
        self.ctl.set_models_dir(path, move)
        self.update_model()

    def _open_store(self):
        model_store.ROOT.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(model_store.ROOT)))

    def update_model(self):
        if not hasattr(self, "model_label"):
            return
        cur, ctl = model_store.active(), self.ctl
        sel = model_store.current()
        lines = model_store.lines()
        shape = [(v.id, v.available, v.supported) for ln in lines for v in ln.variants]
        if getattr(self, "_model_shape", None) != shape:          # catalogue changed: rebuild
            for w in getattr(self, "_model_widgets", []):
                w.deleteLater()
            self._model_widgets, self.model_rows = [], {}
            for ln in lines:
                self._model_widgets.append(self._line_header(ln))
                for v in ln.variants:
                    r = self._model_row(v)
                    self._model_widgets.append(r["frame"])
                    if v.available:
                        self.model_rows[v.id] = r
            self._model_shape = shape
        cat = [m for m in model_store.models() if m.available]
        busy = bool(ctl.downloading or ctl.downloading_id)
        rec = model_store.get_model(model_store.recommended_id())
        self.models_intro.setText(
            "Each line is what a model is trained for; under it are its versions, from most accurate "
            "to fastest. " + (f"<b>{rec.name}</b> is the recommended one. " if rec else "")
            + "A model downloads once and then works offline; the one you dictate with is outlined "
            "in green. Speed and accuracy tiers are estimates.")
        for m in cat:
            r, inst = self.model_rows[m.id], model_store.active(m.id)
            in_use = m.id == sel.id
            # The row in use is tinted and outlined in brand green, so it reads as "this one" rather
            # than as a row with its buttons missing (Daniel, 2026-10-21: the in-use row looked greyed
            # out next to rows that had Use / Delete buttons).
            active = in_use and inst is not None
            r["chip"].setText("✓ In use")
            r["chip"].setVisible(active)
            r["frame"].setStyleSheet(
                (f"#modelRow {{ border: 2px solid {BRAND_GREEN}; border-radius: 10px;"
                 " background: rgba(15, 107, 92, 0.08); }" if active else
                 "#modelRow { border: none; border-bottom: 1px solid palette(midlight); }")
                + " #modelRow QLabel { border: none; background: transparent; }")
            r["use"].setObjectName("primary" if r["rec"] else "")
            r["use"].style().unpolish(r["use"])
            r["use"].style().polish(r["use"])
            here = ctl.downloading_id == m.id
            if here:
                text = "<b>Downloading…</b>"
            elif inst:
                text = (f"<span style='color:#2e9e5b'>✓ Downloaded</span> · {inst[1].label} · "
                        f"{model_store.disk_usage(m.id) >> 20} MB")
            else:
                text = f"<span style='color:gray'>Not downloaded · about {m.download_mb or 660} MB</span>"
            r["status"].setText(text)
            r["pbar"].setVisible(here and ctl.downloading is not None)
            r["dl"].setVisible(inst is None)
            r["dl"].setEnabled(not busy)
            r["dl"].setText("Downloading…" if here else "Download")
            r["use"].setVisible(inst is not None and not in_use)
            r["use"].setEnabled(ctl.state == "idle")
            r["rm"].setVisible(inst is not None and not in_use)
            r["rm"].setEnabled(not here)

        if cur is None:
            text = (f"<b>{sel.name} isn't downloaded yet.</b> Download it above, or download "
                    "another model and click Switch to.")
        else:
            text = f"In use: <b>{sel.name}</b> {cur[1].label}"
            if ctl.engine.loaded_dir != cur[0]:
                text += " <i>(loading…)</i>"
        if ctl.update_available():
            text += f"<br>New version available: <b style='color:{BLUE}'>{ctl.latest.label}</b>"
        last = load_json(STATE_PATH).get("last_check")
        if last:
            text += f"<br><small>Last checked {time.strftime('%Y-%m-%d %H:%M', time.localtime(last))}</small>"
        self.model_label.setText(text)
        self.btn_update.setVisible(not busy and ctl.update_available())
        self.btn_update.setText(f"Update to {ctl.latest.version}" if ctl.latest else "Update")
        self.btn_cancel.setVisible(ctl.downloading is not None)
        self.btn_check.setEnabled(not busy)

        custom = model_store.ROOT.resolve() != MODELS_DIR.resolve()
        self.store_label.setText(
            f"<b>{model_store.ROOT}</b><br><small>"
            + ("A folder you chose. " if custom else "The default folder. ")
            + "Each model is a subfolder named by its id (Jachnun's is codeswitch), with the "
            "version in use inside it.</small>")
        self.btn_store_default.setVisible(custom)

    def progress(self, frac: float, text: str):
        r = self.model_rows.get(self.ctl.downloading_id or "")
        if r is None:
            return
        if frac < 0:
            r["pbar"].hide()
            return
        r["pbar"].show()
        r["pbar"].setValue(int(frac * 1000))
        r["pbar"].setFormat(text)

    # -- settings ------------------------------------------------------------------
    def _settings_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 14, 16, 14)

        box, b = card("Dictation")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.hk_labels, self.hk_btns = {}, {}
        for slot, label in (("hotkey", "Toggle key"), ("ptt_hotkey", "Push-to-talk key")):
            form.addRow(label, self._hotkey_row(slot))
            if slot == "hotkey":
                form.addRow("", self._check("hold_to_talk", "Holding it is push-to-talk too",
                                            self.update_state))
        form.addRow("", self._check("double_tap_retake", "Double-tap it while dictating to start "
                                                         "again (Retake)", self.update_state))
        form.addRow("", muted("Tap the toggle key to start, tap again to stop. Hold the "
                              "push-to-talk key while you talk. Any key on any keyboard or foot "
                              "pedal: pick ones nothing else uses (F13–F24 are ideal). With "
                              "double-tap on, a single tap stops ~0.3 s later, while it waits "
                              "for a second tap."))
        esc = self._check("escape_discards", "Esc discards the take while dictating", self.update_state)
        esc.setToolTip("Esc also reaches the app you're in.")
        form.addRow("", esc)
        self.chord_entry = chord = QLineEdit(self.cfg["paste_chord"])
        chord.setToolTip("ctrl+v for most apps; ctrl+shift+v for terminals")
        chord.textChanged.connect(lambda t: self._on_chord(chord, t))
        form.addRow("Paste shortcut", chord)
        b.addLayout(form)
        b.addWidget(muted("Output (at the cursor, clipboard, this window: any combination) and the "
                          "microphone are on the Dictate tab."))
        b.addWidget(self._check("trailing_space", "Add a space after each transcript"))
        nf = self._check("detect_no_field", "Experimental: when a take finds no text field, offer "
                                            "Paste in the overlay", self._on_detect_no_field)
        nf.setToolTip("After each pasted take, Hebrish asks the desktop's accessibility interface "
                      "whether a text field had focus. Turning this on switches that interface on "
                      "for every app. Some apps report no field when there is one. The Paste last "
                      "transcription key (Action keys) works either way.")
        b.addWidget(nf)
        caps = self._check("all_caps", "Dictate in ALL CAPS (from the next take)")
        caps.setToolTip("Just for fun: everything you dictate is pasted in capitals. History and the "
                        "File tab keep the normal case.")
        b.addWidget(caps)
        b.addWidget(self._check("clear_each_take", "Start the Dictate tab's text box empty for each "
                                                   "take (otherwise takes collect, a blank line "
                                                   "between them; all are in History)"))
        b.addWidget(self._check("keep_history", "Keep a history of every transcript (History tab)", self._on_history_setting))
        lay.addWidget(box)

        box, b = card("Action keys")
        b.addWidget(muted("Optional keys for a macropad or foot pedals, one per action. Each acts "
                          "when pressed, alongside the toggle and push-to-talk keys. Start also "
                          "resumes a paused take."))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        for a, label in ACTIONS:
            form.addRow(label, self._hotkey_row(f"key_{a}"))
        send = QLineEdit(self.cfg["send_chord"])
        send.setToolTip("enter for most chat boxes; ctrl+enter or shift+enter where Enter "
                        "starts a new line")
        send.textChanged.connect(lambda t: self._on_chord(send, t, "send_chord"))
        form.addRow("Send key", send)
        b.addLayout(form)
        b.addWidget(muted("Stop and send stops dictation, waits for the last words to be "
                          "inserted, then presses the send key, so nothing is cut off when you "
                          "submit (a chat box, Claude Code, a terminal). Paste output only."))
        lay.addWidget(box)

        box, b = card("Speed")
        b.addWidget(muted("Inserting as you go (on by default, Normal: every ~5 seconds) decodes the take "
                          "while you are still talking, at a pause, so text appears as you speak "
                          "and only the last few seconds are left when you stop. When you stop "
                          "to think for a second, what you said so far goes in straight away. "
                          "Text already inserted stays if you then Discard or Retake. Off: "
                          "everything is inserted at once when you stop.<br><br>With "
                          "<b>Shakshuka</b>, the streaming model, any setting other than Off "
                          "inserts text while you speak, in the pieces chosen below, and the "
                          "interval doesn't apply."))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("Insert as you go", self._live_row())
        form.addRow("Shakshuka pastes", self._combo("stream_release", STREAM))
        th = QSpinBox(minimum=0, maximum=os.cpu_count() or 16, value=self.cfg["num_threads"])
        th.setSpecialValueText(f"Auto ({threads({'num_threads': 0})})")
        reload = QTimer(self, singleShot=True, interval=900, timeout=self.ctl.load_model)   # once, after the last click
        th.valueChanged.connect(lambda v: (self.cfg.set("num_threads", v), reload.start()))
        form.addRow("CPU threads", th)
        b.addLayout(form)
        lay.addWidget(box)

        box, b = card("Sounds")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("Feedback", self._combo("feedback", FEEDBACK, lambda: (
            voice.setEnabled(self.cfg["feedback"] == "voice"), self.ctl.cue("recording"))))
        voice = self._combo("voice", audio.VOICES, lambda: self.ctl.cue("recording"))
        voice.setEnabled(self.cfg["feedback"] == "voice")
        voice.setToolTip("Herman, Corn and Hilbert are the voices of the My Weird Prompts podcast")
        form.addRow("Voice", voice)
        row = QHBoxLayout()
        vol = QSlider(Qt.Horizontal, minimum=0, maximum=100, value=self.cfg["beep_volume"])
        vol_lbl = QLabel(f"{self.cfg['beep_volume']} %")
        vol_lbl.setMinimumWidth(44)
        vol.valueChanged.connect(lambda v: vol_lbl.setText(f"{v} %"))
        vol.sliderReleased.connect(lambda: (self.cfg.set("beep_volume", vol.value()),
                                            self.ctl.cue("recording")))
        row.addWidget(vol, 1)
        row.addWidget(vol_lbl)
        form.addRow("Volume", row)
        b.addLayout(form)
        b.addWidget(muted("Voice says “Recording”, “Paused”, “Resumed”, “Transcribing”, "
                          "“Discarded”, and “Copied” when Output is the clipboard, in Herman's, "
                          "Corn's or Hilbert's voice. Nothing is said when the text arrives: you "
                          "can see it. The microphone ignores the prompt while it plays, so it "
                          "never ends up in your text."))
        b.addWidget(self._check("quiet_hours", "Quiet hours: no sounds between"))
        row = QHBoxLayout()
        for key in ("quiet_from", "quiet_to"):
            te = QTimeEdit(QTime.fromString(self.cfg[key], "HH:mm"), displayFormat="HH:mm")
            te.timeChanged.connect(lambda t, k=key: self.cfg.set(k, t.toString("HH:mm")))
            if key == "quiet_to":
                row.addWidget(QLabel("and"))
            row.addWidget(te)
        row.addStretch(1)
        b.addLayout(row)
        lay.addWidget(box)

        box, b = card("Floating overlay")
        b.addWidget(muted("A small bar over every app, like the Android floating mic: the timer, "
                          "a level meter, Pause, Retake and Discard. Drag it anywhere. It never "
                          "takes the keyboard focus, so the text still goes where your cursor is."))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        ov = self._combo("overlay", OVERLAY, self.ctl.overlay_changed)
        form.addRow("Show", ov)
        op = QSpinBox(minimum=25, maximum=100, suffix=" %", value=self.cfg["overlay_opacity"])
        op.valueChanged.connect(lambda v: (self.cfg.set("overlay_opacity", v), self.ctl.overlay_changed()))
        form.addRow("Idle opacity", op)
        b.addLayout(form)
        reset = QPushButton("Reset position")
        reset.clicked.connect(lambda: (self.cfg.set("overlay_pos", None), self.ctl.overlay_changed()))
        b.addWidget(reset, 0, Qt.AlignLeft)
        if not self.ctl.overlay.available:
            ov.setEnabled(False)
            op.setEnabled(False)
            reset.setEnabled(False)
            b.addWidget(muted(self.ctl.overlay.reason))
        lay.addWidget(box)

        box, b = card("Model updates")
        form = QFormLayout()
        spin = QSpinBox(minimum=0, maximum=24 * 7, suffix=" h", value=self.cfg["update_check_hours"])
        spin.setSpecialValueText("Never")
        spin.valueChanged.connect(lambda v: self.cfg.set("update_check_hours", v))
        form.addRow("Check every", spin)
        b.addLayout(form)
        b.addWidget(self._check("auto_update", "Install new model versions automatically"))
        b.addWidget(muted("A new version replaces the old one: the old version is deleted once the "
                          "new one has downloaded and checked out, so each model is on disk once."))
        lay.addWidget(box)

        box, b = card("App updates")
        b.addWidget(self._check("app_update_check", "Check for a new version of Hebrish (at start, then daily)"))
        b.addWidget(muted({
            "apt": "Installed from the Hebrish repository: an update installs from here (it asks "
                   "for your password) or with Software Updater, like any other package.",
            "deb-manual": "Installed from a .deb without the Hebrish repository: you'll get a link "
                          "to the new .deb. Installing it adds the repository, so updates after "
                          "that install from here.",
            "windows": "The portable Windows build: you'll get a link to the new zip.",
            "source": "Running from source: you'll be told when there's a new version.",
        }[self.ctl.app_method]))
        row = QHBoxLayout()
        check = QPushButton("Check now")
        check.clicked.connect(lambda: (self.app_status_label.setText("Checking…"),
                                       self.ctl.check_app_update(manual=True)))
        self.btn_restart = QPushButton(f"Restart {APP_NAME}", objectName="primary")
        self.btn_restart.clicked.connect(self.ctl.restart)
        self.btn_restart.hide()
        row.addWidget(check)
        row.addWidget(self.btn_restart)
        row.addStretch(1)
        b.addLayout(row)
        self.app_status_label = muted()
        b.addWidget(self.app_status_label)
        lay.addWidget(box)

        box, b = card("System")
        self.chk_autostart = QCheckBox("Start at login, in the tray", checked=autostart.enabled())
        self.chk_autostart.toggled.connect(self.ctl.set_autostart)
        b.addWidget(self.chk_autostart)
        path = muted(f"Config file: {CONFIG_PATH}<br>App version {__version__}")
        path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        b.addWidget(path)
        lay.addWidget(box)
        lay.addStretch(1)
        return page

    def _check(self, key, label, then=None):
        c = QCheckBox(label, checked=self.cfg[key])
        c.toggled.connect(lambda v: (self.cfg.set(key, v), then and then()))
        return c

    def _combo(self, key, options, then=None):
        c = QComboBox()
        for val, label in options:
            c.addItem(label, val)
        c.setCurrentIndex(max(0, c.findData(self.cfg[key])))

        def changed(_i):
            self.cfg.set(key, c.currentData())
            self.update_state()
            if then:
                then()
        c.currentIndexChanged.connect(changed)
        return c

    def _live_row(self):
        """Preset combo, plus a seconds box shown for Custom (any value not in LIVE)."""
        row = QHBoxLayout()
        c = QComboBox()
        for val, label in LIVE:
            c.addItem(label, val)
        presets = [v for v, _ in LIVE if v >= 0]
        cur = self.cfg["live_insert_s"]
        spin = QSpinBox(minimum=3, maximum=60, suffix=" s", value=cur if cur not in presets else 5)
        c.setCurrentIndex(c.findData(cur if cur in presets else -1))
        spin.setVisible(cur not in presets)

        def changed(_i):
            custom = c.currentData() == -1
            spin.setVisible(custom)
            self.cfg.set("live_insert_s", spin.value() if custom else c.currentData())
            self.update_state()
        c.currentIndexChanged.connect(changed)
        spin.valueChanged.connect(lambda v: c.currentData() == -1 and self.cfg.set("live_insert_s", v))
        row.addWidget(c)
        row.addWidget(spin)
        row.addStretch(1)
        return row

    def _on_chord(self, entry, text, key="paste_chord"):
        try:
            parse_chord(text)
            entry.setStyleSheet("")
            self.cfg.set(key, text.strip().lower())
        except ValueError:
            entry.setStyleSheet("border: 1px solid #D62828;")

    def _hotkey_row(self, slot):
        row = QHBoxLayout()
        lbl = QLabel(pretty(self.cfg[slot]))
        lbl.setStyleSheet("font-weight: 600;")
        change = QPushButton("Change…")
        change.clicked.connect(lambda: self._capture_hotkey(slot))
        clear = QPushButton("Clear")
        clear.clicked.connect(lambda: (self.cfg.set(slot, ""), self.update_state()))
        row.addWidget(lbl, 1)
        row.addWidget(change)
        row.addWidget(clear)
        self.hk_labels[slot], self.hk_btns[slot] = lbl, change
        return row

    def _capture_hotkey(self, slot):
        for b in self.hk_btns.values():
            b.setEnabled(False)
        self.hk_labels[slot].setText("Press the key you want…")
        self._capture_slot = slot
        self.ctl.sig.captured.connect(self._captured)
        self.ctl.hotkeys.capture_next_key(self.ctl.sig.captured.emit)

    def _captured(self, name):
        self.ctl.sig.captured.disconnect(self._captured)
        slot = self._capture_slot
        for other in SLOTS:                    # one key, one job: move it
            if other != slot and self.cfg[other] == name:
                self.cfg[other] = ""
        self.cfg.set(slot, name)
        for b in self.hk_btns.values():
            b.setEnabled(True)
        self.update_state()

    # -- about ---------------------------------------------------------------------
    def _about_page(self):
        self._about = about.AboutPage(icon("hebrish"), card, muted)
        self.tabs.currentChanged.connect(lambda i: self.tabs.widget(i) is self._about and self._about.refresh())
        return self._about

    # -- misc ----------------------------------------------------------------------
    def toast(self, text="Settings saved"):
        if not self.isVisible():
            return
        t = self.toast_label
        t.setText(f"✓  {text}")
        t.adjustSize()
        t.resize(t.width() + 28, t.height() + 12)
        root = t.parentWidget()
        t.move((root.width() - t.width()) // 2, root.height() - t.height() - 36)
        t.raise_()
        t.show()
        self._toast_timer.start()

    def status(self, text):
        self.status_label.setText(text)

    def _on_detect_no_field(self):
        if self.cfg["detect_no_field"]:
            from .. import focus
            focus.enable_bus(True)

    def sync_output(self):
        """Output and paste shortcut were changed from the tray menu."""
        widgets = [*self.output_buttons.values(), self.chord_entry]
        for w in widgets:
            w.blockSignals(True)
        for key, btn in self.output_buttons.items():
            btn.setChecked(bool(self.cfg[key]))
        self.chord_entry.setText(self.cfg["paste_chord"])
        self.chord_entry.setStyleSheet("")
        for w in widgets:
            w.blockSignals(False)
        self.update_state()

    def sync_autostart(self, on: bool):
        self.chk_autostart.blockSignals(True)
        self.chk_autostart.setChecked(on)
        self.chk_autostart.blockSignals(False)

    def banner(self, text):
        self.banner_label.setText(text)
        self.banner_label.show()
        self.present_tab("dictate")
