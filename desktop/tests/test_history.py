"""hebrish.history: the 0.7.0 SQLite transcript store (search, stats, corrections, audio)."""

import json
import time
import wave

import numpy as np

from hebrish.history import History, fts_query


def make(tmp_path):
    return History(tmp_path / "history.db")


def test_add_search_prefix_and_ranking(tmp_path):
    h = make(tmp_path)
    h.add("Order shakshuka for the meeting", seconds=3.0, model="shakshuka v1.0")
    h.add("The meeting moved to Sunday")
    h.add("   ")                                   # blank: not stored
    assert h.count() == 2
    assert [r["text"] for r in h.search("shak")] == ["Order shakshuka for the meeting"]
    assert len(h.search("meeting")) == 2
    assert h.search("meeting sunday")[0]["text"] == "The meeting moved to Sunday"
    assert "[shakshuka]" in h.search("shakshuka")[0]["snippet"]
    assert h.search('"(*') == h.recent(200)        # nothing searchable: the recent list, no error
    assert fts_query('a "b" c*') == '"a"* "b"* "c"*'


def test_stats_today_week_all(tmp_path):
    h = make(tmp_path)
    now = time.time()
    h.add("one two three", seconds=60, at=now)
    h.add("four five", at=now - 3 * 86400)
    h.add("six", at=now - 30 * 86400)
    st = h.stats(now)
    assert st["today"] == {"dictations": 1, "words": 3, "seconds": 60}
    assert st["week"]["words"] == 5 and st["all"]["words"] == 6
    assert st["days_active"] == 3


def test_correction_keeps_original_once(tmp_path):
    h = make(tmp_path)
    rid = h.add("meet at the shook")
    h.update_text(rid, "meet at the shuk")
    h.update_text(rid, "meet at the Shuk")
    r = h.recent()[0]
    assert (r["text"], r["original"]) == ("meet at the Shuk", "meet at the shook")
    assert h.search("shuk") and not h.search("shook")


def test_audio_kept_and_deleted(tmp_path):
    h = make(tmp_path)
    rid = h.add("hello", samples=np.zeros(16000, dtype=np.float32), seconds=1.0)
    r = h.recent()[0]
    f = h.audio_dir / r["audio"]
    with wave.open(str(f)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getnframes()) == (16000, 1, 16000)
    h.delete(rid)
    assert not f.exists() and h.count() == 0


def test_import_json_once_and_clear(tmp_path):
    old = tmp_path / "history.json"
    old.write_text(json.dumps([{"text": "newer", "at": 200.0}, {"text": "older", "at": 100.0}]))
    h = make(tmp_path)
    assert h.import_json(old) == 2
    assert not old.exists() and (tmp_path / "history.json.imported").exists()
    assert [r["text"] for r in h.recent()] == ["newer", "older"]
    assert h.recent()[0]["source"] == "import"
    h.clear()
    assert h.count() == 0 and h.search("newer") == []


def test_device_id_is_stable(tmp_path):
    d = make(tmp_path).device
    assert d and make(tmp_path).device == d
