"""The one-time licence notice and its wording (2026-11-05)."""

import pytest


def test_wording_matches_the_licence_policy():
    pytest.importorskip("PySide6")
    from hebrish.ui import licence
    for phrase in ("CC BY-NC 4.0", "small non-profits", "health funds and public bodies", "access@hebrish.app", "MIT"):
        assert phrase in licence.LICENCE_HTML
    assert "non-profit use" not in licence.LICENCE_HTML      # replaced by the 2026-11-02 tiers


def test_icons_and_corn_ship_with_the_app():
    pytest.importorskip("PySide6")
    from hebrish.ui import licence
    for path in ("corn/corn.png", "licence/cc.png", "licence/by.png", "licence/nc.png"):
        assert (licence.DATA / path).is_file()


def test_notice_shows_once(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from hebrish.ui import licence
    state = tmp_path / "state.json"
    monkeypatch.setattr(licence, "STATE_PATH", state)
    made = []
    monkeypatch.setattr(licence, "NoticeOnFirstShow", made.append)
    licence.install("window")
    assert made == ["window"]
    licence.mark_seen()
    licence.install("window")
    assert made == ["window"]
