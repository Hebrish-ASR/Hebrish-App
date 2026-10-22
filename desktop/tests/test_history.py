"""hebrish.history: the 0.7.0 SQLite transcript store (search, stats, corrections, audio)."""

import json
import time


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


def test_audio_left_by_older_versions_is_deleted(tmp_path):
    # 0.7.3 (D-2026-10-22-20): no audio is kept; what 0.7.0-0.7.2 kept goes, the text stays
    h = make(tmp_path)
    rid = h.add("hello", seconds=1.0)
    h.audio_dir.mkdir()
    (h.audio_dir / "x.wav").write_bytes(b"RIFF")
    with h.db:
        h.db.execute("UPDATE dictations SET audio = 'x.wav' WHERE id = ?", (rid,))
    h.close()
    h = make(tmp_path)
    assert not h.audio_dir.exists()
    assert [(r["text"], r["audio"]) for r in h.recent()] == [("hello", None)]


def test_export_csv(tmp_path):
    import csv
    h = make(tmp_path)
    h.add("Shalom, \"quoted\", and a comma", model="sabich Sabich v2.0", model_rev="e" * 40, at=1_000_000)
    rid = h.add("second", at=1_000_100)
    h.update_text(rid, "second take")
    p = tmp_path / "h.csv"
    assert h.export_csv(p) == 2
    rows = list(csv.DictReader(open(p, encoding="utf-8-sig", newline="")))
    assert list(rows[0]) == list(h.CSV_COLUMNS)
    assert rows[0]["text"] == 'Shalom, "quoted", and a comma' and rows[0]["model_rev"] == "e" * 40
    assert rows[1]["text"] == "second take" and rows[1]["original"] == "second"
    assert rows[0]["timestamp"].startswith("1970-01-1")


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


def test_rows_record_the_exact_weights_and_decode(tmp_path):
    # schema 2 (0.7.3): model_rev + decode JSON, exported with each row
    h = History(tmp_path / "h.db")
    h.add("Shalom", model="sabich Sabich v2.0", model_rev="eebf26d8c3f9" + "0" * 28,
          decode={"app": "0.7.3", "engine": "sherpa_offline_transducer", "live_insert_s": 5})
    h.add("No metadata")
    out = tmp_path / "x.jsonl"
    h.export_jsonl(out)
    rows = {r["text"]: r for r in map(json.loads, out.read_text().splitlines())}
    assert rows["Shalom"]["model_rev"].startswith("eebf26d8c3f9")
    assert json.loads(rows["Shalom"]["decode"])["live_insert_s"] == 5
    assert rows["No metadata"]["model_rev"] is None and rows["No metadata"]["decode"] is None


def test_schema_1_database_gains_the_columns_once(tmp_path):
    import sqlite3
    p = tmp_path / "old.db"
    db = sqlite3.connect(p)            # a 0.7.0-0.7.2 database: schema 1, no model_rev/decode
    db.executescript("""CREATE TABLE dictations (id INTEGER PRIMARY KEY, uid TEXT NOT NULL UNIQUE,
        at REAL NOT NULL, text TEXT NOT NULL, words INTEGER NOT NULL, seconds REAL,
        model TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT 'dictate', audio TEXT, original TEXT);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta VALUES ('schema', '1'), ('device', 'abc');
        INSERT INTO dictations(uid, at, text, words, model) VALUES ('u1', 1, 'old take', 2, 'sabich Sabich v2.0');""")
    db.commit()
    db.close()
    h = History(p)
    assert h.meta("schema") == "2" and h.device == "abc"
    h.add("new take", model_rev="r" * 40, decode={"app": "0.7.3"})
    rows = [dict(r) for r in h.db.execute("SELECT text, model_rev FROM dictations ORDER BY id")]
    assert rows == [{"text": "old take", "model_rev": None}, {"text": "new take", "model_rev": "r" * 40}]
    History(p)                           # opening again changes nothing
