"""Microphone pickers and Settings' Microphones card (R-2026-10-25-2; hebrish.mics).

The Dictate and Transcription tabs' mic boxes offer System default, Preferred order, then each
connected mic by its alias. The card lists every mic the app has seen, in the preferred order,
with an alias, a type and whether it is connected now."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFrame, QHBoxLayout, QHeaderView,
                               QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from .. import mics


def fill_combo(combo: QComboBox, cfg, setting: str) -> list[mics.Mic]:
    """Fill a mic box for config `setting` and select its value; returns the connected mics.
    Mics seen here are remembered too."""
    found = mics.list_mics()
    known = cfg["mics"]
    if mics.remember(known, found):
        cfg.set("mics", known)
    cur = cfg[setting]
    combo.blockSignals(True)
    combo.clear()
    combo.addItem("System default", "")
    combo.addItem("Preferred order (Settings → Microphones)", mics.PREFERRED)
    for m in found:
        if m.device:
            combo.addItem(mics.name(known.get(m.key, {"label": m.label})), m.device)
    if cur and combo.findData(cur) < 0:
        combo.addItem(f"{cur} (not found)", cur)
    combo.setCurrentIndex(max(0, combo.findData(cur)))
    combo.blockSignals(False)
    return found


def in_use(cfg, setting: str = "audio_device") -> str:
    """The "In use:" text for a mic setting."""
    from .. import audio
    dev = cfg[setting]
    if dev == mics.PREFERRED:
        _, name = mics.resolve(cfg, setting)
        return f"{name} (preferred order)" if name else "System default (no mic in your order is connected)"
    if dev:
        known = next((e for e in cfg["mics"].values() if e.get("device") == dev), None)
        return mics.name(known) if known else dev
    real = audio.default_input_name()
    return f"{real} (system default)" if real else "System default"


class MicsCard(QFrame):
    """Settings → Microphones. `changed` is called after anything that changes what a mic box
    shows (alias, order, the Preferred order switch)."""

    COLS = ["", "Name", "Type", "Detected as", "Status"]

    def __init__(self, cfg, changed=None):
        super().__init__(objectName="card")
        self.cfg, self.changed = cfg, changed or (lambda: None)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(8)
        lay.addWidget(QLabel("Microphones", objectName="cardTitle"))
        note = QLabel("Every microphone Hebrish has seen on this computer. Give each a name and a "
                      "type, and put them in the order you'd like them used: with the microphone "
                      "set to <b>Preferred order</b>, each take uses the first one here that is "
                      "connected, and the system default when none is.", objectName="muted")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.use = QCheckBox("Dictate with the first connected mic in this order",
                             checked=cfg["audio_device"] == mics.PREFERRED)
        self.use.toggled.connect(self._on_use)
        lay.addWidget(self.use)

        self.table = t = QTableWidget(0, len(self.COLS))
        t.setHorizontalHeaderLabels(self.COLS)
        t.verticalHeader().hide()
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                          | QAbstractItemView.SelectedClicked)
        h = t.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.Stretch)
        t.setMinimumHeight(160)
        t.itemChanged.connect(self._on_item)
        lay.addWidget(t)

        row = QHBoxLayout()
        self.status = QLabel(objectName="muted")
        row.addWidget(self.status, 1)
        for text, tip, slot in (("↑", "Use this one earlier", lambda: self._move(-1)),
                                ("↓", "Use this one later", lambda: self._move(1)),
                                ("Forget", "Remove it from the list (it comes back when next seen)", self._forget),
                                ("Rescan", "Look for microphones again", self.refresh)):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            row.addWidget(b)
        lay.addLayout(row)
        self.refresh()

    # -- data ------------------------------------------------------------------------
    def _keys(self) -> list[str]:
        return mics.ordered(self.cfg["mics"], self.cfg["mic_order"])

    def refresh(self):
        found = mics.list_mics()
        known = self.cfg["mics"]
        if mics.remember(known, found):
            self.cfg.set("mics", known)
        here = {m.key for m in found if m.device}
        self._filling = True
        t = self.table
        keys = self._keys()
        t.setRowCount(len(keys))
        for i, key in enumerate(keys):
            e = known[key]
            num = QTableWidgetItem(str(i + 1))
            num.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            t.setItem(i, 0, num)
            alias = QTableWidgetItem(e.get("alias", ""))
            alias.setToolTip(f"Double-click to name it. Empty: “{e.get('label', '')}”")
            alias.setData(Qt.UserRole, key)
            if not e.get("alias"):
                alias.setText(e.get("label", ""))
                alias.setForeground(t.palette().placeholderText())
            t.setItem(i, 1, alias)
            box = QComboBox()
            for val, label in mics.TYPES:
                box.addItem(label, val)
            box.setCurrentIndex(max(0, box.findData(e.get("type", ""))))
            box.currentIndexChanged.connect(lambda _i, k=key, b=box: self._set(k, "type", b.currentData()))
            t.setCellWidget(i, 2, box)
            ids = ":".join(x for x in (e.get("vendor_id"), e.get("product_id")) if x)
            det = QTableWidgetItem(" ".join(x for x in ((e.get("bus") or "").upper(), ids) if x) or e.get("label", ""))
            det.setToolTip(f"{e.get('label', '')}\nKey {key}" + (f"\nSerial {e['serial']}" if e.get("serial") else ""))
            det.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            t.setItem(i, 3, det)
            st = QTableWidgetItem("Connected" if key in here else f"Last seen {e.get('last_seen', '?')}")
            st.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            t.setItem(i, 4, st)
        self._filling = False
        n = len(keys)
        self.status.setText(f"{len(here)} connected, {n} known." if n else "No microphones found.")

    def _set(self, key: str, field: str, value):
        known = self.cfg["mics"]
        if key in known and known[key].get(field) != value:
            known[key][field] = value
            self.cfg.set("mics", known)
            self.changed()

    def _on_item(self, item: QTableWidgetItem):
        if self._filling or item.column() != 1:
            return
        key = item.data(Qt.UserRole)
        label = self.cfg["mics"].get(key, {}).get("label", "")
        text = item.text().strip()
        self._set(key, "alias", "" if text == label else text)
        self.refresh()

    def _on_use(self, on: bool):
        self.cfg.set("audio_device", mics.PREFERRED if on else "")
        self.changed()

    def sync(self):
        """The Dictate tab's mic box changed."""
        self.use.blockSignals(True)
        self.use.setChecked(self.cfg["audio_device"] == mics.PREFERRED)
        self.use.blockSignals(False)

    def _row(self) -> int:
        rows = {i.row() for i in self.table.selectedIndexes()}
        return rows.pop() if rows else -1

    def _move(self, step: int):
        i, keys = self._row(), self._keys()
        j = i + step
        if i < 0 or not 0 <= j < len(keys):
            return
        keys[i], keys[j] = keys[j], keys[i]
        self.cfg.set("mic_order", keys)
        self.refresh()
        self.table.selectRow(j)
        self.changed()

    def _forget(self):
        i = self._row()
        if i < 0:
            return
        key = self._keys()[i]
        if self.table.item(i, 4).text() == "Connected":
            self.status.setText("Unplug it first: a connected mic comes straight back.")
            return
        known = self.cfg["mics"]
        known.pop(key, None)
        self.cfg.set("mics", known)
        self.cfg.set("mic_order", [k for k in self.cfg["mic_order"] if k != key])
        self.refresh()
        self.changed()
