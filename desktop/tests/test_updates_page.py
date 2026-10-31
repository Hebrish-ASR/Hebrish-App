"""Updates page (2026-10-31): every baked entry, newest first; extra keys such as `platforms` are ignored."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from hebrish.ui import about, window  # noqa: E402
from hebrish.ui.updates import UpdatesPage, _newest_first  # noqa: E402

_app = QApplication.instance() or QApplication([])


def test_newest_first_tolerates_platforms_and_missing_dates():
    got = _newest_first([{"date": "2026-10-01", "platforms": ["desktop", "models", "site"]},
                         {"title": "undated"}, {"date": "2026-10-30"}, "not a dict"])
    assert [e.get("date") for e in got] == ["2026-10-30", "2026-10-01", None]


def test_page_shows_every_baked_entry():
    page = UpdatesPage(window.card, window.muted)
    entries = about.load_updates()["entries"]
    assert len(page.entries) == len(entries)
    for e in entries:
        assert about.html.escape(e["title"]) in page.updates_label.text()
