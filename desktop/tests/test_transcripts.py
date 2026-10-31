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
    assert transcripts.default_dir().name == "Hebrish transcripts"
