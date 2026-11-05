"""hebrish.transforms (B-82): the shipped prompt library in history.db, user copies, the run."""

import sqlite3
import tarfile
import time

import pytest

from hebrish import backup, transforms
from hebrish.history import History


@pytest.fixture
def h(tmp_path):
    hist = History(tmp_path / "history.db")
    yield hist
    hist.close()


def test_library_loaded_once(h):
    n = h.db.execute("SELECT COUNT(*) FROM builtin_transform_prompts").fetchone()[0]
    assert n > 200
    assert h.meta(transforms.META_KEY) == transforms.bundle_hash()
    assert transforms.sync(h.db) is False            # unchanged bundle: not rewritten


def test_filters(h):
    feats = transforms.search(h.db, featured=True)
    assert 5 <= len(feats) <= 20 and all(p["featured"] for p in feats)
    emails = transforms.search(h.db, type_="email", style="professional")
    assert emails and all(p["type"] == "email" and p["style"] == "professional" for p in emails)
    assert any(p["id"] == "business-email" for p in transforms.search(h.db, "business email"))
    assert transforms.search(h.db, "zzqqxx") == []


def test_edit_is_a_copy_and_reset_restores(h):
    orig = transforms.get(h.db, "tweet")
    transforms.edit(h.db, "tweet", "Write it as a short post for Mastodon.")
    p = transforms.get(h.db, "tweet")
    assert p["edited"] and not p["stale"] and p["prompt"].startswith("Write it as")
    assert p["original"] == orig["prompt"]
    # the shipped row is untouched
    assert h.db.execute("SELECT prompt FROM builtin_transform_prompts WHERE id='tweet'").fetchone()[0] == orig["prompt"]
    assert [x["id"] for x in transforms.search(h.db, edited=True)] == ["tweet"]
    transforms.reset(h.db, "tweet")
    assert transforms.get(h.db, "tweet") == orig


def test_saving_the_original_text_drops_the_copy(h):
    orig = transforms.get(h.db, "tweet")
    transforms.edit(h.db, "tweet", "changed")
    transforms.edit(h.db, "tweet", orig["prompt"])
    assert not transforms.get(h.db, "tweet")["edited"]
    with pytest.raises(ValueError):
        transforms.edit(h.db, "tweet", "   ")
    with pytest.raises(KeyError):
        transforms.edit(h.db, "no-such-prompt", "x")


def test_library_update_keeps_edits_and_flags_stale(h, tmp_path):
    transforms.edit(h.db, "tweet", "my version")
    import json
    doc = json.loads(transforms.BUNDLED.read_text(encoding="utf-8"))
    for p in doc["prompts"]:
        if p["id"] == "tweet":
            p["prompt"] = "A newer shipped prompt."
    newer = tmp_path / "lib.json"
    newer.write_text(json.dumps(doc))
    assert transforms.sync(h.db, newer) is True
    p = transforms.get(h.db, "tweet")
    assert p["prompt"] == "my version" and p["stale"] and p["original"] == "A newer shipped prompt."


def test_backup_leaves_out_builtin_tables(h, tmp_path):
    transforms.edit(h.db, "tweet", "my version")
    h.add("hello there", seconds=1.0)
    dest = tmp_path / "b.tar.gz"
    backup.make(dest, history_db=h.path, transcripts_dir=tmp_path / "none")
    with tarfile.open(dest) as t:
        member = next(n for n in t.getnames() if n.endswith("/history/history.db"))
        (tmp_path / "x").mkdir()
        (tmp_path / "x" / "history.db").write_bytes(t.extractfile(member).read())
    con = sqlite3.connect(tmp_path / "x" / "history.db")
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
    assert "builtin_transform_prompts" not in names and "user_transform_prompts" in names
    assert con.execute("SELECT value FROM meta WHERE key = ?", (transforms.META_KEY,)).fetchone() is None
    con.close()
    # restored, it loads the library again and keeps the edit
    r = History(tmp_path / "x" / "history.db")
    assert transforms.get(r.db, "tweet")["prompt"] == "my version"
    r.close()


class Fake:
    def __init__(self, reply, stop="eos", tokens=50):
        self.reply, self.stop, self.tokens, self.calls = reply, stop, tokens, []

    def count(self, text):
        return self.tokens

    def chat(self, system, user, n_predict, timeout):
        self.calls.append((system, user, n_predict))
        return self.reply, self.stop


def test_run_sends_prompt_as_system_and_transcript_as_user(h):
    p = transforms.get(h.db, "business-email")
    c = Fake("<think>\n\n</think>\n\nDear Yossi,\n\nCould you come on Thursday?")
    out = transforms.run_with(c, "  ask yossi to come thursday  ", p)
    assert out == "Dear Yossi,\n\nCould you come on Thursday?"
    system, user, _ = c.calls[0]
    assert system.startswith(p["prompt"]) and system.endswith(transforms.OUTPUT_SUFFIX)
    assert user == "ask yossi to come thursday"


def test_run_unwraps_fences_for_data_only(h):
    data = {"prompt": "x", "type": "data", "structured_output": True}
    assert transforms.run_with(Fake('```json\n{"a": 1}\n```'), "t", data) == '{"a": 1}'
    prose = {"prompt": "x", "type": "rewrite", "structured_output": None}
    assert transforms.run_with(Fake("```\ncode\n```"), "t", prose) == "```\ncode\n```"


@pytest.mark.parametrize("fake, err", [(Fake(""), RuntimeError), (Fake("half", stop="limit"), RuntimeError),
                                       (Fake("x", tokens=transforms.MAX_INPUT_TOKENS + 1), ValueError)])
def test_run_failures_raise(fake, err):
    with pytest.raises(err):
        transforms.run_with(fake, "text", {"prompt": "x", "type": "rewrite"})
    with pytest.raises(ValueError):
        transforms.run_with(fake, "   ", {"prompt": "x", "type": "rewrite"})
