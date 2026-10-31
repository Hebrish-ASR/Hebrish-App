"""hebrish.transcripts (B-74): dated folders, snake_case titles, Markdown, no overwrites."""

import json
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


def _body(p):
    """The text after the front matter, H1, H2 and credit line."""
    return p.read_text().split("*\n\n", 1)[1]


def test_save_no_overwrite(tmp_path):
    a = transcripts.save("first", str(tmp_path), when=WHEN)
    b = transcripts.save("second", str(tmp_path), when=WHEN)
    assert _body(a) == "first\n" and b.name == "14-05-09-2.md" and _body(b) == "second\n"
    assert (tmp_path / "2026/10/31/14-05-09.json").is_file() and b.with_suffix(".json").is_file()


def test_save_with_title(tmp_path):
    meta = {"generator": "Hebrish 1.014", "model": "Sabich v2.3", "audio_seconds": 12.34, "source": "recording"}
    p = transcripts.save("body text", str(tmp_path), title="Shopping list", when=WHEN, meta=meta)
    assert p.name == "shopping_list_14-05-09.md"
    t = p.read_text()
    fm, rest = t.split("\n---\n\n", 1)
    assert fm.startswith("---\ntitle: \"Shopping list\"\ndate: 2026-10-31T14:05:09")
    assert 'model: "Sabich v2.3"' in fm and "audio_seconds: 12.3" in fm and "version: transcript" in fm
    assert 'versions: "shopping_list_14-05-09.json"' in fm
    assert rest.startswith("# Shopping list\n\n## Saturday 31 October 2026, 14:05\n\n"
                           "*Transcribed by Hebrish 1.014 with Sabich v2.3 on 31 October 2026.*\n\nbody text\n")


def test_untitled_heading(tmp_path):
    p = transcripts.save("x", str(tmp_path), when=WHEN)
    assert "\n# Transcript\n" in p.read_text() and "title:" not in p.read_text()


def test_raw_and_cleaned_versions(tmp_path):
    p = transcripts.save("Edited text.", str(tmp_path), title="T", when=WHEN, raw="edited text")
    raw = p.with_name(p.stem + ".raw.md")
    assert raw.is_file() and _body(raw) == "edited text\n"
    same = transcripts.save("Same", str(tmp_path), when=WHEN, raw=" Same ")
    assert not same.with_name(same.stem + ".raw.md").exists()
    c1 = transcripts.add_version(p, "cleaned", "Clean.", {"cleanup_model": "S1-mini by Superwhisper v1"})
    c2 = transcripts.add_version(p, "cleaned", "Clean again.", {"cleanup_model": "S1-mini by Superwhisper v1"})
    assert c1.name == "t_14-05-09.cleaned.md" and c2.name == "t_14-05-09.cleaned-2.md"
    assert _body(p) == "Edited text.\n"                     # the original is never touched
    assert "Cleaned up by Hebrish with S1-mini by Superwhisper v1" in c1.read_text()
    doc = json.loads(p.with_suffix(".json").read_text())
    assert [v["kind"] for v in doc["versions"]] == ["transcript", "raw", "cleaned", "cleaned"]
    assert doc["versions"][2]["of"] == p.name and doc["versions"][2]["cleanup_model"].startswith("S1-mini")


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
