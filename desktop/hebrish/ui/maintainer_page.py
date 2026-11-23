"""Maintainer tab (Settings window, 1.043, Daniel 2026-11-23): maintainer mode's switch, how much
disk its audio uses now, and its caps, on one page.

Daniel, 2026-11-23: "a maintainer page that shows current storage used in gigabytes. You can change
the capacity and we can start recording." The switch used to sit alone under the History switch on
the Settings tab, with the caps (14 days, 3 GB) fixed in its tooltip. The caps are the existing
config keys `maintainer_max_gb` and `maintainer_keep_days`, applied by maintainer.prune() after
every saved take; lowering the capacity here prunes at once.

Usage is measured from the folder itself (maintainer.usage()), never a running count, and refreshed
every 5 s while the page is shown."""

import os
import subprocess
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .. import maintainer

GB = 1024 ** 3


def gb(n: int) -> str:
    return f"{n / GB:.2f} GB"


class MaintainerPage(QScrollArea):
    def __init__(self, ctl, card, muted):
        super().__init__()
        self.ctl, self.cfg = ctl, ctl.cfg
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)

        box, b = card("Maintainer mode")
        b.addWidget(muted("For improving Hebrish: each Voice Typing take's recording (FLAC, about 1 MB "
                          "a minute) and how it was cut and joined are kept beside its History row, so "
                          "real dictation can be replayed, annotated and measured. Stays on this "
                          "computer. Needs the history on."))
        self.switch = QCheckBox("Keep each take's audio and seam log", checked=bool(self.cfg["maintainer_mode"]))
        self.switch.toggled.connect(self._toggle)
        b.addWidget(self.switch)
        lay.addWidget(box)

        box, b = card("Storage")
        self.used = QLabel()
        self.used.setStyleSheet("font-size: 20px; font-weight: 600;")
        b.addWidget(self.used)
        self.bar = QProgressBar(textVisible=False, maximum=1000)
        b.addWidget(self.bar)
        self.detail = muted("")
        b.addWidget(self.detail)
        form = QFormLayout()
        self.cap = QDoubleSpinBox(decimals=1, minimum=0.5, maximum=500.0, singleStep=0.5, suffix=" GB")
        self.cap.setValue(float(self.cfg["maintainer_max_gb"] or maintainer.MAX_GB))
        self.cap.setToolTip("When the folder grows past this, the oldest takes are deleted first.")
        self.cap.valueChanged.connect(lambda v: self._set_cap("maintainer_max_gb", float(v)))
        form.addRow("Capacity", self.cap)
        self.days = QSpinBox(minimum=1, maximum=3650, suffix=" days")
        self.days.setValue(int(self.cfg["maintainer_keep_days"] or maintainer.KEEP_DAYS))
        self.days.setToolTip("Day folders older than this are deleted, whatever the capacity.")
        self.days.valueChanged.connect(lambda v: self._set_cap("maintainer_keep_days", int(v)))
        form.addRow("Keep for", self.days)
        b.addLayout(form)
        row = QHBoxLayout()
        self.path = muted(str(maintainer.folder()))
        self.path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.path, 1)
        opn = QPushButton("Open folder")
        opn.clicked.connect(self._open)
        row.addWidget(opn)
        b.addLayout(row)
        lay.addWidget(box)
        lay.addStretch(1)
        self.setWidget(page)

        self._timer = QTimer(self, interval=5000, timeout=self.refresh)
        self.refresh()

    def _toggle(self, on: bool):
        self.cfg.set("maintainer_mode", on)
        self.refresh()

    def _set_cap(self, key, value):
        self.cfg.set(key, value)
        maintainer.prune(self.cfg["maintainer_keep_days"] or maintainer.KEEP_DAYS,
                         self.cfg["maintainer_max_gb"] or maintainer.MAX_GB)
        self.refresh()

    def _open(self):
        d = maintainer.folder()
        d.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(str(d))                 # noqa: S606 (Windows only)
        else:
            subprocess.Popen(["xdg-open", str(d)])

    def refresh(self):
        if self.switch.isChecked() != bool(self.cfg["maintainer_mode"]):
            self.switch.blockSignals(True)
            self.switch.setChecked(bool(self.cfg["maintainer_mode"]))
            self.switch.blockSignals(False)
        u = maintainer.usage()
        cap = float(self.cfg["maintainer_max_gb"] or maintainer.MAX_GB) * GB
        self.used.setText(f"{gb(u['bytes'])} of {cap / GB:.1f} GB")
        self.bar.setValue(min(1000, int(1000 * u["bytes"] / cap)) if cap else 0)
        if u["takes"]:
            mins = u["audio_s"] / 60
            m = f"{mins:.1f}" if mins < 10 else f"{mins:,.0f}"
            self.detail.setText(f"{u['takes']:,} take{'' if u['takes'] == 1 else 's'}, {m} min of audio, "
                                f"{u['first_day']} to {u['last_day']}"
                                + ("" if self.cfg["maintainer_mode"] else ". Maintainer mode is off: nothing new is kept."))
        else:
            self.detail.setText("Nothing kept yet." if self.cfg["maintainer_mode"]
                                else "Nothing kept. Turn maintainer mode on to start.")

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()
        self._timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()
