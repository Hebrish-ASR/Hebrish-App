"""Transforms (B-82, Daniel 2026-11-02): rewrite a finished transcript with a prompt from the
text transformation prompt library (an email, a to-do list, meeting minutes, a tweet …).

Library: ../shared/text-transformation-prompts.json (schema 2, 206 prompts from Daniel's dataset
danielrosehill/Text-Transformation-Prompts-300525, tagged by type and style; written by
scripts/import_transformation_prompts.py), bundled as data/text-transformation-prompts.json.

Storage, in history.db (one app database; table prefixes say whose data it is):

    builtin_transform_prompts   shipped with the app. Rewritten from the bundled file whenever its
                                hash differs from meta `builtin_transform_prompts` (an app update),
                                never edited, left out of backups (backup.py drops `builtin_*`).
    user_transform_prompts      the user's edited copies, keyed by the built-in id: editing a
                                prompt copies it here and the copy is used from then on; "Reset"
                                deletes the copy. `based_on` keeps the built-in text it was copied
                                from, so a later library change can be shown. No prompts written
                                from scratch yet (Daniel, 2026-11-02: editing is the quick win).
    transform_prompts (view)    what the picker shows: built-in rows with the user's copy on top.

Model: a general instruction-following GGUF, catalogue `addons` kind `text_transform`, downloaded
and run on the same pinned llama-server as the clean-up and title models (cleanup.download /
cleanup.server). S1-mini can't do this: given a library prompt it ignores it and only cleans the
text (tested 2026-11-02, D-2026-11-02-01). The prompt is the system turn, the transcript
the user turn, through llama-server's chat endpoint (the GGUF's own chat template).

Never touches the transcript: the result is shown and saved as its own version
(transcripts.add_version kind "transformed"). No Qt import: tests/test_transforms.py.
"""

import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path

from . import cleanup

KIND = "text_transform"
BUNDLED = Path(__file__).parent / "data" / "text-transformation-prompts.json"
META_KEY = "builtin_transform_prompts"
MAX_INPUT_TOKENS = 3000      # whole transcript in one request (an email can't be written in chunks)
OUTPUT_SUFFIX = "\n\nOutput only the transformed text, without any introduction or comment."

TYPES = {"email": "Email", "message": "Message or post", "document": "Document", "notes": "Notes",
         "list": "List", "data": "Data (JSON, CSV …)", "ai-prompt": "AI prompt", "rewrite": "Rewrite",
         "fun": "Just for fun"}
STYLES = {"neutral": "Neutral", "formal": "Formal", "professional": "Professional", "casual": "Casual",
          "playful": "Playful"}

_COLS = ("id", "label", "name", "type", "style", "language", "featured", "prompt", "description",
         "output_format", "structured_output", "source_file")

DDL = """
CREATE TABLE IF NOT EXISTS builtin_transform_prompts (
    id      TEXT PRIMARY KEY,
    label   TEXT NOT NULL,
    name    TEXT NOT NULL,              -- the dataset's name, verbatim
    type    TEXT NOT NULL,
    style   TEXT NOT NULL,
    language TEXT NOT NULL,             -- en | he (the output's language)
    featured INTEGER NOT NULL,
    prompt  TEXT NOT NULL,              -- verbatim (CC BY-ND 4.0)
    description TEXT,
    output_format TEXT,
    structured_output INTEGER,          -- 1 | 0 | NULL (not stated)
    source_file TEXT
);
CREATE TABLE IF NOT EXISTS user_transform_prompts (
    id      TEXT PRIMARY KEY,           -- the built-in prompt's id
    label   TEXT NOT NULL,
    prompt  TEXT NOT NULL,
    based_on TEXT NOT NULL,             -- the built-in prompt text when it was copied
    edited  REAL NOT NULL
);
CREATE VIEW IF NOT EXISTS transform_prompts AS
    SELECT b.id, COALESCE(u.label, b.label) AS label, b.type, b.style, b.language, b.featured,
           COALESCE(u.prompt, b.prompt) AS prompt, b.prompt AS original, b.structured_output,
           u.id IS NOT NULL AS edited, u.id IS NOT NULL AND u.based_on <> b.prompt AS stale
    FROM builtin_transform_prompts b LEFT JOIN user_transform_prompts u ON u.id = b.id;
"""


# -- library -------------------------------------------------------------------------------

def bundle_hash(path: Path = BUNDLED) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def sync(db: sqlite3.Connection, path: Path = BUNDLED) -> bool:
    """Create the tables and load the bundled library into builtin_transform_prompts when it
    changed since the last load. User copies are kept (an edited prompt whose built-in was
    removed simply no longer shows). True when the table was rewritten."""
    db.executescript(DDL)
    h = bundle_hash(path)
    cur = db.execute("SELECT value FROM meta WHERE key = ?", (META_KEY,)).fetchone()
    if cur and cur[0] == h and db.execute("SELECT COUNT(*) FROM builtin_transform_prompts").fetchone()[0]:
        return False
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = [tuple(p.get(c) for c in _COLS) for p in doc["prompts"]]
    with db:
        db.execute("DELETE FROM builtin_transform_prompts")
        db.executemany(f"INSERT INTO builtin_transform_prompts({', '.join(_COLS)}) "
                       f"VALUES ({', '.join('?' * len(_COLS))})", rows)
        db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (META_KEY, h))
    return True


def search(db: sqlite3.Connection, q: str = "", type_: str | None = None, style: str | None = None,
           featured: bool = False, edited: bool = False) -> list[dict]:
    """Prompts for the picker: every word of `q` in the label or prompt, optional type and style;
    featured first, then by label."""
    sql, args = ["SELECT * FROM transform_prompts WHERE 1"], []
    for w in re.findall(r"\w+", q or ""):
        sql.append("AND (label LIKE ? OR prompt LIKE ?)")
        args += [f"%{w}%"] * 2
    if type_:
        sql.append("AND type = ?")
        args.append(type_)
    if style:
        sql.append("AND style = ?")
        args.append(style)
    if featured:
        sql.append("AND featured")
    if edited:
        sql.append("AND edited")
    sql.append("ORDER BY featured DESC, label COLLATE NOCASE")
    return [_row(r) for r in db.execute(" ".join(sql), args)]


def get(db: sqlite3.Connection, pid: str) -> dict | None:
    r = db.execute("SELECT * FROM transform_prompts WHERE id = ?", (pid,)).fetchone()
    return _row(r) if r else None


def _row(r) -> dict:
    cols = ("id", "label", "type", "style", "language", "featured", "prompt", "original",
            "structured_output", "edited", "stale")
    d = dict(zip(cols, tuple(r)))
    for k in ("featured", "edited", "stale"):
        d[k] = bool(d[k])
    return d


def edit(db: sqlite3.Connection, pid: str, prompt: str, label: str | None = None):
    """Save the user's version of built-in prompt `pid` (a copy; the built-in stays as shipped).
    Saving the original text unchanged removes the copy."""
    b = db.execute("SELECT label, prompt FROM builtin_transform_prompts WHERE id = ?", (pid,)).fetchone()
    if b is None:
        raise KeyError(pid)
    prompt, label = prompt.strip(), (label or "").strip() or b[0]
    if not prompt:
        raise ValueError("the prompt is empty")
    with db:
        if prompt == b[1] and label == b[0]:
            db.execute("DELETE FROM user_transform_prompts WHERE id = ?", (pid,))
        else:
            db.execute("INSERT OR REPLACE INTO user_transform_prompts(id, label, prompt, based_on, edited) "
                       "VALUES (?, ?, ?, ?, ?)", (pid, label, prompt, b[1], time.time()))


def reset(db: sqlite3.Connection, pid: str):
    """Back to the shipped prompt: the user's copy is deleted."""
    with db:
        db.execute("DELETE FROM user_transform_prompts WHERE id = ?", (pid,))


# -- model ---------------------------------------------------------------------------------

def entries() -> list[dict]:
    return cleanup.entries(KIND)


def ready() -> dict | None:
    """The transform model's entry when it is downloaded, else None."""
    for e in entries():
        if cleanup.installed(e["id"]) is not None:
            return e
    return None


def tidy(out: str, structured: bool = False) -> str:
    """The reply without a leftover think block or end token; for data prompts, without the
    Markdown fence around the whole reply."""
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S).replace(cleanup.END_OF_TURN, "").strip()
    if structured:
        m = re.fullmatch(r"```[\w-]*\n(.*?)\n?```", out, flags=re.S)
        if m:
            out = m.group(1).strip()
    return out


def run_with(client, text: str, prompt: dict) -> str:
    """`text` rewritten by `prompt` (a search()/get() row) through `client` (cleanup.Server or a
    fake with count() and chat()). Raises on any failure; the caller keeps the transcript."""
    text = text.strip()
    if not text:
        raise ValueError("there is no transcript to transform")
    n = client.count(text)
    if n > MAX_INPUT_TOKENS:
        raise ValueError(f"the transcript is too long to transform in one go ({n} tokens, "
                         f"at most {MAX_INPUT_TOKENS}, about {MAX_INPUT_TOKENS * 3 // 4} words)")
    n_predict = min(4096, max(600, 2 * n + 200))
    content, stop = client.chat(prompt["prompt"] + OUTPUT_SUFFIX, text, n_predict,
                                timeout=60.0 + n_predict / 5.0)
    out = tidy(content, bool(prompt.get("structured_output")) or prompt.get("type") == "data")
    if not out:
        raise RuntimeError("the model returned nothing")
    if stop == "limit":
        raise RuntimeError("the model's answer was cut off")
    return out


def run(text: str, prompt: dict) -> str:
    e = ready()
    if e is None:
        raise FileNotFoundError("the transform model isn't downloaded")
    return run_with(cleanup.server(e["id"]), text, prompt)
