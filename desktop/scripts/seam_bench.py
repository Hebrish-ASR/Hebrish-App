#!/usr/bin/env python3
"""Seams of insert-as-you-go (Sabich) when you stop to think in the middle of a sentence.

    .venv/bin/python scripts/seam_bench.py <benchmark data/test dir> [interval_s] [out.json]
    SETUPS="0.7.6" CONTEXT_S=2 .venv/bin/python scripts/seam_bench.py ...

<benchmark data/test dir>: `data/test` of the HF dataset Hebrish/English-Hebrew-Codeswitching-ASR-Benchmark
at its pinned v1 commit 3cb0b2b3b3e4 (an audiofolder; the dataset's `main` is Parquet since 2026-10-30).
Model: ~/.local/share/hebrish/models/sabich. CPU only, nothing is uploaded.

The other benches (pace_sim.py, live_bench.py) pause only between sentences. Real dictation pauses
inside them, which is where seams go wrong. Here every clip gets one pause inside a sentence, at a
word boundary found from Sabich's token timestamps on the clip alone (the quietest 20 ms just before
a lowercase word that follows a word with no mark), of MID_GAPS seconds in turn; clips are joined
four to a take with BETWEEN_GAPS. Each take is played in 0.5 s ticks through engine.live_split, as
Controller._live_tick does, and joined as Controller._worker does, in two setups:

- 0.7.5: each piece decoded alone; full stop held only at pauses under LIVE_BREAK_S; CONTINUES rule.
- whole: the take decoded at Stop (live insertion off), the floor.
- 0.7.6: each piece decoded after CONTEXT_S of the previous one (Engine.transcribe_after); the full
  stop held at every pause; the model's mark at the seam decides.

Scored against the reference text with case and marks (alignment on lowercased words):
mid_caps = capitalised words the reference has lowercase (not "I"), false_stops = .?! after a word
where the reference has none, lost_stops = the reverse, lost_caps = lowercase where the reference
capitalises; and WER (lowercase, marks stripped). Results: desktop/docs/maintaining.md,
"Context at the seams (0.7.6)"."""

import difflib
import json
import os
import re
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hebrish import engine as E  # noqa: E402

SR = 16000
TICK = 0.5
PER_TAKE = 4
MID_GAPS = (0.7, 1.0, 1.4, 2.0)
BETWEEN_GAPS = (0.8, 1.3, 2.0)
SUBSETS = {"clean", "desktop_mic", "english_control"}
MODELS = Path.home() / ".local/share/hebrish/models"
rng = np.random.default_rng(7)


def read_wav(p):
    w = wave.open(str(p))
    assert w.getframerate() == SR and w.getsampwidth() == 2
    a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    return a.reshape(-1, w.getnchannels()).mean(1) if w.getnchannels() > 1 else a


def quiet(n):
    return (rng.standard_normal(int(n * SR)) * 0.002).astype(np.float32)


def word_starts(eng, x):
    s = eng._rec.create_stream()
    s.accept_waveform(SR, np.concatenate([x, np.zeros(SR, np.float32)]))
    eng._rec.decode_stream(s)
    words, cur = [], None
    for tok, t in zip(s.result.tokens, s.result.timestamps):
        if tok.startswith(" ") or cur is None:
            cur = [tok.strip(), t]
            words.append(cur)
        else:
            cur[0] += tok
    return words


def split_point(eng, x):
    """Sample index of a pause point inside the sentence, or None."""
    words = word_starts(eng, x)
    n = len(words)
    ok = [k for k in range(1, n - 1) if words[k - 1][0][-1:].isalnum() and words[k][0][:1].islower()]
    if not ok:
        return None
    k = min(ok, key=lambda k: abs(k - n / 2))
    t = words[k][1]
    a, b = int(max(0, t - 0.3) * SR), int((t + 0.02) * SR)
    fr = x[a:b][: (b - a) // 320 * 320].reshape(-1, 320)
    return a + int(np.argmin((fr ** 2).mean(1))) * 320 + 160


def old_hold(text, pause):
    return pause is not None and pause < E.LIVE_BREAK_S and text.endswith(".") and not text.endswith("..")


def run_take(eng, x, interval, mode):
    """Play x in ticks; return (joined text, decode seconds, pieces)."""
    if mode == "whole":         # the floor: the take decoded at Stop, live insertion off
        t0 = time.monotonic()
        return eng.transcribe(x, vad=True, record=False), time.monotonic() - t0, 1
    pieces, buf, pos, step = [], np.zeros(0, np.float32), 0, int(TICK * SR)
    while pos < len(x):
        buf = np.concatenate([buf, x[pos:pos + step]])
        pos += step
        cut = E.live_split(buf, interval)
        if cut:
            pieces.append((buf[: cut[0]], cut[1]))
            buf = buf[cut[0]:]
    pieces.append((buf, None))
    parts, held, ctx, took = [], False, None, 0.0
    for i, (p, pause) in enumerate(pieces):
        final = pause is None
        t0 = time.monotonic()
        if mode == "0.7.6":
            text, stop = eng.transcribe_after(p, ctx, vad=True, record=False)
            ctx = p if pause else None
        else:
            text, stop = eng.transcribe(p, vad=True, record=False), None
        took += time.monotonic() - t0
        if text and held:
            seam = E.after_held_stop(text, stop)
            text = seam.lstrip(". ")
            if seam.startswith("."):
                parts[-1] += "."
        elif held and final:
            parts[-1] += "."
        if text:
            hold = E.hold_stop if mode == "0.7.6" else old_hold
            held = not final and hold(text, pause)
            parts.append(text[:-1] if held else text)
    return " ".join(parts), took, len(pieces)


def words_cm(t):
    return [w for w in t.split() if re.search(r"\w", w)]


def bare(w):
    return re.sub(r"[^\w']", "", w).lower()


def score(ref, hyp):
    r, h = words_cm(ref), words_cm(hyp)
    rb, hb = [bare(w) for w in r], [bare(w) for w in h]
    sm = difflib.SequenceMatcher(None, rb, hb, autojunk=False)
    c = dict(mid_caps=0, lost_caps=0, false_stops=0, lost_stops=0, errors=0, ref_words=len(r))
    ex = []
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op != "equal":
            c["errors"] += max(a2 - a1, b2 - b1)
            continue
        for i, j in zip(range(a1, a2), range(b1, b2)):
            rw, hw = r[i], h[j]
            if rb[i] not in ("i", "i'm", "i'll", "i've", "i'd"):
                if hw[:1].isupper() and rw[:1].islower():
                    c["mid_caps"] += 1
                    ex.append(" ".join(h[max(0, j - 3):j + 2]))
                if hw[:1].islower() and rw[:1].isupper():
                    c["lost_caps"] += 1
            rs, hs = rw[-1] in ".?!", hw[-1] in ".?!"
            if i < len(r) - 1:
                c["false_stops"] += hs and not rs
                c["lost_stops"] += rs and not hs
    return c, ex


def main():
    d = Path(sys.argv[1])
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 5
    meta = [json.loads(line) for line in open(d / "metadata.jsonl")]
    meta = [m for m in meta if m["subset"] in SUBSETS and m["duration_s"] > 3.5]
    E.CONTEXT_S = float(os.environ.get("CONTEXT_S", E.CONTEXT_S))
    out_ctx = E.CONTEXT_S
    eng = E.Engine()
    eng.load(next((MODELS / "sabich").iterdir()), 8)
    clips = []
    for m in meta:
        x = read_wav(d / m["file_name"])
        cut = split_point(eng, x)
        if cut is not None:
            clips.append((x, cut, m["text"].strip()))
    takes = []
    for t in range(0, len(clips) - PER_TAKE + 1, PER_TAKE):
        audio, refs = [], []
        for i, (x, cut, ref) in enumerate(clips[t:t + PER_TAKE]):
            audio += [x[:cut], quiet(MID_GAPS[(t + i) % len(MID_GAPS)]), x[cut:]]
            if i < PER_TAKE - 1:
                audio.append(quiet(BETWEEN_GAPS[(t + i) % len(BETWEEN_GAPS)]))
            refs.append(ref if ref[-1] in ".?!" else ref + ".")
        takes.append((np.concatenate(audio), " ".join(refs)))
    out = {"interval_s": interval, "context_s": out_ctx, "takes": len(takes), "clips": len(takes) * PER_TAKE,
           "audio_min": round(sum(len(a) for a, _ in takes) / SR / 60, 1), "setups": {}}
    for mode in os.environ.get("SETUPS", "0.7.5 0.7.6 whole").split():
        tot, took, npieces, exs = {}, 0.0, 0, []
        for a, ref in takes:
            hyp, t, n = run_take(eng, a, interval, mode)
            c, ex = score(ref, hyp)
            for k, v in c.items():
                tot[k] = tot.get(k, 0) + v
            took, npieces, exs = took + t, npieces + n, exs + ex
        tot["wer"] = round(tot.pop("errors") / tot["ref_words"], 4)
        tot.update(pieces=npieces, decode_s=round(took, 1), mid_caps_examples=exs[:12])
        out["setups"][mode] = tot
        print(mode, json.dumps({k: v for k, v in tot.items() if k != "mid_caps_examples"}), flush=True)
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
