"""Help me choose (0.6.0): a few questions about the device and what matters more, answered by the
catalogue's `chooser.rules`, the same decision list as hebrish.app/models/choose
(model_store.recommend). The GPU and its VRAM are detected where that is cheap (nvidia-smi,
Linux sysfs) and can be corrected by hand.

A pick this app can't run yet is still named, with how to run it (the rule's `how`; "use via
llama.cpp, see the card" for Qwen3-ASR), followed by the best one this app can run."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QLabel, QPushButton, QVBoxLayout)

from .. import model_store

DEVICES = [("computer", "This computer"), ("phone", "A phone"), ("wearable", "A watch or a wearable")]
# The chooser's gpu values; Intel graphics count as none (no rule uses them).
GPUS = [("none", "None, built-in or Intel graphics"), ("nvidia", "NVIDIA"), ("amd", "AMD")]
PRIORITIES = [("balanced", "A balance of both"), ("speed", "Speed: text as fast as possible"),
              ("accuracy", "Accuracy: fewest mistakes")]


def where_else(v) -> str:
    if v.engine == "qwen3_asr":
        return "Use via llama.cpp: see the model card."
    return v.runs_on or "Not in this app yet: see the model card."


class ChooseDialog(QDialog):
    def __init__(self, parent, ctl):
        super().__init__(parent)
        self.ctl = ctl
        self.setWindowTitle("Help me choose a model")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        intro = QLabel("A few questions. The answer follows the same rules as hebrish.app/models/choose; "
                       "speed and accuracy are estimates, not benchmark results.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        form = QFormLayout()
        self.device = self._combo(DEVICES)
        form.addRow("Where will you dictate?", self.device)
        self.gpu = self._combo(GPUS)
        form.addRow("Graphics card (GPU)", self.gpu)
        self.vram = QDoubleSpinBox(minimum=0, maximum=192, decimals=0, suffix=" GB")
        self.vram.valueChanged.connect(self._update)
        form.addRow("Its memory (VRAM)", self.vram)
        self.detected = QLabel()
        self.detected.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow("", self.detected)
        self.priority = self._combo(PRIORITIES)
        form.addRow("What matters more?", self.priority)
        self.live = QCheckBox("I want to see the words while I'm still talking")
        self.live.toggled.connect(self._update)
        form.addRow("", self.live)
        lay.addLayout(form)
        self.answer = QLabel()
        self.answer.setWordWrap(True)
        self.answer.setTextFormat(Qt.RichText)
        self.answer.setOpenExternalLinks(True)
        self.answer.setStyleSheet("padding: 10px; border: 1px solid palette(midlight); border-radius: 8px;")
        lay.addWidget(self.answer)
        self.act = QPushButton(objectName="primary")
        self.act.clicked.connect(self._act)
        self.act.hide()
        lay.addWidget(self.act, 0, Qt.AlignLeft)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self._target = None
        self._detect()
        self._update()

    def _combo(self, options):
        c = QComboBox()
        for key, label in options:
            c.addItem(label, key)
        c.currentIndexChanged.connect(self._update)
        return c

    def _detect(self):
        vendor, gb = model_store.detect_gpu()
        if vendor not in dict(GPUS):
            vendor, gb = "none", 0.0
        self.gpu.setCurrentIndex(max(0, self.gpu.findData(vendor)))
        self.vram.setValue(gb)
        self.detected.setText(f"Detected: {dict(GPUS)[vendor]}" + (f", {gb:g} GB" if gb else "")
                              + ". Change it if that's wrong." if vendor != "none"
                              else "No separate GPU detected. Change it if you have one.")

    def _update(self, *_):
        device = self.device.currentData()
        here_too = device == "computer"
        for w in (self.gpu, self.vram):
            w.setEnabled(here_too)
        r = model_store.recommend(device, self.gpu.currentData() if here_too else "none",
                                  self.vram.value() if here_too else 0, self.priority.currentData(),
                                  self.live.isChecked())
        self._target = None
        self.act.hide()
        best = r["pick"]
        if best is None:
            self.answer.setText("Nothing in the catalogue fits that yet.")
            return
        base = f" <small style='color:gray'>Base model: {best.base_label}</small>" if best.base_label else ""
        html = [f"<b style='font-size:15px'>{best.name}</b>{base}"]
        if r.get("reason"):
            html.append(f"<br>{r['reason']}")
        html.append(f"<br><small>{best.hardware}</small>")
        if best.card:
            html.append(f" <small><a href='{best.card}'>Model card</a></small>")
        if r.get("how"):
            html.append(f"<br><br><b>How:</b> {r['how']}")
        if here_too and not best.supported:
            html.append("<br><b>Not in this app yet.</b>" if r.get("how") else f"<br><b>{where_else(best)}</b>")
        elif here_too and not best.available:
            html.append("<br>Not published yet.")
        if r.get("note"):
            html.append(f"<br><i>{r['note']}</i>")
        runner = r.get("runner_up")
        if runner:
            html.append(f"<br><br>Also good: <b>{runner.name}</b>"
                        + (f", {r['runner_how']}" if r.get("runner_how") else "") + ".")
        here = r["here"] if here_too else None
        if here and here is not best:
            html.append(f"<br><br>In this app, the best fit is <b>{here.name}</b>.")
        if here:
            self._target = here
            on_disk = bool(model_store.installed(here.id))
            in_use = on_disk and here.id == model_store.current_id()
            self.act.setText("Already in use" if in_use else
                             (f"Switch to {here.name}" if on_disk else f"Download {here.name}"))
            self.act.setEnabled(not in_use)
            self.act.show()
        self.answer.setText("".join(html))

    def _act(self):
        v = self._target
        if not v:
            return
        if model_store.installed(v.id):
            self.ctl.use_model(v.id)
        else:
            self.ctl.download_model(v.id)
        self.accept()
