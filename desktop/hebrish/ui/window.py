"""Main window: header, then Dictate / File / [History] / Models / Settings / About tabs.
History is there only while "Keep a history" is on (off by default since 0.5.0)."""

import os
import time

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTime, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QScrollArea, QSlider, QSpinBox,
                               QTabWidget, QTimeEdit, QToolButton, QVBoxLayout, QWidget)

from .. import __version__, audio, autostart, model_store
from ..config import APP_NAME, CONFIG_PATH, MODELS_DIR, STATE_PATH, TAGLINE, load_json, threads
from ..hotkey import ACTIONS, SLOTS, describe, pretty
from ..inserter import copy_to_clipboard, parse_chord
from . import about
from .app import icon
from .meter import LevelMeter, verdict
from .style import BLUE, BRAND_GREEN

OVERLAY = [("off", "Off"), ("active", "While dictating"), ("always", "Always (a mic button)")]
LIVE = [(0, "Off: everything when you stop"), (10, "Every ~10 seconds"), (15, "Every ~15 seconds"),
        (20, "Every ~20 seconds"), (30, "Every ~30 seconds")]
OUTPUT = [("paste", "Paste at the cursor"), ("clipboard", "Clipboard only"),
          ("app", "This window's text box only")]
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


def ago(ts: float) -> str:
    d = time.time() - ts
    if d < 60:
        return "just now"
    if d < 3600:
        return f"{int(d // 60)} min ago"
    if d < 86400:
        return time.strftime("%H:%M", time.localtime(ts))
    return time.strftime("%d %b %H:%M", time.localtime(ts))


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

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.pages = {}
        self.pages["dictate"] = self._dictate_page()
        from .transcribe import TranscribePage
        self.transcribe = self.pages["file"] = TranscribePage(ctl, card, muted)
        self.pages["history"] = self._history_page()
        self.pages["model"] = self._scroll(self._model_page())
        self.pages["settings"] = self._scroll(self._settings_page())
        from .diagnostics import DiagnosticsPage
        self.pages["diagnostics"] = DiagnosticsPage(ctl, card, muted)
        self.pages["about"] = self._about_page()
        for key, label in (("dictate", "Dictate"), ("file", "File"), ("history", "History"),
                           ("model", "Models"), ("settings", "Settings"),
                           ("diagnostics", "Diagnostics"), ("about", "About")):
            self.tabs.addTab(self.pages[key], label)
        self.tabs.setTabVisible(self.tabs.indexOf(self.pages["history"]), self.cfg["keep_history"])
        self.ctl.sig.piece.connect(self._append_piece)
        self._meter_timer = QTimer(self, interval=60, timeout=self._update_meter)
        self._meter_timer.start()
        outer.addWidget(self.tabs, 1)

        self.status_label = muted()
        self.status_label.setContentsMargins(16, 4, 16, 8)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        outer.addWidget(self.status_label)
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
        self.text.setPlaceholderText("Press Talk or your hotkey and start talking. The text appears "
                                     "here as well as wherever Output sends it, and you can edit it.")
        self.text.setStyleSheet("font-size: 14px;")
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
        self.output_combo = self._combo("insert", OUTPUT)
        row.addWidget(self.output_combo)
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
            name = f"System default: {real}" if real else "System default"
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

    def _append_piece(self, text):
        cur = self.text.toPlainText()
        sep = "" if not cur or cur.endswith((" ", "\n")) else " "
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

    # -- history (optional) ------------------------------------------------------------
    def _history_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 14, 16, 8)
        box, blay = card()
        head = QHBoxLayout()
        head.addWidget(QLabel("Recent transcripts", objectName="cardTitle"))
        head.addStretch(1)
        self.btn_copy_all = QPushButton("Copy all")
        self.btn_copy_all.clicked.connect(
            lambda: copy_to_clipboard("\n\n".join(h["text"] for h in reversed(self.ctl.history))))
        self.btn_clear = QPushButton(QIcon.fromTheme("edit-clear-history"), "Clear history")
        self.btn_clear.clicked.connect(self._confirm_clear)
        head.addWidget(self.btn_copy_all)
        head.addWidget(self.btn_clear)
        blay.addLayout(head)
        blay.addWidget(muted("Kept because “Keep a history” is on in Settings: the last 50 "
                             "transcripts, saved on this computer."))
        self.hist_box = QVBoxLayout()
        self.hist_box.setSpacing(6)
        inner = QWidget()
        inner.setLayout(self.hist_box)
        sc = self._scroll(inner)
        sc.setMinimumHeight(180)
        blay.addWidget(sc, 1)
        lay.addWidget(box, 1)
        return page

    def _on_history_setting(self):
        on = self.cfg["keep_history"]
        self.tabs.setTabVisible(self.tabs.indexOf(self.pages["history"]), on)
        if not on and self.ctl.history and QMessageBox.question(
                self, "History", "Also delete the saved history?") == QMessageBox.Yes:
            self.ctl.clear_history()

    def _confirm_clear(self):
        n = len(self.ctl.history)
        if n and QMessageBox.question(
                self, "Clear history", f"Delete {n} transcript{'s' if n > 1 else ''}? This can't be undone."
        ) == QMessageBox.Yes:
            self.ctl.clear_history()

    def show_history(self):
        while self.hist_box.count():
            w = self.hist_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not self.ctl.history:
            empty = muted("Nothing yet. Transcripts are added here from now on.")
            empty.setAlignment(Qt.AlignCenter)
            self.hist_box.addWidget(empty)
        for h in self.ctl.history:
            row = QFrame()
            row.setStyleSheet("QFrame { border-bottom: 1px solid palette(midlight); }"
                              "QLabel, QToolButton { border: none; }")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(4, 6, 4, 6)
            col = QVBoxLayout()
            col.setSpacing(2)
            t = QLabel(h["text"], objectName="transcript")
            t.setWordWrap(True)
            t.setTextInteractionFlags(Qt.TextSelectableByMouse)
            col.addWidget(t)
            col.addWidget(muted(ago(h["at"])))
            rl.addLayout(col, 1)
            b = QToolButton()
            b.setIcon(QIcon.fromTheme("edit-copy"))
            b.setText("Copy")
            b.setToolTip("Copy")
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if QIcon.hasThemeIcon("edit-copy")
                                 else Qt.ToolButtonTextOnly)
            b.setIconSize(QSize(16, 16))
            b.clicked.connect(lambda _=False, s=h["text"]: copy_to_clipboard(s))
            rl.addWidget(b, 0, Qt.AlignTop)
            self.hist_box.addWidget(row)
        self.hist_box.addStretch(1)
        has = bool(self.ctl.history)
        self.btn_clear.setEnabled(has)
        self.btn_copy_all.setEnabled(has)

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
        self.models_intro = muted()
        self.models_intro.setTextFormat(Qt.RichText)
        b.addWidget(self.models_intro)
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

    def _model_row(self, m) -> dict:
        f = QFrame(objectName="modelRow")
        outer = QHBoxLayout(f)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(12)
        pic = QLabel()
        ic = icon(f"model-{m.id}")
        pic.setPixmap((ic if not ic.pixmap(8, 8).isNull() else icon("hebrish")).pixmap(48, 48))
        pic.setFixedSize(52, 52)
        outer.addWidget(pic, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(3)
        head = QHBoxLayout()
        name = QLabel(f"<b style='font-size:15px'>{m.name}</b>")
        head.addWidget(name)
        chip = QLabel(objectName="chip")
        chip.setStyleSheet(f"background: {BRAND_GREEN}; color: white; border-radius: 9px; padding: 1px 8px;"
                           " font-size: 11px; font-weight: 600;")
        head.addWidget(chip)
        rec = QLabel("Recommended")
        rec.setStyleSheet("color: #0f6b5c; border: 1px solid #0f6b5c; border-radius: 9px;"
                          " padding: 0 7px; font-size: 11px;")
        rec.setVisible(m.id == model_store.catalogue().get("recommended"))
        head.addWidget(rec)
        head.addStretch(1)
        col.addLayout(head)
        summary = muted()
        summary.setTextFormat(Qt.RichText)
        summary.setOpenExternalLinks(True)
        link = f" <a href='{m.card}'>Model card</a>" if m.card else ""
        terms = (f"<br><small>Free for personal and non-commercial use: <a href='{about.TERMS}'>"
                 "terms of use</a>.</small>" if m.id != "stock" else "")
        summary.setText(m.summary + link + terms)
        col.addWidget(summary)
        status = QLabel()
        status.setStyleSheet("font-size: 12px;")
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
            btns.addWidget(w)
        btns.addStretch(1)
        outer.addLayout(btns)
        self.model_rows_box.addWidget(f)
        return {"frame": f, "chip": chip, "status": status, "pbar": pbar, "dl": dl, "use": use, "rm": rm,
                "rec": m.id == model_store.catalogue().get("recommended")}

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
        cat = [m for m in model_store.models() if m.available]
        if list(self.model_rows) != [m.id for m in cat]:         # catalogue changed: rebuild
            for r in self.model_rows.values():
                r["frame"].deleteLater()
            self.model_rows = {m.id: self._model_row(m) for m in cat}
        busy = bool(ctl.downloading or ctl.downloading_id)
        rec = model_store.get_model(model_store.catalogue().get("recommended") or "")
        self.models_intro.setText(
            (f"<b>{rec.name}</b> is the recommended model. " if rec else "")
            + "Each model is about 660 MB, downloads once and then works offline. "
            "The one you dictate with is outlined in green. Not getting good results with one? "
            "Try the other.")
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
                text = "<span style='color:gray'>Not downloaded · about 660 MB</span>"
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
                    "another model and click Use.")
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
            + "Each model is a subfolder (codeswitch = Jachnun, sabich = Sabich, stock = "
            "Parakeet), with the version in use inside it.</small>")
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
        form.addRow("", self._check("escape_discards", "Esc discards the take while dictating "
                                                       "(Esc also reaches the app you're in)",
                                    self.update_state))
        chord = QLineEdit(self.cfg["paste_chord"])
        chord.setToolTip("ctrl+v for most apps; ctrl+shift+v for terminals")
        chord.textChanged.connect(lambda t: self._on_chord(chord, t))
        form.addRow("Paste shortcut", chord)
        b.addLayout(form)
        b.addWidget(muted("Output (paste, clipboard or the text box) and the microphone are on "
                          "the Dictate tab."))
        b.addWidget(self._check("trailing_space", "Add a space after each transcript"))
        b.addWidget(self._check("keep_history", "Keep a history of transcripts (adds a History tab, "
                                                "saved on this computer)", self._on_history_setting))
        lay.addWidget(box)

        box, b = card("Action keys")
        b.addWidget(muted("Optional keys for a macropad or foot pedals, one per action. Each acts "
                          "when pressed, alongside the toggle and push-to-talk keys. Start also "
                          "resumes a paused take."))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        for a, label in ACTIONS:
            form.addRow(label, self._hotkey_row(f"key_{a}"))
        b.addLayout(form)
        lay.addWidget(box)

        box, b = card("Speed")
        b.addWidget(muted("Inserting as you go (on by default, every ~10 seconds) decodes the take "
                          "while you are still talking, at a pause, so text appears as you speak "
                          "and only the last few seconds are left when you stop. Text already "
                          "inserted stays if you then Discard or Retake. Off: everything is "
                          "inserted at once when you stop."))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("Insert as you go", self._combo("live_insert_s", LIVE))
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
        form.addRow("Feedback", self._combo("feedback", FEEDBACK, lambda: self.ctl.cue("recording")))
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
                          "“Discarded”, and “Copied” when Output is the clipboard. Nothing is "
                          "said when the text arrives: you can see it."))
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

        box, b = card("System")
        auto = QCheckBox("Start at login, in the tray", checked=autostart.enabled())
        auto.toggled.connect(autostart.set_enabled)
        b.addWidget(auto)
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

    def _on_chord(self, entry, text):
        try:
            parse_chord(text)
            entry.setStyleSheet("")
            self.cfg.set("paste_chord", text.strip().lower())
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

    def banner(self, text):
        self.banner_label.setText(text)
        self.banner_label.show()
        self.present_tab("dictate")
