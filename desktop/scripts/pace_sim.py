#!/usr/bin/env python3
"""Insert-as-you-go pacing, simulated: when text would be pasted, and in what pieces.

    .venv/bin/python scripts/pace_sim.py . <examples dir> <models dir> parakeet
    IVS="3 5" .venv/bin/python scripts/pace_sim.py . <examples dir> <models dir> parakeet
    .venv/bin/python scripts/pace_sim.py . <examples dir> <models dir> shak phrase sentence word

<examples dir>: the Hugging Face demo Space's `examples/` folder (six code-switched WAVs and
examples.json; the same clips as "Live insertion" in docs/maintaining.md). <models dir>: ~/.local/share/hebrish/models (needs `sabich` and
`shakshuka` downloaded). The six clips are joined with gaps of quiet noise ("thinking": 0.4-2.5 s,
"flowing": 0.4-0.5 s) and played in 0.5 s ticks like Controller._live_tick: Parakeet through
engine.live_split, the held full stop and after_held_stop (as Controller._worker), Shakshuka
through LiveStream with a simulated clock. Times are when a paste would happen (real decode time
on this machine). Results 2026-10-22: docs/maintaining.md, "Insert-as-you-go pacing (0.7.1)"."""
import json, re, sys, time
from pathlib import Path
import numpy as np, wave
class sf:
    @staticmethod
    def read(p, dtype=None):
        w = wave.open(str(p)); a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        return (a.reshape(-1, w.getnchannels()).mean(1) if w.getnchannels() > 1 else a), w.getframerate()
desk, exdir, mdir = map(Path, sys.argv[1:4])
sys.path.insert(0, str(desk))
from hebrish import engine as E
SR = 16000
import os
IVS = [int(v) for v in os.environ.get("IVS", "5 7").split()]
ex = json.load(open(exdir / "examples.json"))
gap_sets = {"thinking": [0.5, 1.4, 0.4, 2.5, 0.7], "flowing": [0.4, 0.5, 0.4, 0.45, 0.5]}
rng = np.random.default_rng(1)
def build(gaps):
    parts, refs = [], []
    for i, e in enumerate(ex[:6]):
        x, sr = sf.read(exdir / Path(e["file"]).name, dtype="float32")
        assert sr == SR
        parts.append(x)
        refs.append(e["text"])
        if i < 5:
            parts.append((rng.standard_normal(int(gaps[i] * SR)) * 0.002).astype(np.float32))
    return np.concatenate(parts), " ".join(refs)
def norm(s): return re.sub(r"[^\w' ]", " ", s.lower()).split()
def wer(r, h):
    r, h = norm(r), norm(h); d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        p, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            p, d[j] = d[j], min(d[j] + 1, d[j-1] + 1, p + (r[i-1] != h[j-1]))
    return d[len(h)], len(r)
def model(name):
    return next((mdir / name).iterdir())
def run_parakeet(eng, x, interval):
    out, consumed, free, t, held, txt_all = [], 0, 0.0, 0.0, False, ""
    end = len(x) / SR + 0.3
    split = getattr(E, "live_split", None)
    while t < end:
        t += 0.5
        buf = x[consumed:int(min(t, len(x) / SR) * SR)]
        final = t >= end
        if final: cut, pause = len(buf), None
        else:
            r = split(buf, interval) if split else ((E.live_cut(buf, interval), 0.5) if E.live_cut(buf, interval) else None)
            if not r: continue
            cut, pause = r
        t0 = time.monotonic(); txt = eng.transcribe(buf[:cut], vad=True); d = time.monotonic() - t0
        free = max(t, free) + d; consumed += cut
        if not split:
            if txt: out.append((round(free, 1), consumed / SR, txt + " "))
            continue
        lead = ""
        if txt and held:
            seam = E.after_held_stop(txt); txt = seam.lstrip(". "); lead = seam[:len(seam)-len(txt)]
        elif held and final:
            out.append((round(free, 1), consumed / SR, ".")); held = False
        if txt:
            held = not final and E.hold_stop(txt, pause)
            txt = txt[:-1] if held else txt
            out.append((round(free, 1), consumed / SR, lead + txt + ("" if held else " ")))
    return out
def run_shak(eng, x, release):
    ls = eng.live(release); out, t, step = [], 0.0, SR // 2
    for i in range(0, len(x), step):
        t += 0.5
        last = i + step >= len(x)
        txt = ls._decode(x[i:i + step], last)
        r = ls._release(txt, last, now=t)
        if r: out.append((round(t, 1), r))
    return out
if __name__ == "__main__":
    which = sys.argv[4]
    eng = E.Engine()
    if which == "parakeet":
        eng.load(model("sabich"), 6)
        for g, gaps in gap_sets.items():
            x, ref = build(gaps)
            for iv in IVS:
                o = run_parakeet(eng, x, iv)
                hyp = "".join(p[2] for p in o)
                e, n = wer(ref, hyp)
                print(f"\n== {g} interval {iv}: {len(o)} pieces, WER {e}/{n}, take {len(x)/SR:.1f}s")
                for p in o: print(f"  {p[0]:5.1f}s (audio to {p[1]:5.1f}) | {p[2]!r}")
                print("  TEXT:", hyp)
    else:
        eng.load(model("shakshuka"), 6, streaming=True)
        for g, gaps in gap_sets.items():
            x, ref = build(gaps)
            for rel in sys.argv[5:]:
                o = run_shak(eng, x, rel)
                hyp = "".join(p[1] for p in o)
                e, n = wer(ref, hyp)
                ws = [len(p[1].split()) for p in o]
                print(f"\n== {g} {rel}: {len(o)} pastes, words/paste {ws}, WER {e}/{n}")
                for p in o: print(f"  {p[0]:5.1f}s | {p[1]!r}")
