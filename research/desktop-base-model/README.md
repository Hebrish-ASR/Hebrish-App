# Desktop base model: one that does not break sentences at pauses

## Question

Daniel, 2026-10-28: Sabich (Parakeet TDT 0.6B v2) puts full stops and capitals in the middle of
sentences after thinking pauses, fillers and stop/restart, and it feels worse than Whisper did.
Keep Parakeet as the recommended model on phones, and find out whether a different base would be
a significant improvement **for this failure** on the desktop app. Diagnosis:
[docs/debug-log/2026-10-28-false-sentence-breaks-remain.md](../../docs/debug-log/2026-10-28-false-sentence-breaks-remain.md).

## Status

open (2026-10-28). Comparison approved by Daniel on 2026-10-28; not yet run.

## Findings

1. **What the failure needs (I, from the architectures).** Two properties:
   - a decoder that reads its own text (attention encoder-decoder or LLM decoder), so a sentence ends
     when the words complete one, not at a pause. Parakeet's transducer prediction network is small
     and follows the audio;
   - a text prompt, so the previous take's text can be given to the next take (fixes stop/restart).
     Parakeet takes no text input; audio context (`transcribe_after`) is the only workaround.
2. **Constraint (V, 2026-10-28).** The desktop app decodes on CPU. The development laptop has 16
   threads, 13 GB RAM and an AMD integrated GPU with no CUDA. Models of 2B parameters or more
   (Canary-Qwen-2.5B, Granite Speech 2B, Voxtral, Sabich-Qwen3-ASR-1.7B) are unlikely to keep up
   with live dictation there (I).
3. **Candidates** (from the private scouting repo `English-Hebrew-Codeswitching-ASR-Candidates`,
   surveyed 2026-10-15, and the above):

| Candidate | Decoder reads its text | Text prompt | CPU path | Notes |
| --- | --- | --- | --- | --- |
| `Qwen/Qwen3-ASR-0.6B` | yes (Qwen3 LLM) | yes (context) | official GGUF, `ggml-org/Qwen3-ASR-0.6B-GGUF` | Parakeet-sized; official fine-tuning recipe; the Sabich-Qwen3-ASR-1.7B proof of concept already has the training code. **Proposed first choice.** |
| `openai/whisper-large-v3-turbo` | yes | yes (`initial_prompt`) | whisper.cpp, sherpa-onnx, faster-whisper | Whisper Hebrish v1 exists. Hallucinates in silence and repeats: needs strict voice detection. |
| `nvidia/canary-1b-v2` | yes (AED) | no | sherpa-onnx (the engine the app uses) | NeMo, so the Modal training pipeline carries over. Helps pauses, not stop/restart. |
| Parakeet TDT 0.6B v2 (Sabich) | no | no | fast | Stays the phone model. |

4. **Caveat for every base (I).** The training data is short read sentences, each ending in a full
   stop. Fine-tuning any candidate on it can teach the same "end of audio = full stop" habit; the
   scouting repo flags that LLM/AED decoders are the most likely to lose long-form behaviour from
   short clips. The pause/mid-sentence dataset (debug log, option 3) is needed whichever base wins.

## Plan (approved 2026-10-28)

Punctuation behaviour comes from the base, so stock models are compared; Hebrew word errors are not
scored (the stock models are not trained on the romanized terms).

1. **Pauses inside sentences:** benchmark clips (HF `Hebrish/English-Hebrew-Codeswitching-ASR-Benchmark`
   test split, as `desktop/scripts/seam_bench.py` builds them) with 0.7-2.0 s pauses inserted inside
   sentences, plus `Hebrish/Disfluent-Read-Sentences` for real fillers. Models: Sabich v2.2,
   stock Qwen3-ASR-0.6B, stock Whisper large-v3-turbo, stock Canary-1b-v2. Score mid-sentence
   capitals, false stops and lost stops against the reference.
   Daniel's own takes were the first choice, but the desktop app keeps no audio
   (`~/.local/share/hebrish/recordings` empty, `history.db` `audio` NULL for every row, 2026-10-28).
2. **Stop/restart:** each take split at a pause; the second half decoded with the first half's text
   as prompt where the model takes one.
3. **CPU speed:** each candidate timed on the laptop's CPU (real-time factor) against a live-dictation
   budget.
4. GPU runs on Modal; budget under US$1.

## Recommendation

Pending the comparison. If Qwen3-ASR-0.6B clearly wins on sentence breaks and keeps up on CPU, the
next Sabich round adds a Sabich-Qwen3-0.6B desktop variant trained with the pause dataset;
Parakeet-based Sabich stays recommended on Android.
