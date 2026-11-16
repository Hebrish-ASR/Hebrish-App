"""Hebrew switching (2026-11-16): which model a take uses (Controller.take_language), the input
language setting, and what History records."""

from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from hebrish import keyboard_layout, model_store  # noqa: E402
from hebrish.ui.app import Controller  # noqa: E402

HE = model_store.language_model("he")
HE_DIR = Path("/models/hebrew/v1")


class Ctl(Controller):
    def __init__(self, setting="auto", installed=True, loaded=True):
        from PySide6.QtCore import QObject
        QObject.__init__(self)
        self.cfg = {"input_language": setting}
        self.state = "idle"
        self._take_info, self._he_pending, self._he_loading, self.last_lang = {}, False, False, None
        self.he_engine = SimpleNamespace(loaded_dir=HE_DIR if loaded else None, streaming=True)
        self.engine = SimpleNamespace(loaded_dir=Path("/models/main"), streaming=False)
        self._installed = installed
        self.loads = 0
        self.shown = []
        self.win = SimpleNamespace(show_language=self.shown.append)

    def hebrew_install(self):
        man = SimpleNamespace(model=HE.id, version="v1", revision="r", full_label="Hebrew v1")
        return HE, ((HE_DIR, man) if self._installed else None)

    def load_hebrew(self):
        self.loads += 1


def detected(lang):
    return lambda: keyboard_layout.Detected(lang, "kde", "il" if lang == "he" else "gb")


def test_hebrew_keyboard_and_model_installed_uses_the_hebrew_model():
    c = Ctl()
    i = c.take_language(detected("he"))
    assert i["lang"] == "he" and i["engine"] is c.he_engine and i["source"] == "keyboard"
    assert i["method"] == "kde" and i["layout"] == "il" and i["streaming"] is True
    assert c.shown == [i] and c.last_lang is i


def test_other_layouts_and_unknown_are_english():
    for lang in ("en", "unknown"):
        i = Ctl().take_language(detected(lang))
        assert i["lang"] == "en" and i["engine"] is None and i["wanted"] == "en"


def test_manual_setting_ignores_the_keyboard():
    def boom():
        raise AssertionError("keyboard asked")
    assert Ctl("en").take_language(boom)["lang"] == "en"
    i = Ctl("he").take_language(boom)
    assert i["lang"] == "he" and i["source"] == "manual"


def test_hebrew_wanted_but_not_downloaded_falls_back_with_a_hint():
    i = Ctl("he", installed=False).take_language()
    assert i["lang"] == "en" and i["wanted"] == "he" and i["missing"] is True and i["engine"] is None


def test_installed_but_not_loaded_starts_the_load():
    c = Ctl("he", loaded=False)
    c._he_loading = False
    i = c.take_language()
    assert c.loads == 1
    assert i["lang"] == "en"           # the stub load didn't start one: the main model takes it
    c2 = Ctl("he", loaded=False)
    c2.load_hebrew = lambda: setattr(c2, "_he_loading", True)
    assert c2.take_language()["lang"] == "he"     # loading: the take waits for it in the worker


def test_set_input_language_validates_and_saves():
    class Cfg(dict):
        def set(self, k, v):
            self[k] = v
    c = Ctl()
    c.cfg = Cfg(input_language="auto")
    c.set_input_language("he")
    assert c.cfg["input_language"] == "he" and c.loads == 1
    with pytest.raises(ValueError):
        c.set_input_language("fr")


def test_history_names_the_hebrew_model(monkeypatch):
    c = Ctl()
    rows = []
    c.cfg.update(keep_history=True, vad=False, all_caps=False, live_insert_s=0)
    c.history = SimpleNamespace(add=lambda text, **kw: rows.append(kw) or 1)
    c.win = SimpleNamespace(show_history=lambda: None, show_language=lambda i: None)
    c.he_engine.threads = 4
    c.engine.threads = 4
    info = c.take_language(detected("he"))
    c.remember("שלום", seconds=1.0, lang=info)
    r = rows[0]
    assert r["model"] == f"{HE.id} v1" and r["model_rev"] == "r"
    assert r["decode"]["language"] == "he" and r["decode"]["language_source"] == "keyboard"
    assert r["decode"]["layout"] == "il" and r["decode"]["engine"] == "sherpa_online_transducer"
