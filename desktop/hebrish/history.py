"""Dictation history: every transcript, kept on this computer in SQLite (0.7.0).

Up to 0.6.x the History tab was the last 50 transcripts in history.json, off by default.
From 0.7.0 (Daniel, 2026-10-22, D-2026-10-22-13) history is on by default and unlimited, so
it has to stay searchable and countable: one SQLite file with a full-text index.

    DATA_DIR/history.db                 dictations + dictations_fts (FTS5) + meta
    (no audio: 0.7.3 removed `keep_audio` and deletes history-audio/ left by 0.7.0-0.7.2,
     Daniel 2026-10-22, D-2026-10-22-20: audio eats disk; the text is what is kept)

Each row has a random `uid` and the database a random `device` id (in `meta`), so rows can
later be merged across devices or backed up without colliding (Drive backup and accounts are
planned: planning/backlog.md). Schema changes bump SCHEMA and migrate in _migrate().

Only the GUI thread uses a History object.
"""

import json
import re
import sqlite3
import time
import uuid
from pathlib import Path


SCHEMA = 2      # 2 (0.7.3): model_rev and decode, so mistakes can be traced to exact weights

_DDL = """
CREATE TABLE IF NOT EXISTS dictations (
    id      INTEGER PRIMARY KEY,
    uid     TEXT NOT NULL UNIQUE,
    at      REAL NOT NULL,              -- unix time the transcript landed
    text    TEXT NOT NULL,
    words   INTEGER NOT NULL,
    seconds REAL,                       -- audio length; NULL when unknown (imported rows)
    model   TEXT NOT NULL DEFAULT '',   -- catalogue id and version, e.g. "shakshuka v1.0"
    source  TEXT NOT NULL DEFAULT 'dictate',   -- dictate | file | import
    audio   TEXT,                       -- unused since 0.7.3 (always NULL); was a file in history-audio/
    original TEXT,                      -- the model's text, set when the user first edits it
    model_rev TEXT,                     -- exact weights: the model version's commit (manifest revision); NULL before schema 2
    decode  TEXT                        -- JSON: app version, engine, device and the decode settings in force
);
CREATE INDEX IF NOT EXISTS dictations_at ON dictations(at);
CREATE VIRTUAL TABLE IF NOT EXISTS dictations_fts USING fts5(
    text, content='dictations', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER IF NOT EXISTS dictations_ai AFTER INSERT ON dictations BEGIN
    INSERT INTO dictations_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS dictations_ad AFTER DELETE ON dictations BEGIN
    INSERT INTO dictations_fts(dictations_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS dictations_au AFTER UPDATE OF text ON dictations BEGIN
    INSERT INTO dictations_fts(dictations_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO dictations_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def count_words(text: str) -> int:
    return len(text.split())


def fts_query(q: str) -> str:
    """User text -> an FTS5 query: every word must appear, each as a prefix ("shak" finds
    "shakshuka"). Quoting each term keeps FTS5 syntax characters from breaking the query."""
    terms = re.findall(r"\w+", q, flags=re.UNICODE)
    return " ".join(f'"{t}"*' for t in terms)


def _day_start(now: float) -> float:
    t = time.localtime(now)
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))


class History:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.audio_dir = self.path.with_name("history-audio")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_DDL)
        self._migrate()
        if self.audio_dir.is_dir():
            self.drop_audio()

    def _migrate(self):
        cur = self.meta("schema")
        if cur is None:
            self.set_meta("schema", str(SCHEMA))
            self.set_meta("device", uuid.uuid4().hex)
            self.set_meta("created", str(time.time()))
            return
        if int(cur) < 2:
            # 0.7.3 (Daniel, 2026-10-22): record the exact weights and decode settings per row, so
            # a word the model gets wrong can be tied to a model version as versions iterate.
            # Older rows keep NULL: their `model` label is all that is known.
            cols = {r[1] for r in self.db.execute("PRAGMA table_info(dictations)")}
            with self.db:
                for col in ("model_rev", "decode"):
                    if col not in cols:
                        self.db.execute(f"ALTER TABLE dictations ADD COLUMN {col} TEXT")
            self.set_meta("schema", "2")

    def meta(self, key):
        r = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return r[0] if r else None

    def set_meta(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, value))

    @property
    def device(self) -> str:
        return self.meta("device")

    # -- writing ----------------------------------------------------------------------
    def add(self, text: str, *, seconds: float | None = None, model: str = "",
            source: str = "dictate", at: float | None = None,
            model_rev: str | None = None, decode: dict | None = None) -> int:
        text = text.strip()
        if not text:
            return 0
        uid = uuid.uuid4().hex
        with self.db:
            cur = self.db.execute(
                "INSERT INTO dictations(uid, at, text, words, seconds, model, source, audio, model_rev, decode) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (uid, at or time.time(), text, count_words(text), seconds, model, source, None,
                 model_rev or None, json.dumps(decode, sort_keys=True) if decode else None))
        return cur.lastrowid

    def drop_audio(self):
        """Delete the audio 0.7.0-0.7.2 kept with `keep_audio` (0.7.3 keeps none) and unlink it
        from the rows. The text stays."""
        for f in self.audio_dir.glob("*.wav"):
            f.unlink(missing_ok=True)
        try:
            self.audio_dir.rmdir()
        except OSError:
            pass
        with self.db:
            self.db.execute("UPDATE dictations SET audio = NULL WHERE audio IS NOT NULL")

    def update_text(self, rid: int, text: str):
        """A corrected transcript (edited in the History tab). The model's own text is kept in
        `original` the first time, so model output -> correction pairs (with the audio, when
        kept) can become training data."""
        with self.db:
            self.db.execute("UPDATE dictations SET original = COALESCE(original, text), text = ?, "
                            "words = ? WHERE id = ?", (text.strip(), count_words(text), rid))

    def delete(self, rid: int):
        r = self.db.execute("SELECT audio FROM dictations WHERE id = ?", (rid,)).fetchone()
        if r and r["audio"]:
            (self.audio_dir / r["audio"]).unlink(missing_ok=True)
        with self.db:
            self.db.execute("DELETE FROM dictations WHERE id = ?", (rid,))

    def clear(self):
        with self.db:
            self.db.execute("DELETE FROM dictations")
            self.db.execute("INSERT INTO dictations_fts(dictations_fts) VALUES ('rebuild')")
        if self.audio_dir.is_dir():
            for f in self.audio_dir.glob("*.wav"):
                f.unlink(missing_ok=True)
        self.db.execute("VACUUM")

    def import_json(self, path: Path) -> int:
        """The 0.6.x history.json ([{"text", "at"}], newest first). Imported once, then
        renamed to history.json.imported so it isn't read again."""
        try:
            rows = json.loads(Path(path).read_text())
        except (OSError, ValueError):
            return 0
        n = 0
        for h in reversed(rows if isinstance(rows, list) else []):
            if isinstance(h, dict) and str(h.get("text", "")).strip():
                self.add(h["text"], at=h.get("at") or None, source="import")
                n += 1
        Path(path).rename(Path(path).with_name(Path(path).name + ".imported"))
        return n

    # -- reading ----------------------------------------------------------------------
    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM dictations").fetchone()[0]

    def recent(self, limit: int = 100, offset: int = 0) -> list[dict]:
        rows = self.db.execute("SELECT * FROM dictations ORDER BY at DESC, id DESC LIMIT ? OFFSET ?",
                               (limit, offset))
        return [dict(r) for r in rows]

    def search(self, q: str, limit: int = 200) -> list[dict]:
        """Keyword search, best match first (bm25), with the matches marked in `snippet`.
        Semantic search is planned (backlog): it would rank by meaning, not by words."""
        query = fts_query(q)
        if not query:
            return self.recent(limit)
        rows = self.db.execute(
            "SELECT d.*, snippet(dictations_fts, 0, '[', ']', '…', 24) AS snippet "
            "FROM dictations_fts JOIN dictations d ON d.id = dictations_fts.rowid "
            "WHERE dictations_fts MATCH ? ORDER BY bm25(dictations_fts), d.at DESC LIMIT ?",
            (query, limit))
        return [dict(r) for r in rows]

    def all(self):
        """Every row, oldest first (export, the dataset tools)."""
        for r in self.db.execute("SELECT * FROM dictations ORDER BY at, id"):
            yield dict(r)

    def stats(self, now: float | None = None) -> dict:
        """Words and dictations today, in the last 7 days (today included) and all time, plus
        hours of audio and the number of days with at least one dictation."""
        now = now or time.time()
        today = _day_start(now)
        week = _day_start(now - 6 * 86400)

        def agg(since):
            r = self.db.execute("SELECT COUNT(*), COALESCE(SUM(words), 0), COALESCE(SUM(seconds), 0) "
                                "FROM dictations WHERE at >= ?", (since,)).fetchone()
            return {"dictations": r[0], "words": r[1], "seconds": r[2]}

        out = {"today": agg(today), "week": agg(week), "all": agg(0)}
        first = self.db.execute("SELECT MIN(at) FROM dictations").fetchone()[0]
        out["since"] = first
        out["days_active"] = self.db.execute(
            "SELECT COUNT(DISTINCT date(at, 'unixepoch', 'localtime')) FROM dictations").fetchone()[0]
        return out

    CSV_COLUMNS = ("timestamp", "text", "model", "model_rev", "original", "seconds", "words", "source", "uid")

    def export_csv(self, path: Path) -> int:
        """One row per transcript, oldest first: local ISO timestamp, the text (as corrected),
        the model version label and exact weights (`model_rev`, from 0.7.3), the model's own text
        when corrected. UTF-8 with a BOM, so spreadsheets open it as UTF-8."""
        import csv
        n = 0
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(self.CSV_COLUMNS)
            for r in self.all():
                ts = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(r["at"]))
                w.writerow([ts, r["text"], r["model"], r.get("model_rev") or "", r["original"] or "",
                            "" if r["seconds"] is None else round(r["seconds"], 1), r["words"], r["source"], r["uid"]])
                n += 1
        return n

    def export_jsonl(self, path: Path) -> int:
        n = 0
        with open(path, "w", encoding="utf-8") as f:
            for r in self.all():
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                n += 1
        return n

    def size_bytes(self) -> int:
        n = sum(p.stat().st_size for p in self.path.parent.glob(self.path.name + "*") if p.is_file())
        if self.audio_dir.is_dir():
            n += sum(p.stat().st_size for p in self.audio_dir.glob("*.wav"))
        return n

    def close(self):
        self.db.close()
