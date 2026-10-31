"""hebrish.backup (B-76): one archive of history, transcripts, dictionary and settings."""

import json
import tarfile
import time
import zipfile

import pytest

from hebrish import backup, transcripts
from hebrish.history import History


@pytest.fixture
def data(tmp_path):
    h = History(tmp_path / "data" / "history.db")
    h.add("Ani holekh la-makolet", seconds=2.0, model="Sabich v2.3")
    h.add("second take", seconds=1.0, model="Sabich v2.3")      # left open: WAL not checkpointed
    tdir = tmp_path / "transcripts"
    transcripts.save("hello", str(tdir), when=time.mktime((2026, 10, 31, 9, 0, 0, 0, 0, -1)))
    (tmp_path / "dictionary.json").write_text('{"schema": 1, "words": []}')
    yield tmp_path, h, tdir
    h.close()


@pytest.mark.parametrize("fmt", ["tar.gz", "zip"])
def test_archive(data, fmt):
    root, h, tdir = data
    name = backup.file_name(fmt, backup.count(h.path), when=time.mktime((2026, 10, 31, 15, 7, 0, 0, 0, -1)))
    assert name.startswith("2026-10-31_1507_hebrish-backup_") and name.endswith(f"_2-dictations.{fmt}")
    dest = root / "out" / name
    m = backup.make(dest, history_db=h.path, transcripts_dir=tdir,
                    dictionary=root / "dictionary.json", config=root / "missing.json", app_version="1.015")
    assert m["history"]["dictations"] == 2 and m["transcripts"]["files"] == 2 and m["config"] is None
    top = name[: -len(fmt) - 1]
    if fmt == "zip":
        with zipfile.ZipFile(dest) as z:
            names = set(z.namelist())
            jl = z.read(f"{top}/history/history.jsonl").decode()
            man = json.loads(z.read(f"{top}/manifest.json"))
    else:
        with tarfile.open(dest) as t:
            names = set(t.getnames())
            jl = t.extractfile(f"{top}/history/history.jsonl").read().decode()
            man = json.loads(t.extractfile(f"{top}/manifest.json").read())
    assert {f"{top}/history/history.db", f"{top}/transcripts/2026/10/31/09-00-00.md",
            f"{top}/dictionary.json"} <= names
    assert [json.loads(x)["text"] for x in jl.splitlines()] == ["Ani holekh la-makolet", "second take"]
    assert man["app_version"] == "1.015" and man["kind"] == "hebrish-desktop-backup"
    assert not dest.with_name(dest.name + ".part").exists()


def test_no_history(tmp_path):
    m = backup.make(tmp_path / "b.zip", history_db=tmp_path / "none.db", transcripts_dir=tmp_path / "none")
    assert m["history"] is None and m["transcripts"] is None and backup.count(tmp_path / "none.db") == 0
