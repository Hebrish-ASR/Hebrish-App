"""Help me choose (0.6.0): a few questions about the device and what matters more, answered with a
variant from the catalogue (model_store.recommend). The GPU and its VRAM are detected where that
is cheap (nvidia-smi, Linux sysfs) and can be corrected by hand.

A recommended variant this app can't run yet is still named, with where it runs instead
("use via llama.cpp, see the card" for Qwen3-ASR), followed by the best one this app can run."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QLabel, QPushButton, QVBoxLayout)

from .. import model_store

DEVICES = [("desktop", "This computer"), ("phone", "A phone"), ("wearable", "A watch or a wearable")]
GPUS = [("none", "None, or built-in graphics only"), ("nvidia", "NVIDIA"), ("amd", "AMD"),
        ("intel", "Intel Arc")]
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
        intro = QLabel("Four questions. The answer comes from the speed and accuracy tiers in the "
                       "model list, which are estimates, not benchmark results.")
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
        self.gpu.setCurrentIndex(max(0, self.gpu.findData(vendor)))
        self.vram.setValue(gb)
        self.detected.setText(f"Detected: {dict(GPUS)[vendor]}" + (f", {gb:g} GB" if gb else "")
                              + ". Change it if that's wrong." if vendor != "none"
                              else "No separate GPU detected. Change it if you have one.")

    def _update(self, *_):
        device = self.device.currentData()
        desktop = device == "desktop"
        for w in (self.gpu, self.vram):
            w.setEnabled(desktop)
        picks = model_store.recommend(device, self.gpu.currentData() if desktop else "none",
                                      self.vram.value() if desktop else 0, self.priority.currentData(),
                                      self.live.isChecked())
        self._target = None
        self.act.hide()
        if not picks:
            self.answer.setText("Nothing in the catalogue fits that yet.")
            return
        best = picks[0]
        html = [f"<b style='font-size:15px'>{best.name}</b> <small style='color:gray'>{best.base_model}</small>"
                f"<br>{best.recommendation}<br><small>{best.hardware}</small>"]
        if best.card:
            html.append(f"<br><a href='{best.card}'>Model card</a>")
        if not desktop:
            html.append("<br><br>On a phone, use it in the Hebrish Android app"
                        + (" once it's there." if not best.available and best.supported else "."))
        elif not best.supported:
            html.append(f"<br><br><b>{where_else(best)}</b>")
        elif not best.available:
            html.append("<br><br>Coming soon to this app.")
        here = next((v for v in picks if v.available), None) if desktop else None
        if here and here is not best:
            html.append(f"<br><br>In this app, the best fit is <b>{here.name}</b>: {here.recommendation}")
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
