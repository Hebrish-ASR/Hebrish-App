# Post-processing after the speech model

## Question

Daniel, 2026-10-24 (R-2026-10-24-1 to -4): the fine-tunes are being trained to drop disfluencies
and to write numbers as digits, but some of that could be done deterministically after decoding,
as a fallback to the training and to get results sooner. Specifically:

1. A **disfluency chop** (*um, uh, eh, erm* …) baked into every app and every model, not a setting:
   "I can't think there's any reason why people would want those disfluencies."
2. **Numbers**: "the year was two thousand and twenty four" should come out as "the year was 2024".
   Other regex-able fixes (capitalisation).
3. **Paragraph inference** with Daniel's own model. **Dropped from Hebrish 2026-10-24** (D-2026-10-24-08):
   it needs a different architecture and is a separate project (ASR-Paragraph-Breaks), not an app stage.
4. **S1-mini by Superwhisper**, the first dedicated ASR clean-up model: can it run on a phone, is
   there a bigger one for desktop, and can the apps offer a chain (raw ASR /
   ASR + S1-mini with its control line), local in every case.

## Status

`open` (2026-10-24). Disfluency chop built (B-38, unreleased, `shared/disfluencies.md`), with *er*
included (Daniel, 2026-10-24). S1-mini by Superwhisper: desktop only, if it runs well there; on hold on
Android (D-2026-10-24-05). Paragraphs: out of scope (D-2026-10-24-08).

## Findings

### Where text is processed today

- Android: `TakeDecoder.piece()` (`android/core/.../TakeDecoder.kt`) decodes a piece, applies the
  personal dictionary, then `OutputStyle.apply` (ALL CAPS), per piece. Desktop: `hebrish/dictionary.py`
  likewise. Rules shared between the two are specified once in `shared/` with a shared test-case
  file (`shared/personal-dictionary.md`, `shared/dictionary-cases.json`). Confirmed from the code.
- Text leaves the app **piece by piece** while you speak (insert-as-you-go / type-as-you-go). A
  per-piece rule (disfluencies, most numbers) fits that; anything that needs the whole take
  (S1-mini) can only run when the take ends, and only when the take is inserted in one go.
- The Parakeet-family vocabularies cannot emit a line break at all
  (`docs/debug-log/2026-10-23-overlay-eats-line-break.md`).

### Disfluencies

- Tested patterns already exist: `ASR-Regex-Post-Processing/topics/disfluencies.md` (ICU-valid,
  i.e. they work in Android's regex engine), with risk ratings. The low-risk catch-all is
  `(?i)\b(?:u+[hm]+|e+r+m+|h+m+|a+h+)\b[,.]?\s*` followed by the cleanup rules (double spaces,
  orphan commas, re-capitalising a sentence that now starts lower case). Confirmed from the repo.
- Gaps for Hebrish: Israeli *eh / ehh / ehm* is not in the catch-all; bare *er* deletes *ER*;
  *mm* deletes millimetres; *ah* is arguably a real interjection. Inferred.
- Safe scope: hesitation sounds and stutters only. *Like*, *you know*, *I mean* and false starts
  are not regex work (meaning-dependent); they stay with the fine-tune / S1-mini.

### Numbers

- sherpa-onnx's `OfflineRecognizerConfig` has `ruleFsts` / `ruleFars` (confirmed in the bundled
  Kotlin binding, `android/app/src/main/java/com/k2fsa/sherpa/onnx/OfflineRecognizer.kt:175`): it
  can apply an inverse-text-normalisation (ITN) grammar compiled as an FST inside the recogniser.
  An English ITN grammar exists in NVIDIA's `nemo_text_processing`; whether it can be exported to
  a `.fst`/`.far` that sherpa-onnx accepts is **not verified** and would be the prototype step.
- A regex alone handles numbers badly (compounds like "two thousand and twenty four" need
  arithmetic). The practical option is a small number-word parser in code, specified once in
  `shared/` with shared test cases, as the personal dictionary is.
- Must stay conservative: "one of the", "a couple of two things", "the two of us" stay words.
  Convert a spelled number when it contains a scale word (*hundred, thousand, million*), is ≥ 10, or
  is followed by a unit / *percent* / *am, pm*; years "twenty twenty four" only after *in / the year /
  since / by*. Inferred; to be settled by the test cases.

### S1-mini by Superwhisper

Source: <https://huggingface.co/superwhisper/s1-mini> and <https://superwhisper.com/blog/s1>, read
2026-10-24. Confirmed from the model card unless marked.

- Qwen3-0.6B fine-tune, 596M parameters. Q4_K_M GGUF 462 MiB (`superwhisper/s1-mini-GGUF`, 18
  quantisations). No ONNX. Runtimes: llama.cpp (`--jinja`), Ollama, transformers ≥ 4.51, vLLM.
- Licence: Apache 2.0 plus a naming clause: wherever it is used it must be called "S1-mini" by
  "Superwhisper", in that capitalisation. The app UI must name it that way.
- Control line, no free prompt: `[Styling: casual|semi-casual|semi-formal|formal] [Structure:
  prose|lists] [Context: general|email]`, then the transcript. The exact system prompt from the card
  is required; `enable_thinking=False`, greedy decoding, inputs under about 1,000 tokens (chunk
  longer takes), `max_new_tokens` ≈ 1.3 × input + 32.
- Does: fillers, self-corrections, punctuation, capitalisation, numbers, dates, emails. **English
  only**, and not trained on romanised Hebrew: it may "correct" *teudat zehut* or *arnona*. That
  is the main risk for Hebrish and must be measured on the Hebrish test set before shipping.
- **No bigger open model.** S1-Voice and S1-Language (launched 2026-08-19) are proprietary,
  cloud-only. A larger *local* desktop option would have to be a general instruct model prompted
  for clean-up (e.g. a 2–4B Qwen3 or Gemma 3 GGUF through llama.cpp), or Daniel's own planned
  LoRA of S1-mini (`ASR-Post-Processor-Model`, planning since 2026-10-16).
- Phone feasibility (inferred, not measured): a 0.6B Q4 model in llama.cpp needs about 0.6–0.8 GB
  RAM and on a recent flagship decodes in the tens of tokens per second, so a 100-word message
  (~130 output tokens) would take a few seconds after the take ends. Workable as an opt-in on recent
  phones, too slow and too large for older ones and for type-as-you-go.

## Recommendation

One pipeline on every platform, each stage specified once in `shared/` with shared test cases:

| Stage | Where | Default | Applies to |
| --- | --- | --- | --- |
| 1. Personal dictionary | exists | on | per piece |
| 2. **Disfluency chop** (*um, uh, eh, ehm, er, erm, hmm*, then cleanup) | regex, both apps | **always on, no setting** (Daniel) | per piece, every model |
| 3. **Numbers to digits** | number-word parser, both apps | on, with a setting | per piece |
| 4. **Finishing** (one of): *None* · *Clean-up: S1-mini by Superwhisper* (desktop only; Styling / Structure / Context pickers) | S1-mini: llama.cpp on desktop; downloaded on demand like speech models | None | the whole take, only when it is inserted in one go (insert-as-you-go off, File / Transcribe tab, Paste last) |

Notes on the design:

- Run stages 2–3 before S1-mini too: shorter input, and the result is the same if S1-mini skips a
  filler.
- S1-mini on desktop only, through llama.cpp (GGUF; desktop B-35 already brings a GGML build path).
  There is no ONNX build of S1-mini and none is needed on desktop.
- A guard for S1-mini: if a word from the
  personal dictionary or the Hebrish lexicon is changed or dropped, fall back to the stage-3 text.
- Listed in the model catalogue (`shared/catalogue.json`) as a separate "text clean-up" kind, so the
  download, size and hardware lines work as for speech models.
- Desktop "bigger model": offer a prompted local instruct model only after S1-mini has been measured
  on Hebrish text; adding one now has nothing to compare against.

## Next steps

1. **B-38 Disfluency chop** (both apps): done, unreleased (2026-10-24): `shared/disfluencies.md`,
   `shared/disfluency-cases.json`; ships in the next release of each app.
2. **B-39 Numbers to digits** (both apps): shared spec and cases first; try the NeMo ITN → sherpa-onnx
   `ruleFsts` route in parallel, keep whichever passes the cases.
3. **B-40 Finishing stage**: measure S1-mini on Hebrish benchmark transcripts on the laptop CPU
   (romanised-word preservation, latency) before adding it to desktop. Paragraph inference is not
   part of Hebrish (D-2026-10-24-08).
