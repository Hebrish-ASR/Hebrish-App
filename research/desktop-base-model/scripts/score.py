#!/usr/bin/env python3
"""Score the hypotheses of run_model.py against the references; write results.json.

    <python> score.py <takes.json> <out_dir with out_<model>.json> <results.json>

Whole decodes (takes, disfluent): desktop/scripts/seam_bench.py `score` (alignment on lowercased words;
mid_caps = capitalised where the reference is lowercase, not "I"; false_stops = .?! where the
reference has none, last word excluded; lost_stops the reverse; lost_caps; WER with case and marks
stripped). Rates are per 100 reference words.

Stop/restart (one cut per take, inside a sentence, before a lowercase word):
- first_false_stop: the first half's text ends with .?! (the reference continues the sentence);
- second_wrong_cap: the second half's first word is capitalised while the reference word it aligns to
  (first + second text aligned to the take's reference) is lowercase; not "I".
false_breaks (added 2026-10-28): the failure itself. A .?! after a word whose reference has no mark (not the
last reference word), and the next hypothesis word capitalised (not "I"). Unlike mid_caps it does not count
stock models writing an unknown romanized Hebrew term as a capitalised name ("a Kaspomat"), which is a
vocabulary effect, not a sentence break.
Sabich `ctx`: Engine.transcribe_after(rest of the sentence, context = first half): wrong cap as above
on its text, false stop = the model ended the context with a mark (`ctx_stop`).
"""
import difflib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "desktop/scripts"))
import seam_bench as sb  # noqa: E402

KEYS = ("mid_caps", "false_stops", "lost_stops", "lost_caps")
I_WORDS = ("i", "i'm", "i'll", "i've", "i'd")


def false_breaks(ref, hyp):
    r, h = sb.words_cm(ref), sb.words_cm(hyp)
    sm = difflib.SequenceMatcher(None, [sb.bare(x) for x in r], [sb.bare(x) for x in h], autojunk=False)
    n, ex = 0, []
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op != "equal":
            continue
        for i, j in zip(range(a1, a2), range(b1, b2)):
            if i < len(r) - 1 and j < len(h) - 1 and h[j][-1] in ".?!" and r[i][-1] not in ".?!":
                nxt = h[j + 1]
                if nxt[:1].isupper() and sb.bare(nxt) not in I_WORDS:
                    n += 1
                    ex.append(" ".join(h[max(0, j - 2):j + 3]))
    return n, ex


def total(pairs):
    tot = dict.fromkeys(KEYS + ("errors", "ref_words", "false_breaks"), 0)
    ex, bex = [], []
    for ref, hyp in pairs:
        c, e = sb.score(ref, hyp)
        c["false_breaks"], b = false_breaks(ref, hyp)
        for k in tot:
            tot[k] += c[k]
        ex += e
        bex += b
    n = tot["ref_words"]
    out = {k: tot[k] for k in KEYS + ("false_breaks",)}
    out["false_breaks_per100w"] = round(100 * tot["false_breaks"] / n, 2)
    out["false_breaks_examples"] = bex[:6]
    out.update({f"{k}_per100w": round(100 * tot[k] / n, 2) for k in KEYS})
    out.update(wer=round(tot["errors"] / n, 4), ref_words=n, items=len(pairs), mid_caps_examples=ex[:6])
    return out


def wrong_cap(ref, first, second):
    """Second half's first word capitalised against a lowercase reference word (None: no text)."""
    h2 = sb.words_cm(second)
    if not h2:
        return None
    w = h2[0]
    if sb.bare(w) in I_WORDS or not w[:1].isupper():
        return False
    r, h = sb.words_cm(ref), sb.words_cm(first) + h2
    j = len(sb.words_cm(first))
    sm = difflib.SequenceMatcher(None, [sb.bare(x) for x in r], [sb.bare(x) for x in h], autojunk=False)
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op == "equal" and b1 <= j < b2:
            return r[a1 + j - b1][:1].islower()
    return True                          # unaligned: the cut is before a lowercase word by construction


def rate(xs):
    xs = [x for x in xs if x is not None]
    return dict(n=len(xs), count=sum(xs), rate=round(sum(xs) / len(xs), 3) if xs else None)


META = dict(
    date="2026-10-28",
    machine="laptop CPU, 16 threads, 13 GB RAM, no CUDA; shared with other jobs (load average 10-19 during the runs)",
    material="27 seam_bench takes (19.3 min, benchmark test split, one 0.7-2.0 s pause inside every sentence); "
             "first 30 Hebrish/Disfluent-Read-Sentences recordings (6.9 min); stop/restart on the first 14 takes",
    runtimes=dict(
        sabich="Sabich v2.2 (Parakeet TDT 0.6B v2 fine-tune), sherpa-onnx 2.0.1 transducer, int8; raw = one decode of the "
               "whole take, app = desktop Engine.transcribe(vad=True): voice-detection edits, ~10 s pieces cut at pauses",
        qwen3="Qwen/Qwen3-ASR-0.6B, sherpa-onnx 2.0.1 from_qwen3_asr, int8 export sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25; "
              "prompt = stream option hotwords (system turn)",
        whisper="openai/whisper-large-v3-turbo, faster-whisper (CTranslate2) int8, mobiuslabsgmbh/faster-whisper-large-v3-turbo, "
                "language en, beam 1, no VAD filter; prompt = initial_prompt",
        canary="nvidia/canary-1b-v2, onnx-asr int8 export istupakov/canary-1b-v2-onnx, language en, pnc on; no text prompt"),
)


def main():
    meta = json.loads(Path(sys.argv[1]).read_text())
    refs = {t["name"]: t["ref"] for t in meta["takes"] + meta["disfluent"]}
    res = {"_meta": META}
    for f in sorted(Path(sys.argv[2]).glob("out_*.json")):
        o = json.loads(f.read_text())
        name = o["model"]
        r = res[name] = {}
        for key in ("takes", "dis"):
            if key in o:
                r[key] = total([(refs[x["name"]], x["hyp"]) for x in o[key]])
                r[key]["audio_min"] = round(sum(x["audio_s"] for x in o[key]) / 60, 1)
                r[key]["decode_s"] = round(sum(x["decode_s"] for x in o[key]), 1)
                if "hyp_app" in o[key][0]:
                    r[key + "_app"] = total([(refs[x["name"]], x["hyp_app"]) for x in o[key]])
        if "restart" in o:
            rs = o["restart"]
            rr = r["restart"] = {}
            variants = [("alone", "first", "second")]
            if "second_prompt" in rs[0]:
                variants += [("prompt", "first", "second_prompt"), ("prompt_nostop", "first", "second_prompt_nostop")]
            if "first_app" in rs[0]:
                variants += [("app_alone", "first_app", "second_app")]
            for v, a, b in variants:
                rr[v] = dict(first_false_stop=rate([x[a].rstrip()[-1:] in ".?!" if x[a].strip() else None for x in rs]),
                             second_wrong_cap=rate([wrong_cap(refs[x["name"]], x[a], x[b]) for x in rs]),
                             joined=total([(refs[x["name"]], x[a] + " " + x[b]) for x in rs]))
                rr[v]["joined"].pop("mid_caps_examples")
                rr[v]["joined"].pop("false_breaks_examples")
            if "second_ctx" in rs[0]:
                rr["audio_ctx"] = dict(
                    seam_false_stop=rate([x["ctx_stop"] for x in rs]),
                    second_wrong_cap=rate([wrong_cap(refs[x["name"]], x["first_app"], x["second_ctx"]) for x in rs]))
        if "speed" in o:
            r["speed"] = o["speed"]
        r["load_s"] = o.get("load_s")
    Path(sys.argv[3]).write_text(json.dumps(res, indent=1))
    res.pop("_meta")
    print(json.dumps({m: {k: (v if k == "speed" else {kk: vv for kk, vv in v.items() if not kk.endswith("_examples")} if isinstance(v, dict) else v)
                         for k, v in r.items()} for m, r in res.items()}, indent=1))


if __name__ == "__main__":
    main()
