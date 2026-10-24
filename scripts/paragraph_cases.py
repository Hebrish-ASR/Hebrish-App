# /// script
# requires-python = ">=3.10"
# dependencies = ["onnxruntime>=1.17", "tokenizers>=0.15", "numpy", "huggingface_hub"]
# ///
"""Regenerate shared/paragraph-cases.json from its own inputs with the reference implementation.

  uv run scripts/paragraph_cases.py [--revision <hf sha>]

Downloads paragraphs.py and onnx/ from danielrosehill/MiniLM-L12-ASR-Paragraph-Breaks (Hub) and
recomputes word_pieces, windows, probs_int8 and output for every case. Spec: shared/paragraphs.md.
"""
import argparse
import importlib.util
import json
from pathlib import Path

from huggingface_hub import snapshot_download

REPO = "danielrosehill/MiniLM-L12-ASR-Paragraph-Breaks"
CASES = Path(__file__).resolve().parent.parent / "shared" / "paragraph-cases.json"

ap = argparse.ArgumentParser()
ap.add_argument("--revision", default=None)
a = ap.parse_args()
d = Path(snapshot_download(REPO, revision=a.revision, allow_patterns=["onnx/*", "paragraphs.py"]))
spec = importlib.util.spec_from_file_location("paragraphs", d / "paragraphs.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
tok, sess, thr = P.load(local=d / "onnx")
unk = tok.token_to_id("[UNK]")
data = json.loads(CASES.read_text())
for c in data["cases"]:
    words = c["input"].split()
    pieces = [e.ids or [unk] for e in tok.encode_batch(words, add_special_tokens=False)]
    c["word_pieces"] = pieces
    c["windows"] = [list(w) for w in P.windows(pieces)] if words else []
    c["probs_int8"] = [round(p, 5) for p in P.word_probs(tok, sess, words)] if words else []
    c["output"] = P.paragraphs(c["input"], tok, sess, thr)
data["threshold"] = thr
CASES.write_text(json.dumps(data, indent=1, ensure_ascii=False))
print(f"{len(data['cases'])} cases, threshold {thr}")
