# Desktop base model: one that does not break sentences at pauses

## Question

Daniel, 2026-10-28: Sabich (Parakeet TDT 0.6B v2) puts full stops and capitals in the middle of
sentences after thinking pauses, fillers and stop/restart, and it feels worse than Whisper did.
Keep Parakeet as the recommended model on phones, and find out whether a different base would be
a significant improvement **for this failure** on the desktop app. Diagnosis:
[docs/debug-log/2026-10-28-false-sentence-breaks-remain.md](../../docs/debug-log/2026-10-28-false-sentence-breaks-remain.md).

## Status

answered (2026-10-28). Comparison approved by Daniel and run on 2026-10-28 on the laptop CPU; no
GPU or cloud use. Raw numbers: [`results.json`](results.json); method below, scripts in
[`scripts/`](scripts/).

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

## Measured (2026-10-28)

### Method

- **Material (V).** `scripts/build_takes.py` builds the takes with `desktop/scripts/seam_bench.py`'s own
  functions: benchmark test-split clips (HF `Hebrish/English-Hebrew-Codeswitching-ASR-Benchmark`,
  subsets clean, desktop_mic, english_control, over 3.5 s), each with one 0.7/1.0/1.4/2.0 s pause
  inserted inside the sentence before a lowercase word, four clips to a take with 0.8-2.0 s between
  them: 27 takes, 19.3 min, 2,571 reference words. Disfluent: the first 30 recordings of
  `Hebrish/Disfluent-Read-Sentences` (6.9 min, 718 words; plain English, real fillers). Stop/restart:
  the first 14 takes, cut in the middle of one inside-sentence pause. Subsets were capped to keep the
  whole run near an hour of laptop CPU.
- **Runtimes (V)**, all CPU, 16 threads, int8, 1 s of silence appended:
  - Sabich v2.2: sherpa-onnx 2.0.1 transducer (the app's model and engine). Two paths:
    **raw** = one decode of the whole take; **app** = `Engine.transcribe(vad=True)` (voice-detection
    edits `shorten_silences`/`stretch_pauses`, pieces of ~10 s cut at pauses).
  - `Qwen/Qwen3-ASR-0.6B`: sherpa-onnx 2.0.1 `from_qwen3_asr`, int8 export
    `sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25`. Text prompt = stream option `hotwords`, which
    sherpa-onnx places in the system turn (Qwen3-ASR's context slot; (I) from the sherpa-onnx source,
    the official transformers/GGUF route was not run).
  - `openai/whisper-large-v3-turbo`: faster-whisper 1.2.1 (CTranslate2 4.8.4) int8,
    `mobiuslabsgmbh/faster-whisper-large-v3-turbo`, language en, beam 1, no VAD filter; prompt =
    `initial_prompt`.
  - `nvidia/canary-1b-v2`: onnx-asr 0.12.0 (onnxruntime 1.31.1) int8 export
    `istupakov/canary-1b-v2-onnx`, language en, punctuation on. No text prompt.
- **Scoring (V)** (`scripts/score.py`): `seam_bench.score` (mid-sentence capitals, false stops, lost
  stops, WER), plus **false breaks**: a `.?!` where the reference has none, followed by a capital
  (not "I"). False breaks are the failure itself; mid-sentence capitals also count the stock
  models writing an unknown romanized Hebrew term as a name ("a Kaspomat"), a vocabulary effect.
  WER is a side column only: the stock models are not trained on romanized Hebrew terms, so their
  WER on the code-switched takes says nothing about the failure.
- **Machine (V).** 16 threads, 13 GB RAM, no CUDA, shared with other jobs during the run (load
  average 10-19), so timings are upper bounds.

### Results

Test 1, pauses inside sentences, per 100 reference words (count in brackets):

| Model, path | Takes: false breaks | mid caps | false stops | lost stops | WER (side) | Disfluent: false breaks | mid caps | false stops | WER (side) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Sabich v2.2, raw (whole take) | **0.04** (1) | 0.54 | 0.12 | 0.12 | 7.7% | **0.14** (1) | 0.14 | 0.14 | 0.1% |
| Sabich v2.2, app path | 0.54 (14) | 1.63 | 0.78 | 0.23 | 11.6% | 0.28 (2) | 0.28 | 0.42 | 0.4% |
| Whisper large-v3-turbo | 0.19 (5) | 1.48 | 0.27 | 0.12 | 13.1% | 0.84 (6) | 1.39 | 1.11 | 1.5% |
| Canary-1b-v2 | 0.43 (11) | 1.79 | 0.74 | 0.08 | 13.9% | 0.97 (7) | 1.25 | 1.25 | 2.8% |
| Qwen3-ASR-0.6B | 1.17 (30) | 1.94 | 1.36 | 0.04 | 11.6% | 1.53 (11) | 1.81 | 1.67 | 2.9% |

Typical stock-model break on the disfluent set: "a short list of questions to ask at the optician.
Because I need a new pair of glasses" (Whisper, Canary and Qwen3 alike) (V).

Test 2, stop/restart (14 takes, cut inside a sentence):

| Model, variant | First half ends with a false stop | Second half starts with a wrong capital |
| --- | --- | --- |
| Sabich v2.2, raw, second half alone | 8/14 | 10/14 |
| Sabich v2.2, app path, second half alone | 7/14 | 7/14 |
| Sabich v2.2, audio context (`transcribe_after`, last 3 s of the first half) | 1/14 (model ends the context with a mark) | **0/14** |
| Whisper turbo, alone | 13/14 | 6/14 |
| Whisper turbo, `initial_prompt` = first half's text | 13/14 | 9/14 |
| Whisper turbo, prompt with its final stop removed | 13/14 | 3/14 |
| Canary-1b-v2, alone (no prompt) | 14/14 | 10/14 |
| Qwen3-ASR-0.6B, alone | 14/14 | 12/14 |
| Qwen3-ASR-0.6B, context = first half's text (with or without final stop) | 14/14 | 12/14 |

Test 3, CPU real-time factor (decode time / audio time, median of 3 after a warm-up; second timing
pass 22:42-22:47 local time; lower is faster):

| Model | Runtime, quantisation | ~10 s clip | ~30 s clip |
| --- | --- | --- | --- |
| Sabich v2.2 | sherpa-onnx 2.0.1 transducer, int8 | 0.097 (app path 0.083) | 0.092 (app path 0.110) |
| Canary-1b-v2 | onnx-asr 0.12.0 / onnxruntime, int8 | 0.19 | 0.31 |
| Qwen3-ASR-0.6B | sherpa-onnx 2.0.1, int8 | 0.38 | 0.67 |
| Whisper large-v3-turbo | faster-whisper 1.2.1 / CTranslate2, int8 | 0.87 | 0.61 |

Whisper's cost is per 30 s window, so a 10 s piece costs nearly as much as 30 s (8.7 s vs 18.3 s) (V).

### Findings from the measurements

5. **No stock candidate breaks fewer sentences than Sabich (V).** On the same audio, Sabich decoding
   the whole take made 1 false break in 2,571 words; Whisper 5, Canary 11, Qwen3-ASR-0.6B 30. On real
   fillers (disfluent set) Sabich made 1 in 718 words, the stock models 6-11. The proposed first choice,
   Qwen3-ASR-0.6B, was the worst on both sets. Caveat (I): Sabich is fine-tuned on this one speaker and
   the stock models are not; and a fine-tuned candidate could behave differently from its stock base.
   Disfluency recordings are outside the default Sabich training blend (`DEFAULT_TASK_TAGS` in
   ASR-Training), so the disfluent set is not training data for it (I, v2.2's run options not checked).
6. **The app's decoding path adds most of Sabich's breaks (V).** The same model on the same takes: 1
   false break as one decode, 14 through `Engine.transcribe(vad=True)` (mid-sentence capitals 0.54 vs
   1.63 per 100 words). Which part is responsible (piece cuts at pauses, or the pause edits
   `shorten_silences`/`stretch_pauses`) was not separated (I: the piece cuts, since a piece cut at a
   pause is decoded as a finished clip).
7. **Stop/restart is not solved by any base on its own (V).** Every model ends a half-sentence with a
   full stop most of the time (Sabich 7-8/14, stock models 13-14/14). For the restart, Sabich with
   audio context gave 0/14 wrong capitals; the best text prompt was Whisper with the previous text's
   final stop removed (3/14). The Qwen3-ASR context (via sherpa-onnx) changed nothing (12/14).
8. **Speed (V, on a loaded machine).** Only Sabich and Canary stay well under real time on short
   pieces; Qwen3-ASR-0.6B slows with length (0.38 to 0.67); Whisper turbo spends ~8.7 s on any piece
   up to 30 s, too slow for the app's live pieces without a different piece strategy (I).

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
4. GPU runs, if any were needed, on Modal (none were).

## Recommendation

Do not change the desktop base model for this failure (2026-10-28). None of Qwen3-ASR-0.6B, Whisper
large-v3-turbo or Canary-1b-v2 breaks fewer sentences than Sabich on the same audio, and all three are
2-9 times slower on CPU. The breaks Daniel sees come mostly from how the app feeds Sabich, and from
stop/restart, which no base handles alone. Next steps, in the debug log's order:

1. Context across takes (debug log option 1): decode a take that starts soon after the last one after
   the last 3 s of it, and remove the pasted full stop when the model continues the sentence. Measured
   here: 0/14 wrong capitals with audio context.
2. Find which part of the app path adds the breaks (14 vs 1 on the same takes): run `seam_bench.py`
   with the pause edits off, and with longer pieces or a whole-take re-decode where latency allows.
3. Keep the pause/mid-sentence dataset (option 3) for the next Sabich round.

Revisit a base change only if a fine-tuned candidate is benchmarked with the pause dataset.
