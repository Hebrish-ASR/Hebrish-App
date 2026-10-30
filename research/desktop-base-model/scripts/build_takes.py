#!/usr/bin/env python3
"""Build the test material once, with the app's own runtime (Sabich timestamps pick the pause points).

    desktop/.venv/bin/python research/desktop-base-model/scripts/build_takes.py <bench data/test dir> <disfluent snapshot dir> <out.npz>

Takes: exactly as desktop/scripts/seam_bench.py builds them (its functions are imported, same seed):
benchmark test clips (subsets clean, desktop_mic, english_control, > 3.5 s), one 0.7/1.0/1.4/2.0 s pause
inserted inside each sentence at a word boundary before a lowercase word, four clips to a take with
0.8/1.3/2.0 s between them. Low noise (std 0.002) fills every pause.

Stop/restart: each take is cut once, in the middle of its inside-sentence pause of clip 1 (even takes)
or clip 2 (odd takes): first = audio up to the pause, second = audio after it. `second_sent` is the
rest of that sentence only (for Engine.transcribe_after, which falls back to no context above 25 s).

Disfluent: Hebrish/Disfluent-Read-Sentences (train + test) as recorded; the snapshot may be an audiofolder
revision or the Parquet layout (main since 2026-10-30).
<bench data/test dir>: the benchmark's audiofolder `data/test`, i.e. a snapshot at its pinned v1 commit
3cb0b2b3b3e4 (the benchmark's `main` is Parquet since 2026-10-30).
Speed: ~10 s and ~30 s of real speech (benchmark clips joined with 0.5 s pauses)."""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "desktop/scripts"))
import seam_bench as sb  # noqa: E402

E = sb.E
SR = sb.SR


def dis_rows(dis, split):
    """(row, audio path) of a Disfluent-Read-Sentences snapshot split. Audiofolder: data/<split>/metadata.jsonl.
    Parquet (the dataset since 2026-10-30): index meta/<split>.jsonl; each take's audio file sits verbatim
    in its shard at audio_offset/audio_length and is cut out once to data/<split>/<audio_path>."""
    if not (dis / "meta" / "schema.json").exists():
        for line in open(dis / "data" / split / "metadata.jsonl"):
            m = json.loads(line)
            yield m, dis / "data" / split / m["file_name"]
        return
    for line in open(dis / "meta" / f"{split}.jsonl"):
        m = json.loads(line)
        p = dis / "data" / split / m["audio_path"]
        if not p.exists():
            with open(dis / m["shard"], "rb") as f:
                f.seek(m["audio_offset"])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(f.read(m["audio_length"]))
        yield m, p


def main():
    d, dis, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    meta = [json.loads(line) for line in open(d / "metadata.jsonl")]
    meta = [m for m in meta if m["subset"] in sb.SUBSETS and m["duration_s"] > 3.5]
    eng = E.Engine()
    eng.load(next((sb.MODELS / "sabich").iterdir()), 8)
    clips = []
    for m in meta:
        x = sb.read_wav(d / m["file_name"])
        cut = sb.split_point(eng, x)
        if cut is not None:
            clips.append((x, cut, m["text"].strip(), m["id"]))
    arrays, takes = {}, []
    for n, t in enumerate(range(0, len(clips) - sb.PER_TAKE + 1, sb.PER_TAKE)):
        audio, refs, pauses, ends, ids = [], [], [], [], []
        pos = 0
        for i, (x, cut, ref, cid) in enumerate(clips[t:t + sb.PER_TAKE]):
            gap = sb.quiet(sb.MID_GAPS[(t + i) % len(sb.MID_GAPS)])
            audio += [x[:cut], gap, x[cut:]]
            pauses.append((pos + cut, pos + cut + len(gap)))
            pos += len(x) + len(gap)
            ends.append(pos)
            if i < sb.PER_TAKE - 1:
                g = sb.quiet(sb.BETWEEN_GAPS[(t + i) % len(sb.BETWEEN_GAPS)])
                audio.append(g)
                pos += len(g)
            refs.append(ref if ref[-1] in ".?!" else ref + ".")
            ids.append(cid)
        a = np.concatenate(audio)
        k = 1 + n % 2
        p0, p1 = pauses[k]
        mid = (p0 + p1) // 2
        arrays[f"take{n}"] = a
        takes.append(dict(name=f"take{n}", ref=" ".join(refs), clip_ids=ids, seconds=round(len(a) / SR, 2),
                          split_clip=k, split_ref=refs[k], first_end=mid, second_start=mid,
                          second_sent_end=ends[k]))
    dm = []
    for split in ("train", "test"):
        for m, path in dis_rows(dis, split):
            x = sb.read_wav(path)
            arrays[f"dis_{m['id']}"] = x
            dm.append(dict(name=f"dis_{m['id']}", ref=m["text"].strip(), seconds=round(len(x) / SR, 2), split=split))
    # speed clips: real speech, joined with 0.5 s of quiet
    for target in (10, 30):
        parts, tot = [], 0
        for x, _, _, _ in clips[40:]:
            parts += [x, sb.quiet(0.5)]
            tot += len(x) + int(0.5 * SR)
            if tot >= target * SR:
                break
        arrays[f"speed{target}"] = np.concatenate(parts)[: target * SR]
    np.savez_compressed(out, **arrays)
    out.with_suffix(".json").write_text(json.dumps(dict(takes=takes, disfluent=dm), indent=1))
    print(len(takes), "takes", round(sum(t["seconds"] for t in takes) / 60, 1), "min;",
          len(dm), "disfluent", round(sum(t["seconds"] for t in dm) / 60, 1), "min")


if __name__ == "__main__":
    main()
