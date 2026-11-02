"""Transform dialog (B-82): pick a prompt from the library, optionally edit it, run it on the
transcript, then copy or save the result. Opened by *Transform…* on the Transcription tab.

Left: search, Type, Style, *Featured* / *Edited* filters and the list. Right: the prompt (editable;
*Save my version* stores a copy in user_transform_prompts, *Reset to original* deletes it) and,
after *Transform*, the result with *Copy* and *Save as a version* (<stem>.<prompt-id>.md beside
the saved transcript). The transcript in the box is never changed. Data and the model run:
hebrish/transforms.py.
"""

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QPushButton, QSplitter, QVBoxLayout, QWidget)

from .. import cleanup, transforms


class _Sig(QObject):
    done = Signal(object, object)      # (prompt id, text) or (prompt id, exception)


class TransformDialog(QDialog):
    def __init__(self, parent, db, text: str, save_version):
        """db: the history connection (GUI thread). save_version(text, prompt) -> Path saves the
        result as a version of the transcript and returns where (raises on failure)."""
        super().__init__(parent)
        self.setWindowTitle("Transform the transcript")
        self.resize(1000, 640)
        self.db, self.source, self.save_version = db, text, save_version
        self.sig = _Sig()
        self.sig.done.connect(self._done)
        self.current: dict | None = None
        self.result_for: dict | None = None
        self.running = False

        lay = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        lay.addWidget(split, 1)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.q = QLineEdit(placeholderText="Search prompts")
        self.q.textChanged.connect(self._fill)
        lv.addWidget(self.q)
        row = QHBoxLayout()
        self.type = QComboBox()
        self.type.addItem("All types", None)
        for k, v in transforms.TYPES.items():
            self.type.addItem(v, k)
        self.style = QComboBox()
        self.style.addItem("All styles", None)
        for k, v in transforms.STYLES.items():
            self.style.addItem(v, k)
        for c in (self.type, self.style):
            c.currentIndexChanged.connect(self._fill)
            row.addWidget(c)
        lv.addLayout(row)
        row = QHBoxLayout()
        self.featured = QCheckBox("Featured", checked=True)
        self.featured.setToolTip("A short list of everyday prompts; untick to see all of them")
        self.edited = QCheckBox("Edited by me")
        for c in (self.featured, self.edited):
            c.toggled.connect(self._fill)
            row.addWidget(c)
        row.addStretch(1)
        lv.addLayout(row)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._pick)
        lv.addWidget(self.list, 1)
        self.count = QLabel()
        self.count.setStyleSheet("color: gray;")
        lv.addWidget(self.count)
        split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel()
        self.title.setTextFormat(Qt.RichText)
        rv.addWidget(self.title)
        self.prompt = QPlainTextEdit()
        self.prompt.setToolTip("The instruction the model follows. Edit it to make it yours: your version "
                               "is kept, and the original can be restored.")
        self.prompt.textChanged.connect(self._sync_buttons)
        rv.addWidget(self.prompt, 2)
        row = QHBoxLayout()
        self.btn_keep = QPushButton("Save my version")
        self.btn_keep.clicked.connect(self._keep)
        self.btn_reset = QPushButton("Reset to original")
        self.btn_reset.clicked.connect(self._reset)
        row.addWidget(self.btn_keep)
        row.addWidget(self.btn_reset)
        row.addStretch(1)
        self.btn_run = QPushButton("Transform")
        self.btn_run.setDefault(True)
        self.btn_run.clicked.connect(self._run)
        row.addWidget(self.btn_run)
        rv.addLayout(row)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: gray;")
        rv.addWidget(self.note)
        self.out = QPlainTextEdit(readOnly=True, placeholderText="The result appears here. "
                                  "Your transcript is not changed.")
        rv.addWidget(self.out, 3)
        row = QHBoxLayout()
        self.btn_copy = QPushButton("Copy")
        self.btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.out.toPlainText()))
        self.btn_save = QPushButton("Save as a version")
        self.btn_save.setToolTip("Save the result beside the transcript (which is saved first if it isn't yet)")
        self.btn_save.clicked.connect(self._save)
        row.addStretch(1)
        row.addWidget(self.btn_copy)
        row.addWidget(self.btn_save)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        rv.addLayout(row)
        split.addWidget(right)
        split.setSizes([360, 640])

        self.model = transforms.ready()
        self._fill()
        self._sync_buttons()

    # -- list ---------------------------------------------------------------------------
    def _fill(self, *_):
        keep = self.current["id"] if self.current else None
        rows = transforms.search(self.db, self.q.text(), self.type.currentData(), self.style.currentData(),
                                 featured=self.featured.isChecked() and not self.q.text().strip(),
                                 edited=self.edited.isChecked())
        self.list.blockSignals(True)
        self.list.clear()
        pick = 0
        for i, p in enumerate(rows):
            tag = f"{transforms.TYPES[p['type']]} · {transforms.STYLES[p['style']]}"
            it = QListWidgetItem(f"{p['label']}{'  ✎' if p['edited'] else ''}\n{tag}")
            it.setData(Qt.UserRole, p["id"])
            it.setToolTip(p["prompt"][:400])
            self.list.addItem(it)
            if p["id"] == keep:
                pick = i
        self.list.blockSignals(False)
        self.count.setText(f"{len(rows)} prompt{'s' if len(rows) != 1 else ''}"
                           + (" (searching all)" if self.q.text().strip() and self.featured.isChecked() else ""))
        if rows:
            self.list.setCurrentRow(pick)
        else:
            self._show(None)

    def _pick(self, item, _prev=None):
        self._show(transforms.get(self.db, item.data(Qt.UserRole)) if item else None)

    def _show(self, p):
        self.current = p
        self.prompt.blockSignals(True)
        self.prompt.setPlainText(p["prompt"] if p else "")
        self.prompt.blockSignals(False)
        if p:
            bits = [transforms.TYPES[p["type"]], transforms.STYLES[p["style"]]]
            if p["language"] == "he":
                bits.append("writes Hebrew")
            if p["edited"]:
                bits.append("your version")
            self.title.setText(f"<b style='font-size:15px'>{p['label']}</b> "
                               f"<span style='color:gray'>{' · '.join(bits)}</span>")
        else:
            self.title.setText("<span style='color:gray'>No prompt matches</span>")
        self._sync_buttons()

    # -- edit ---------------------------------------------------------------------------
    def _sync_buttons(self):
        p = self.current
        text = self.prompt.toPlainText().strip()
        self.btn_keep.setEnabled(bool(p) and bool(text) and text != p["prompt"])
        self.btn_reset.setEnabled(bool(p) and p["edited"])
        self.btn_run.setEnabled(bool(p) and bool(text) and self.model is not None and not self.running
                                and bool(self.source.strip()))
        has = bool(self.out.toPlainText().strip()) and not self.running
        self.btn_copy.setEnabled(has)
        self.btn_save.setEnabled(has)
        if self.running:
            return
        if self.model is None:
            self.note.setText("To run a transform, download the transform model in Models → Utilities → "
                              "Post-processing. You can browse and edit prompts without it.")
        elif p and p["stale"]:
            self.note.setText("The shipped version of this prompt has changed since you edited it. "
                              "Reset to original to use the new one.")
        elif self.prompt.toPlainText().strip() != (p or {}).get("prompt", "").strip():
            self.note.setText("Unsaved change: Transform uses the text as it is now; Save my version keeps it.")
        else:
            self.note.setText("")

    def _keep(self):
        if not self.current:
            return
        transforms.edit(self.db, self.current["id"], self.prompt.toPlainText())
        self._fill()

    def _reset(self):
        if not self.current:
            return
        if QMessageBox.question(self, "Reset prompt", f"Go back to the original “{self.current['label']}” "
                                "prompt? Your version is deleted.") != QMessageBox.Yes:
            return
        transforms.reset(self.db, self.current["id"])
        self._fill()

    # -- run ----------------------------------------------------------------------------
    def _run(self):
        if not self.current or self.running:
            return
        p = dict(self.current, prompt=self.prompt.toPlainText().strip())
        self.running = True
        self.out.clear()
        self.note.setText(f"Transforming with {cleanup.label(self.model)}… the first run loads the model.")
        self._sync_buttons()
        text = self.source

        def work():
            try:
                self.sig.done.emit(p, transforms.run(text, p))
            except Exception as e:
                self.sig.done.emit(p, e)
        threading.Thread(target=work, daemon=True, name="transform").start()

    def _done(self, p, result):
        self.running = False
        if isinstance(result, Exception):
            self.result_for = None
            self.note.setText(f"Couldn't transform: {result}")
        else:
            self.result_for = p
            self.out.setPlainText(result)
            self.note.setText(f"“{p['label']}” with {cleanup.label(self.model)}.")
        self._sync_buttons()

    def _save(self):
        if not self.result_for:
            return
        try:
            path = self.save_version(self.out.toPlainText(), self.result_for)
        except Exception as e:
            QMessageBox.warning(self, "Couldn't save", str(e))
            return
        self.note.setText(f"Saved {path}")
