"""Updates page (2026-10-31, Daniel: an Updates panel on desktop, like Android's Updates screen).

Every entry baked into this build (data/updates.json, a copy of shared/updates.json written by
scripts/bake_updates.py), newest first: date · tag, title and summary, then the full changelog
link. Opened from the header's Updates button, like Diagnostics and About. Up to 1.013 this was a
"What's new" card on About showing five entries with "Show all".

Entries may carry extra keys (e.g. a `platforms` list); they are ignored here.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from .about import CHANGELOG, _rich, load_updates, updates_html


def _newest_first(entries: list) -> list:
    """Sorted by date, newest first; entries without a date keep their place at the end."""
    dated = [e for e in entries if isinstance(e, dict) and e.get("date")]
    rest = [e for e in entries if isinstance(e, dict) and not e.get("date")]
    return sorted(dated, key=lambda e: str(e["date"]), reverse=True) + rest


class UpdatesPage(QScrollArea):
    """card(title) and muted(text) are window.py's helpers (passed in: window imports us)."""

    def __init__(self, card, muted):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(12)
        doc = load_updates()
        self.entries = _newest_first(doc["entries"])
        box, b = card("Updates")
        if not self.entries:
            b.addWidget(_rich(f"This version has no list of changes. See <a href='{CHANGELOG}'>hebrish.app/changelog</a>."))
        else:
            b.addWidget(_rich(f"<small style='color:gray'>Changes to Hebrish (apps, models and site), up to "
                              f"{doc.get('built', '')} when this version was built.</small>"))
            self.updates_label = _rich(updates_html(self.entries))
            b.addWidget(self.updates_label)
            b.addWidget(_rich(f"<a href='{CHANGELOG}'>Full changelog on hebrish.app</a>"))
        lay.addWidget(box)
        lay.addStretch(1)
        self.setWidget(page)
