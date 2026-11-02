"""Maintainer mode's files (R-2026-11-02-2, hebrish.maintainer): audio + seam log per History
row, pruned by age and size."""

import json
from datetime import date

import numpy as np

from hebrish import maintainer
from hebrish.audio import SAMPLE_RATE


def test_save_writes_audio_and_log(tmp_path):
    x = (0.1 * np.sin(np.arange(SAMPLE_RATE) / 10)).astype(np.float32)
    j = maintainer.save(42, x, {"pieces": [{"raw": "Hello."}], "pasted": []}, root=tmp_path, day="2026-11-02")
    rec = json.loads(j.read_text())
    assert rec["row_id"] == 42 and rec["schema"] == 1 and rec["pieces"][0]["raw"] == "Hello."
    audio = j.with_name(rec["audio"])
    assert audio.exists() and audio.suffix in (".flac", ".wav")
    if audio.suffix == ".flac":
        import soundfile
        y, sr = soundfile.read(str(audio), dtype="float32")
        assert sr == SAMPLE_RATE and len(y) == len(x) and np.abs(y - x).max() < 1e-3


def test_prune_by_age_then_size(tmp_path):
    for day, rid in (("2026-10-01", 1), ("2026-10-30", 2), ("2026-11-01", 3), ("2026-11-02", 4)):
        maintainer.save(rid, np.zeros(SAMPLE_RATE * 4, np.float32), {"pieces": []}, root=tmp_path, day=day)
    maintainer.prune(keep_days=14, max_gb=100, root=tmp_path, today=date(2026, 11, 2))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["2026-10-30", "2026-11-01", "2026-11-02"]
    one = maintainer.size_bytes(tmp_path) / 3
    maintainer.prune(keep_days=14, max_gb=1.5 * one / 1024 ** 3, root=tmp_path, today=date(2026, 11, 2))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["2026-11-02"]   # oldest takes first, empty days removed


def test_clear(tmp_path):
    maintainer.save(1, np.zeros(10, np.float32), {}, root=tmp_path / "m")
    maintainer.clear(tmp_path / "m")
    assert not (tmp_path / "m").exists()
