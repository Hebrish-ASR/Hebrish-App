"""The Transcription tab's Notepad (1.032): formatting written out as Markdown, transcripts added
unformatted without losing earlier formatting, Voice Typing into it, and Stop transcribing.

Off-screen Qt; nothing opens the mic."""

import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from hebrish.ui import notepad  # noqa: E402
from hebrish.ui.notepad import BULLET, NUMBERED, Notepad  # noqa: E402
from tests.test_transcribe_controls import make  # noqa: E402,F401

app = QApplication.instance() or QApplication([])


def _select(n: Notepad, start: int, end: int):
    c = n.textCursor()
    c.setPosition(start)
    c.setPosition(end, QTextCursor.KeepAnchor)
    n.setTextCursor(c)


def test_plain_text_is_its_own_markdown():
    n = Notepad()
    n.replace_all("First paragraph.\n\nSecond one.")
    assert n.markdown() == n.toPlainText() == "First paragraph.\n\nSecond one."


def test_bold_italic_highlight_heading_and_lists():
    n = Notepad()
    n.replace_all("Title\n\nsay hello world\n\none\ntwo\n\nfirst\nsecond")
    _select(n, 0, 0)
    n.set_heading(1)
    _select(n, 11, 16)                        # "hello"
    n.toggle_bold()
    _select(n, 17, 22)                        # "world"
    n.toggle_italic()
    n.toggle_highlight()
    _select(n, 24, 31)                        # one, two
    n.toggle_list(BULLET)
    _select(n, 33, 45)                        # first, second
    n.toggle_list(NUMBERED)
    assert n.markdown() == ("# Title\n\nsay **hello** ==*world*==\n\n- one\n- two\n\n"
                            "1. first\n2. second")
    assert n.toPlainText() == "Title\n\nsay hello world\n\none\ntwo\n\nfirst\nsecond"


def test_toggles_undo_and_clear_formatting():
    n = Notepad()
    n.replace_all("a word here")
    _select(n, 2, 6)
    n.toggle_bold()
    assert n.markdown() == "a **word** here"
    n.toggle_bold()
    assert n.markdown() == "a word here"
    n.toggle_list(BULLET)
    n.toggle_list(BULLET)
    assert n.markdown() == "a word here"
    n.set_heading(2)
    assert n.markdown() == "## a word here"
    _select(n, 0, 0)
    n.clear_formatting()
    assert n.markdown() == "a word here"


def test_bold_spaces_stay_outside_the_marks():
    n = Notepad()
    n.replace_all("one two")
    _select(n, 3, 7)                          # " two"
    n.toggle_bold()
    assert n.markdown() == "one **two**"


def test_append_keeps_earlier_formatting_and_is_unformatted():
    n = Notepad()
    n.replace_all("Notes\n\nbold end")
    _select(n, 0, 0)
    n.set_heading(2)
    _select(n, 12, 15)
    n.toggle_bold()
    start = n.append("next take\n\nits second paragraph")
    assert n.toPlainText()[start:] == "next take\n\nits second paragraph"
    assert n.markdown() == "## Notes\n\nbold **end**\n\nnext take\n\nits second paragraph"


def test_append_after_a_list_is_not_a_list_item():
    n = Notepad()
    n.replace_all("item")
    n.toggle_list(BULLET)
    n.append("more")
    assert n.markdown() == "- item\n\nmore"


def test_replace_all_drops_a_heading():
    n = Notepad()
    n.replace_all("old")
    n.set_heading(1)
    n.replace_all("new")
    assert n.markdown() == "new"


def test_dictation_goes_in_at_the_cursor_with_spaces():
    n = Notepad()
    n.replace_all("Hello world")
    _select(n, 5, 5)
    n.insert_at_cursor("there")
    assert n.toPlainText() == "Hello there world"


def test_paste_is_plain_text():
    from PySide6.QtCore import QMimeData
    n = Notepad()
    m = QMimeData()
    m.setHtml("<b>bold</b>")
    m.setText("bold")
    n.edit.insertFromMimeData(m)
    assert n.markdown() == "bold"


def test_page_is_white_in_any_theme():
    n = Notepad()
    assert n.edit.palette().color(n.edit.palette().ColorRole.Base).name() == notepad.PAGE


# -- the Transcription page -------------------------------------------------------------------
def test_stop_transcribes(make, monkeypatch, tmp_path):
    _, page, _ = make()
    wav = tmp_path / "take.wav"
    wav.write_bytes(b"")
    page.tape.stop = lambda: (setattr(page.tape, "active", False), wav)[1]
    went = []
    monkeypatch.setattr(page, "_transcribe_path", lambda p: went.append(p))
    page.btn_rec.click()
    assert not page.btn_go.isVisible()       # Transcribe only for a held recording
    page.btn_stop.click()
    assert went == [wav]


def test_held_recording_shows_transcribe(make, tmp_path):
    _, page, _ = make()
    page._held = tmp_path / "held.wav"
    page._held.write_bytes(b"")
    page._sync()
    assert page.btn_go.isVisible() and page.btn_go.isEnabled()


def test_focus_on_the_tab_routes_voice_typing(make):
    host, page, _ = make()
    host.activateWindow()
    page.text.edit.setFocus()
    app.processEvents()
    assert page.box_focused
    page.insert_dictation("dictated words")
    assert "dictated words" in page.text.toPlainText()


def test_save_writes_markdown(make, monkeypatch, tmp_path):
    _, page, cfg = make()
    page.text.replace_all("a bold move")
    _select(page.text, 2, 6)
    page.text.toggle_bold()
    saved = []
    from hebrish.ui import transcribe
    monkeypatch.setattr(transcribe.transcripts, "save",
                        lambda text, folder, **kw: saved.append(text) or Path(tmp_path / "t.md"))
    page._save_now(page.text.markdown())
    assert saved == ["a **bold** move"]
