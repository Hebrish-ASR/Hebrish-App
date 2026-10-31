"""Back up the user's data to one archive (B-76, Daniel 2026-10-31). Desktop only.

What goes in (the archive's top folder is the file name without its extension):

    manifest.json        what this is: app version, when, device id, counts, where each part came from
    history/history.db   a consistent snapshot of the history (SQLite backup API: safe while the app
                         is writing, WAL included)
    history/history.jsonl  the same transcripts as JSON Lines, oldest first, readable without SQLite
    transcripts/...      the transcripts folder (B-74) as is: YYYY/MM/DD/*.md
    dictionary.json      the personal dictionary, when there is one
    config.json          the settings, when there are some

Not included: models (re-downloadable, hundreds of MB) and saved Transcription-tab recordings
(audio; large).

Formats: `tar.gz` (default) or `zip`. File name: `YYYY-MM-DD_HHMM_hebrish-backup_<host>_<n>-dictations.<ext>`,
so backups sort by date and say where they came from and how much they hold.

No Qt import: ui/window.py runs `make()` on a worker thread; tests in tests/test_backup.py.
"""

import io
import json
import socket
import sqlite3
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

FORMATS = {"tar.gz": "tar.gz", "zip": "zip"}


def _host() -> str:
    h = "".join(c if c.isalnum() or c == "-" else "-" for c in socket.gethostname().split(".")[0])
    return h.strip("-").lower() or "computer"


def _snapshot(db: Path, dest: Path) -> tuple[dict, sqlite3.Connection]:
    """Copy `db` to `dest` with the backup API; returns counts read from the copy, and the copy open."""
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=10)
    out = sqlite3.connect(dest)
    try:
        src.backup(out)
    finally:
        src.close()
    try:
        r = out.execute("SELECT COUNT(*), COALESCE(SUM(words), 0), MIN(at), MAX(at) FROM dictations").fetchone()
        dev = out.execute("SELECT value FROM meta WHERE key = 'device'").fetchone()
    except sqlite3.Error:
        r, dev = (0, 0, None, None), None
    stats = {"dictations": r[0], "words": r[1],
             "first": _iso(r[2]), "last": _iso(r[3]), "device": dev[0] if dev else None}
    return stats, out


def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t)) if t else None


def _jsonl(con: sqlite3.Connection) -> bytes:
    con.row_factory = sqlite3.Row
    buf = io.StringIO()
    try:
        for r in con.execute("SELECT * FROM dictations ORDER BY at, id"):
            buf.write(json.dumps(dict(r), ensure_ascii=False) + "\n")
    except sqlite3.Error:
        pass
    return buf.getvalue().encode("utf-8")


def file_name(fmt: str, dictations: int, when: float | None = None) -> str:
    stamp = time.strftime("%Y-%m-%d_%H%M", time.localtime(when if when is not None else time.time()))
    return f"{stamp}_hebrish-backup_{_host()}_{dictations}-dictations.{FORMATS[fmt]}"


def count(history_db: Path) -> int:
    """Dictations in the history, for the suggested file name (0 if there is none)."""
    if not Path(history_db).is_file():
        return 0
    try:
        con = sqlite3.connect(f"file:{history_db}?mode=ro", uri=True, timeout=5)
        try:
            return con.execute("SELECT COUNT(*) FROM dictations").fetchone()[0]
        finally:
            con.close()
    except sqlite3.Error:
        return 0


def make(dest: Path, *, history_db: Path, transcripts_dir: Path, dictionary: Path | None = None,
         config: Path | None = None, app_version: str = "") -> dict:
    """Write the archive to `dest` (format from its extension). Returns the manifest. Raises OSError."""
    dest = Path(dest)
    fmt = "zip" if dest.name.endswith(".zip") else "tar.gz"
    top = dest.name[: -len(FORMATS[fmt]) - 1]
    files: list[tuple[str, Path | bytes]] = []
    manifest = {"kind": "hebrish-desktop-backup", "schema": 1, "app_version": app_version,
                "created": _iso(time.time()), "host": _host(), "format": fmt,
                "history": None, "transcripts": None, "dictionary": None, "config": None}
    with tempfile.TemporaryDirectory() as tmp:
        if Path(history_db).is_file():
            snap = Path(tmp) / "history.db"
            stats, con = _snapshot(Path(history_db), snap)
            try:
                jsonl = _jsonl(con)
            finally:
                con.close()
            files += [("history/history.db", snap), ("history/history.jsonl", jsonl)]
            manifest["history"] = {"source": str(history_db), **stats}
        tdir = Path(transcripts_dir)
        if tdir.is_dir():
            mds = sorted(p for p in tdir.rglob("*") if p.is_file())
            files += [(f"transcripts/{p.relative_to(tdir).as_posix()}", p) for p in mds]
            manifest["transcripts"] = {"source": str(tdir), "files": len(mds),
                                       "bytes": sum(p.stat().st_size for p in mds)}
        for key, p in (("dictionary", dictionary), ("config", config)):
            if p and Path(p).is_file():
                files.append((f"{key}.json", Path(p)))
                manifest[key] = {"source": str(p)}
        files.insert(0, ("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False).encode()))

        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        try:
            if fmt == "zip":
                with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
                    for name, src in files:
                        if isinstance(src, bytes):
                            z.writestr(f"{top}/{name}", src)
                        else:
                            z.write(src, f"{top}/{name}")
            else:
                with tarfile.open(part, "w:gz") as t:
                    for name, src in files:
                        if isinstance(src, bytes):
                            info = tarfile.TarInfo(f"{top}/{name}")
                            info.size, info.mtime = len(src), int(time.time())
                            t.addfile(info, io.BytesIO(src))
                        else:
                            t.add(src, f"{top}/{name}", recursive=False)
            part.replace(dest)
        except BaseException:
            part.unlink(missing_ok=True)
            raise
    manifest["bytes"] = dest.stat().st_size
    return manifest
