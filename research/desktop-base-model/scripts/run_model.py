#!/usr/bin/env python3
"""Decode the test material (build_takes.py) with one model on CPU and save hypotheses and timings.

    <python> run_model.py <model> <takes.npz> <out.json> [tasks]

model: sabich | qwen3 | whisper | canary. tasks (default all): takes dis restart speed.
Sabich runs under desktop/.venv (the app's sherpa-onnx); the others under this folder's .venv.

Runtimes (CPU, THREADS threads):
- sabich: sherpa-onnx OfflineRecognizer transducer, int8 (~/.local/share/hebrish/models/sabich), via
  desktop/hebrish/engine.py. Two paths: `app` = Engine.transcribe(vad=True) (shorten_silences,
  stretch_pauses, pieces of ~10 s) and `raw` = one decode of the whole audio (normalize + 1 s tail pad).
- qwen3: sherpa-onnx OfflineRecognizer.from_qwen3_asr, int8 export sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25
  of Qwen/Qwen3-ASR-0.6B; prompt = per-stream option `hotwords`, which sherpa-onnx puts in the system
  turn of the chat template (Qwen3-ASR's context slot). sherpa-onnx turns commas in it into spaces.
- whisper: faster-whisper (CTranslate2) int8, mobiuslabsgmbh/faster-whisper-large-v3-turbo (conversion of
  openai/whisper-large-v3-turbo), language en, greedy (beam_size 1), no VAD filter; prompt = initial_prompt.
- canary: onnx-asr, istupakov/canary-1b-v2-onnx int8 (export of nvidia/canary-1b-v2), language en, pnc on.
  No text prompt.
"""
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

SR = 16000
THREADS = 16
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STOPS = ".?!"
# Laptop CPU budget (~1 h for all four models): every take for test 1, the first N_DIS disfluent
# recordings, the first N_RESTART takes for stop/restart.
N_DIS = 30
N_RESTART = 14


def pad(x):
    """1 s of silence after the audio, as the app's TAIL_PAD_S (without it Qwen3 and Canary dropped the last word)."""
    return np.concatenate([x, np.zeros(SR, np.float32)])


class Sabich:
    prompt = False

    def __init__(self):
        sys.path.insert(0, str(ROOT / "desktop"))
        from hebrish import engine as E
        self.E = E
        self.eng = E.Engine()
        self.eng.load(next((Path.home() / ".local/share/hebrish/models/sabich").iterdir()), THREADS)

    def decode(self, x):                      # raw: one decode, no voice-detection edits
        E = self.E
        y = np.concatenate([E.normalize(x), np.zeros(int(E.TAIL_PAD_S * SR), np.float32)])
        with self.eng._lock:
            return self.eng._decode_piece(y)[0]

    def app(self, x):
        return self.eng.transcribe(x, vad=True, record=False)

    def after(self, x, ctx):
        return self.eng.transcribe_after(x, ctx, vad=True, record=False)


class Qwen3:
    prompt = True

    def __init__(self):
        import sherpa_onnx
        d = HERE.parent / "models/sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25"
        self.rec = sherpa_onnx.OfflineRecognizer.from_qwen3_asr(
            conv_frontend=str(d / "conv_frontend.onnx"), encoder=str(d / "encoder.int8.onnx"),
            decoder=str(d / "decoder.int8.onnx"), tokenizer=str(d / "tokenizer"), num_threads=THREADS,
            max_total_len=2048, max_new_tokens=512)

    def decode(self, x, prompt=None):
        s = self.rec.create_stream()
        if prompt:
            s.set_option("hotwords", prompt)
        s.accept_waveform(SR, pad(x))
        self.rec.decode_stream(s)
        return s.result.text.strip()


class Whisper:
    prompt = True

    def __init__(self):
        from faster_whisper import WhisperModel
        self.m = WhisperModel("mobiuslabsgmbh/faster-whisper-large-v3-turbo", device="cpu",
                              compute_type="int8", cpu_threads=THREADS)

    def decode(self, x, prompt=None):
        segs, _ = self.m.transcribe(pad(x), language="en", beam_size=1, vad_filter=False, initial_prompt=prompt or None)
        return " ".join(s.text.strip() for s in segs).strip()


class Canary:
    prompt = False

    def __init__(self):
        import onnx_asr
        import onnxruntime as rt
        so = rt.SessionOptions()
        so.intra_op_num_threads = THREADS
        self.m = onnx_asr.load_model("nemo-canary-1b-v2", "istupakov/canary-1b-v2-onnx", quantization="int8",
                                     sess_options=so, providers=["CPUExecutionProvider"])

    def decode(self, x):
        return str(self.m.recognize(pad(x), language="en", pnc=True)).strip()


MODELS = dict(sabich=Sabich, qwen3=Qwen3, whisper=Whisper, canary=Canary)


def timed(f, *a):
    t0 = time.monotonic()
    r = f(*a)
    return r, round(time.monotonic() - t0, 3)


def main():
    name, npz, out = sys.argv[1], np.load(sys.argv[2]), Path(sys.argv[3])
    meta = json.loads(Path(sys.argv[2]).with_suffix(".json").read_text())
    tasks = sys.argv[4].split(",") if len(sys.argv) > 4 else ["takes", "dis", "restart", "speed"]
    res = json.loads(out.read_text()) if out.exists() else {}
    t0 = time.monotonic()
    m = MODELS[name]()
    res["model"], res["load_s"], res["threads"] = name, round(time.monotonic() - t0, 1), THREADS
    is_sabich = name == "sabich"
    if "takes" in tasks or "dis" in tasks:
        for key, items in (("takes", meta["takes"]), ("dis", meta["disfluent"][:N_DIS])):
            if key not in tasks:
                continue
            rows = []
            for it in items:
                x = npz[it["name"]]
                h, t = timed(m.decode, x)
                row = dict(name=it["name"], hyp=h, decode_s=t, audio_s=round(len(x) / SR, 2))
                if is_sabich:
                    row["hyp_app"], row["decode_s_app"] = timed(m.app, x)
                rows.append(row)
                print(name, key, it["name"], t, h[:80], flush=True)
            res[key] = rows
    if "restart" in tasks:
        rows = []
        for it in meta["takes"][:N_RESTART]:
            x = npz[it["name"]]
            first, second = x[: it["first_end"]], x[it["second_start"]:]
            r = dict(name=it["name"])
            r["first"], _ = timed(m.decode, first)
            r["second"], _ = timed(m.decode, second)
            if m.prompt:
                p = r["first"]
                r["second_prompt"] = m.decode(second, p)
                r["second_prompt_nostop"] = m.decode(second, p.rstrip(STOPS))
            if is_sabich:
                r["first_app"], r["second_app"] = m.app(first), m.app(second)
                text, stop = m.after(x[it["second_start"]: it["second_sent_end"]], first)
                r["second_ctx"], r["ctx_stop"] = text, stop
            rows.append(r)
            print(name, "restart", it["name"], repr(r["first"][-30:]), "|", repr(r["second"][:30]), flush=True)
        res["restart"] = rows
    if "speed" in tasks:
        sp = {}
        f = m.app if is_sabich else m.decode
        m.decode(npz["speed10"])            # warm-up
        for k in ("speed10", "speed30"):
            x = npz[k]
            ts = [timed(m.decode, x)[1] for _ in range(3)]
            row = dict(audio_s=len(x) / SR, decode_s=ts, rtf=round(statistics.median(ts) / (len(x) / SR), 4))
            if is_sabich:
                ta = [timed(f, x)[1] for _ in range(3)]
                row.update(decode_s_app=ta, rtf_app=round(statistics.median(ta) / (len(x) / SR), 4))
            sp[k] = row
            print(name, k, row, flush=True)
        res["speed"] = sp
    out.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
