"""Main window: header, then Dictate / Model / Settings / About tabs."""

import time

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
                               QScrollArea, QSpinBox, QTabWidget, QTextBrowser, QToolButton,
                               QVBoxLayout, QWidget)

from .. import __version__, audio, autostart, model_store
from ..config import APP_NAME, CONFIG_PATH, STATE_PATH, TAGLINE, load_json
from ..hotkey import pretty
from ..inserter import copy_to_clipboard, parse_chord
from . import about
from .app import icon
from .style import BLUE

MODES = [("hybrid", "Tap to toggle, hold for push-to-talk"),
         ("toggle", "Tap to start, tap to stop"),
         ("hold", "Push-to-talk (hold)")]


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
        self.tabs.addTab(self._dictate_page(), "Dictate")
        from .transcribe import TranscribePage
        self.transcribe = TranscribePage(ctl, card, muted)
        self.tabs.addTab(self.transcribe, "Transcribe")
        self.tabs.addTab(self._scroll(self._model_page()), "Model")
        self.tabs.addTab(self._scroll(self._settings_page()), "Settings")
        self.tabs.addTab(self._about_page(), "About")
        outer.addWidget(self.tabs, 1)

        self.status_label = muted()
        self.status_label.setContentsMargins(16, 4, 16, 8)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        outer.addWidget(self.status_label)
        self.setCentralWidget(root)

        self._pulse = QTimer(self, interval=550, timeout=self._do_pulse)
        self.update_state()
        self.show_history()

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
            self.tabs.setCurrentIndex({"dictate": 0, "transcribe": 1, "model": 2, "settings": 3, "about": 4}[name])
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, ev):
        if not self.quitting:            # close = back to the tray
            ev.ignore()
            self.hide()

    # -- dictate -------------------------------------------------------------------
    def _dictate_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 14, 16, 8)
        lay.setSpacing(12)

        self.banner_label = QLabel(objectName="banner")
        self.banner_label.setWordWrap(True)
        self.banner_label.hide()
        lay.addWidget(self.banner_label)

        self.rec = QPushButton("Talk", objectName="record")
        self.rec.setFixedSize(132, 132)
        self.rec.setCursor(Qt.PointingHandCursor)
        self.rec.clicked.connect(self.ctl.toggle)
        lay.addWidget(self.rec, 0, Qt.AlignHCenter)
        self.state_label = QLabel(alignment=Qt.AlignHCenter)
        self.state_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        lay.addWidget(self.state_label)
        self.hint_label = muted()
        self.hint_label.setAlignment(Qt.AlignHCenter)
        lay.addWidget(self.hint_label)

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

        self.hist_box = QVBoxLayout()
        self.hist_box.setSpacing(6)
        inner = QWidget()
        inner.setLayout(self.hist_box)
        sc = self._scroll(inner)
        sc.setMinimumHeight(180)
        blay.addWidget(sc, 1)
        lay.addWidget(box, 1)
        return page

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
            empty = muted("Nothing yet. Press your hotkey and start talking; the text appears "
                          "wherever your cursor is.")
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
        self.rec.style().unpolish(self.rec)
        self.rec.style().polish(self.rec)
        self._pulse.start() if st == "recording" else self._pulse.stop()
        key = pretty(self.cfg["hotkey"])
        how = {"hold": f"Hold {key} while you talk",
               "toggle": f"Tap {key} to start, tap again to stop",
               "hybrid": f"Tap {key} to start and stop, or hold it while you talk"}[self.cfg["mode"]]
        self.state_label.setText({"idle": "Ready", "recording": "Listening…",
                                  "busy": "Working…"}[st])
        self.hint_label.setText(how)
        if hasattr(self, "hk_label"):
            self.hk_label.setText(key)
        self.update_model()

    # -- model ---------------------------------------------------------------------
    def _model_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 14, 16, 14)
        box, b = card("Choose a model")
        self.picker = QComboBox()
        self.picker.activated.connect(self._on_pick)
        b.addWidget(self.picker)
        self.model_summary = muted()
        self.model_summary.setTextFormat(Qt.RichText)
        self.model_summary.setOpenExternalLinks(True)
        b.addWidget(self.model_summary)
        lay.addWidget(box)

        box, b = card("Status")
        self.model_label = QLabel()
        self.model_label.setWordWrap(True)
        self.model_label.setTextFormat(Qt.RichText)
        b.addWidget(self.model_label)
        row = QHBoxLayout()
        self.btn_check = QPushButton("Check for update")
        self.btn_check.clicked.connect(lambda: self.ctl.check_updates(manual=True))
        self.btn_update = QPushButton("Download", objectName="primary")
        self.btn_update.clicked.connect(self._on_download)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(lambda: self.ctl.downloading and self.ctl.downloading.set())
        for w in (self.btn_check, self.btn_update, self.btn_cancel):
            row.addWidget(w)
        row.addStretch(1)
        b.addLayout(row)
        self.pbar = QProgressBar(maximum=1000)
        self.pbar.hide()
        b.addWidget(self.pbar)
        lay.addWidget(box)

        box, b = card("Installed versions")
        b.addWidget(muted("Kept versions stay on disk so you can switch back. "
                          "Turn off “Keep previous versions” in Settings to save space."))
        row = QHBoxLayout()
        self.versions = QComboBox()
        row.addWidget(self.versions, 1)
        use = QPushButton("Use")
        use.clicked.connect(self._use_version)
        delete = QPushButton("Delete")
        delete.clicked.connect(self._delete_version)
        row.addWidget(use)
        row.addWidget(delete)
        b.addLayout(row)
        self.others_label = muted()
        b.addWidget(self.others_label)
        self.btn_free = QPushButton("Delete the other models")
        self.btn_free.clicked.connect(self._delete_others)
        b.addWidget(self.btn_free, 0, Qt.AlignLeft)
        lay.addWidget(box)
        lay.addStretch(1)
        return page

    def _on_pick(self, _i):
        mid = self.picker.currentData()
        m = model_store.get_model(mid)
        if not m or not m.available or mid == model_store.current_id():
            self.update_model()
            return
        if not model_store.installed(mid) and QMessageBox.question(
                self, "Download model",
                f"{m.name} isn't on this computer yet. Download it now (about 660 MB)? "
                "It works offline afterwards.") != QMessageBox.Yes:
            self.update_model()
            return
        self.ctl.select_model(mid)

    def _delete_others(self):
        cur = model_store.current_id()
        others = [mid for mid in model_store.installed_ids() if mid != cur]
        names = ", ".join(model_store.get_model(m).name for m in others)
        if others and QMessageBox.question(
                self, "Delete models", f"Delete {names}? You can download them again later.") == QMessageBox.Yes:
            for mid in others:
                model_store.remove_model(mid)
            self.update_model()

    def _on_download(self):
        if self.ctl.latest:
            self.ctl.download(self.ctl.latest)
        else:
            self.ctl.pending_download = model_store.current_id()
            self.ctl.check_updates(manual=True)

    def _use_version(self):
        name = self.versions.currentData()
        if name:
            model_store.set_active(name)
            self.ctl.load_model()

    def _delete_version(self):
        name = self.versions.currentData()
        cur = model_store.active()
        if not name:
            return
        if cur and cur[0].name == name:
            self.banner("That's the version in use. Switch to another one first.")
            return
        model_store.remove(name)
        self.update_model()

    def update_model(self):
        if not hasattr(self, "model_label"):
            return
        cur, ctl = model_store.active(), self.ctl
        sel = model_store.current()
        on_disk = set(model_store.installed_ids())
        self.picker.blockSignals(True)
        self.picker.clear()
        for m in model_store.models():
            tag = "" if m.available else "  (coming soon)"
            if m.id in on_disk:
                tag = "  ✓ downloaded"
            self.picker.addItem(m.name + tag, m.id)
            if not m.available:
                self.picker.model().item(self.picker.count() - 1).setEnabled(False)
        self.picker.setCurrentIndex(self.picker.findData(sel.id))
        self.picker.setEnabled(not ctl.downloading)
        self.picker.blockSignals(False)
        link = f" <a href='{sel.card}'>Model card</a>" if sel.card else ""
        if sel.id != "stock":  # a Hebrish fine-tune (codeswitch, sabich): site links, terms
            link += f" · <a href='{about.HEBRISH}'>hebrish.app</a> · " + " · ".join(
                f"<a href='{u}'>{n}</a>" for n, u in about.HEBRISH_LINKS[1:])
        soon = [m.name for m in model_store.models() if not m.available]
        self.model_summary.setText(sel.summary + link + (
            f"<br><small>Coming soon: {', '.join(soon)}.</small>" if soon else ""))
        if cur is None:
            text = (f"<b>{sel.name} isn't downloaded yet</b> (~660 MB). Click Download; "
                    "it downloads once and then works offline.")
            if sel.id != "stock":  # a Hebrish fine-tune (codeswitch, sabich): site links, terms
                text += (f"<br><small>By downloading it you agree to the <a href='{about.TERMS}'>"
                         "terms of use</a>: free for personal and non-commercial use.</small>")
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
        busy = bool(ctl.downloading)
        self.btn_update.setVisible(not busy and (cur is None or ctl.update_available()))
        self.btn_update.setText("Download model" if cur is None else
                                f"Update to {ctl.latest.version}" if ctl.latest else "Update")
        self.btn_cancel.setVisible(busy)
        self.btn_check.setEnabled(not busy)
        self.versions.clear()
        for d, m in model_store.installed():
            self.versions.addItem(m.label + ("  ✓ in use" if cur and d == cur[0] else ""), d.name)
        if cur:
            self.versions.setCurrentIndex(self.versions.findData(cur[0].name))
        others = [mid for mid in on_disk if mid != sel.id]
        self.others_label.setText("Also on disk: " + ", ".join(
            f"{model_store.get_model(mid).name} ({model_store.disk_usage(mid) >> 20} MB)" for mid in others)
            if others else "")
        self.others_label.setVisible(bool(others))
        self.btn_free.setVisible(bool(others) and not busy)

    def progress(self, frac: float, text: str):
        if frac < 0:
            self.pbar.hide()
            return
        self.pbar.show()
        self.pbar.setValue(int(frac * 1000))
        self.pbar.setFormat(text)

    # -- settings ------------------------------------------------------------------
    def _settings_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 14, 16, 14)

        box, b = card("Dictation")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        hk = QHBoxLayout()
        self.hk_label = QLabel(pretty(self.cfg["hotkey"]))
        self.hk_label.setStyleSheet("font-weight: 600;")
        self.hk_btn = QPushButton("Change…")
        self.hk_btn.clicked.connect(self._capture_hotkey)
        hk.addWidget(self.hk_label, 1)
        hk.addWidget(self.hk_btn)
        form.addRow("Hotkey", hk)
        form.addRow("", muted("Any key on any keyboard or foot pedal. Pick one nothing else "
                              "uses: F13–F24 are ideal."))
        form.addRow("Mode", self._combo("mode", MODES))
        form.addRow("Output", self._combo("insert", [("paste", "Paste at the cursor"),
                                                     ("clipboard", "Clipboard only")]))
        chord = QLineEdit(self.cfg["paste_chord"])
        chord.setToolTip("ctrl+v for most apps; ctrl+shift+v for terminals")
        chord.textChanged.connect(lambda t: self._on_chord(chord, t))
        form.addRow("Paste shortcut", chord)
        mics = QComboBox()
        mics.addItem("System default", "")
        for name in audio.input_devices():
            mics.addItem(name, name)
        mics.setCurrentIndex(max(0, mics.findData(self.cfg["audio_device"])))
        mics.currentIndexChanged.connect(lambda _i: self.cfg.set("audio_device", mics.currentData()))
        form.addRow("Microphone", mics)
        b.addLayout(form)
        for key, label in (("beeps", "Start/stop beeps"),
                           ("trailing_space", "Add a space after each transcript"),
                           ("keep_history", "Remember recent transcripts between sessions")):
            b.addWidget(self._check(key, label))
        lay.addWidget(box)

        box, b = card("Model updates")
        form = QFormLayout()
        spin = QSpinBox(minimum=0, maximum=24 * 7, suffix=" h", value=self.cfg["update_check_hours"])
        spin.setSpecialValueText("Never")
        spin.valueChanged.connect(lambda v: self.cfg.set("update_check_hours", v))
        form.addRow("Check every", spin)
        b.addLayout(form)
        b.addWidget(self._check("auto_update", "Install new versions automatically"))
        b.addWidget(self._check("keep_old_versions", "Keep previous versions (to switch back)"))
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

    def _check(self, key, label):
        c = QCheckBox(label, checked=self.cfg[key])
        c.toggled.connect(lambda v: self.cfg.set(key, v))
        return c

    def _combo(self, key, options):
        c = QComboBox()
        for val, label in options:
            c.addItem(label, val)
        c.setCurrentIndex(max(0, c.findData(self.cfg[key])))

        def changed(_i):
            self.cfg.set(key, c.currentData())
            self.update_state()
        c.currentIndexChanged.connect(changed)
        return c

    def _on_chord(self, entry, text):
        try:
            parse_chord(text)
            entry.setStyleSheet("")
            self.cfg.set("paste_chord", text.strip().lower())
        except ValueError:
            entry.setStyleSheet("border: 1px solid #D62828;")

    def _capture_hotkey(self):
        self.hk_btn.setEnabled(False)
        self.hk_label.setText("Press the key you want…")
        self.ctl.sig.captured.connect(self._captured)
        self.ctl.hotkeys.capture_next_key(self.ctl.sig.captured.emit)

    def _captured(self, name):
        self.ctl.sig.captured.disconnect(self._captured)
        self.cfg.set("hotkey", name)
        self.hk_btn.setEnabled(True)
        self.update_state()

    # -- about ---------------------------------------------------------------------
    def _about_page(self):
        tb = QTextBrowser()
        tb.setOpenExternalLinks(True)
        tb.setFrameShape(QFrame.NoFrame)
        tb.document().setDocumentMargin(18)
        self._about = tb
        self._refresh_about()
        self.tabs.currentChanged.connect(lambda i: self.tabs.widget(i) is self._about and self._refresh_about())
        return tb

    def _refresh_about(self):
        cur = model_store.active()
        self._about.setHtml(about.html(cur[1].full_label if cur else "not downloaded yet", BLUE))

    # -- misc ----------------------------------------------------------------------
    def status(self, text):
        self.status_label.setText(text)

    def banner(self, text):
        self.banner_label.setText(text)
        self.banner_label.show()
        self.present_tab("dictate")
