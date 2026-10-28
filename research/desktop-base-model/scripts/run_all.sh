#!/bin/bash
# Run every model in turn on CPU (16 threads each), then score. From research/desktop-base-model/:
#   uv venv .venv && uv pip install -p .venv sherpa-onnx faster-whisper onnx-asr onnxruntime numpy huggingface_hub
#   desktop/.venv/bin/python scripts/build_takes.py <bench data/test> <disfluent snapshot> work/takes.npz   (once)
#   scripts/run_all.sh
cd "$(dirname "$0")/.."
D=../../desktop/.venv/bin/python
$D scripts/run_model.py sabich work/takes.npz work/out_sabich.json > work/log_sabich.txt 2>&1
for m in canary whisper qwen3; do .venv/bin/python scripts/run_model.py $m work/takes.npz work/out_$m.json > work/log_$m.txt 2>&1; done
$D scripts/score.py work/takes.json work results.json
