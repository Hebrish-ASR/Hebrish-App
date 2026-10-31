"""hebrish.transcripts (B-74): dated folders, snake_case titles, Markdown, no overwrites."""

import time

from hebrish import transcripts

WHEN = time.mktime((2026, 10, 31, 14, 5, 9, 0, 0, -1))


def test_layout_and_name(tmp_path):
    p = transcripts.path_for(tmp_path, WHEN)
    assert p == tmp_path / "2026" / "10" / "31" / "14-05-09.md"


def test_title_prefix(tmp_path):
    p = transcripts.path_for(tmp_path, WHEN, "Notes on the API, v2!")
    assert p.name == "notes_on_the_api_v2_14-05-09.md"


def test_slug():
    assert transcripts.slug("  Ani holekh la-makolet ") == "ani_holekh_la_makolet"
    assert transcripts.slug("Café déjà vu") == "cafe_deja_vu"
    assert transcripts.slug("!!!") == ""
    long = transcripts.slug("word " * 40)
    assert len(long) <= transcripts.SLUG_MAX and not long.endswith("_")


def test_save_no_overwrite(tmp_path):
    a = transcripts.save("first", str(tmp_path), when=WHEN)
    b = transcripts.save("second", str(tmp_path), when=WHEN)
    assert a.read_text() == "first\n" and b.name == "14-05-09-2.md" and b.read_text() == "second\n"


def test_save_with_title(tmp_path):
    p = transcripts.save("body text", str(tmp_path), title="Shopping list", when=WHEN)
    assert p.name == "shopping_list_14-05-09.md"
    assert p.read_text() == "# Shopping list\n\nbody text\n"


def test_default_folder():
    assert transcripts.folder("") == transcripts.default_dir()
    assert transcripts.default_dir().name == "transcripts"
    assert transcripts.default_dir().parent.name == "Hebrish"


def test_hebrish_folder(tmp_path, monkeypatch):
    """2026-10-31: transcripts/ and recordings/ live in one Hebrish folder (files_dir), unless set on their own."""
    from hebrish import config
    monkeypatch.setattr(config.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    (tmp_path / "Documents").mkdir()
    cfg = {"files_dir": "", "transcripts_dir": "", "tm_audio_dir": ""}
    assert config.transcripts_folder(cfg) == tmp_path / "Documents" / "Hebrish" / "transcripts"
    assert config.recordings_folder(cfg) == tmp_path / "Documents" / "Hebrish" / "recordings"
    cfg["files_dir"] = str(tmp_path / "hebrish")
    assert config.transcripts_folder(cfg) == tmp_path / "hebrish" / "transcripts"
    cfg["tm_audio_dir"] = "/elsewhere"
    assert config.recordings_folder(cfg) == config.Path("/elsewhere")
    # localised Documents from user-dirs.dirs
    (tmp_path / "Dokumente").mkdir()
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "user-dirs.dirs").write_text('XDG_DOCUMENTS_DIR="$HOME/Dokumente"\n')
    assert config.default_files_root() == tmp_path / "Dokumente" / "Hebrish"


def test_old_default_folders_are_pinned(tmp_path, monkeypatch):
    from hebrish import config
    monkeypatch.setattr(config.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    (tmp_path / "Documents" / "Hebrish recordings").mkdir(parents=True)
    out = config.upgrade({"mics": {}, "send_chord": "enter", "clear_each_take": False})
    assert out["tm_audio_dir"] == str(tmp_path / "Documents" / "Hebrish recordings")
    assert "transcripts_dir" not in out
    # a config that already has files_dir is left alone
    assert "tm_audio_dir" not in config.upgrade({"mics": {}, "send_chord": "enter", "files_dir": ""})
