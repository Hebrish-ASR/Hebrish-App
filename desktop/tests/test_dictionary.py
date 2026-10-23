"""Personal dictionary: the shared test set (../shared/dictionary-cases.json) and the file."""

import json
from pathlib import Path

import pytest

from hebrish import dictionary

CASES = json.loads((Path(__file__).resolve().parents[2] / "shared" / "dictionary-cases.json").read_text(encoding="utf-8"))
FIX = dictionary.compile(CASES["entries"])


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda c: c["in"] or "empty")
def test_shared_cases(case):
    assert FIX(case["in"]) == case["out"]


def test_no_entries_is_identity():
    assert dictionary.compile([]) is str
    assert dictionary.compile([{"word": " ", "heard": ["x"]}]) is str


def test_round_trip(tmp_path):
    p = tmp_path / "dictionary.json"
    dictionary.save([{"word": " Hebrish ", "heard": ["hebrew ish", " ", 3]}, {"word": "", "heard": []}], p)
    assert json.loads(p.read_text(encoding="utf-8"))["schema"] == 1
    assert dictionary.load(p) == [{"word": "Hebrish", "heard": ["hebrew ish"]}]


def test_missing_or_bad_file(tmp_path):
    assert dictionary.load(tmp_path / "none.json") == []
    (tmp_path / "bad.json").write_text("[1, 2]", encoding="utf-8")
    assert dictionary.load(tmp_path / "bad.json") == []


@pytest.fixture
def saved_words():
    dictionary.save([{"word": "Hebrish", "heard": ["hebrew ish"]}])
    yield
    dictionary.PATH.unlink(missing_ok=True)


def test_worker_applies_it_before_all_caps(saved_words):
    # 0.8.0: after the seam rules, before ALL CAPS; History (the transcript) gets the dictionary's
    # spelling in normal case
    from test_live import _run_worker
    pastes, text = _run_worker(["I use hebrew ish.", "So it works.", ""],
                               [(0.7, False), (0.7, False), (None, True)], {"all_caps": True})
    assert pastes == ["I USE HEBRISH", " SO IT WORKS", ". "]
    assert text == "I use Hebrish so it works."


def test_dictionary_tab(saved_words):
    pytest.importorskip("PySide6")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QWidget
    from hebrish.ui.window import MainWindow
    app = QApplication.instance() or QApplication([])  # noqa: F841

    class Page(QWidget):
        _dictionary_page, _dict_show = MainWindow._dictionary_page, MainWindow._dict_show
        _dict_add, _dict_remove = MainWindow._dict_add, MainWindow._dict_remove
        toast = lambda self, text="": None  # noqa: E731

    p = Page()
    page = p._dictionary_page()      # keep it: its children are the table and fields  # noqa: F841
    assert p.dict_table.rowCount() == 1
    p.dict_word.setText(" GitHub ")
    p.dict_heard.setText("git hub, , get hub")
    p._dict_add()
    assert dictionary.load() == [{"word": "Hebrish", "heard": ["hebrew ish"]},
                                 {"word": "GitHub", "heard": ["git hub", "get hub"]}]
    assert p.dict_table.item(1, 1).text() == "git hub, get hub"
    p.dict_table.selectRow(0)
    p._dict_remove()
    assert [e["word"] for e in dictionary.load()] == ["GitHub"]
