# Streaming dictation that revises earlier words

**Status:** answered (2026-10-22). Append-only streaming is built (B-12); corrections are idea I-4.
**Request:** R-2026-10-22-11 (`planning/requests.md`). Backlog: I-4.

## Question

Cloud dictation (Deepgram, Google, Apple) shows text word by word as you speak, and sometimes
goes back and corrects words it already showed once later speech makes them clearer. Can the
Hebrish apps do the same on-device? What is the mechanism, which base model should it run on,
and what has to change in the apps? The main use is dictating into a terminal (Claude Code).
Insert-as-you-go does that today with Parakeet in 5–10 s pieces (`desktop/docs/maintaining.md`,
"Insert-as-you-go presets").

Daniel's starting guess was that the Nemotron streaming model (the Shakshuka line) is a better
base than Parakeet. That guess holds, with one correction: Nemotron streams, but it never
revises what it has emitted. The revisions need a second pass.

Confidence marks: **[C]** confirmed from the source on 2026-10-22; **[I]** inferred.

**Decided since (D-2026-10-22-12):** the first version is append-only Shakshuka on the desktop,
with no corrections (backlog B-12, done; record in `desktop/docs/maintaining.md`, "Shakshuka:
streaming dictation"). Corrections stay idea I-4, and this page is the brief for building them.

## What it's called

Use these names in issues, code and docs:

- **The field:** incremental (streaming) speech recognition.
- **What the recognizer emits:** *partial results* (partial hypotheses) and *final results*.
- **The feature:** *live partial results with revision*.
- **How often partials change:** *stability* of the partial results.
- **What the user sees when they change:** *flicker*.
- **Fixing it on screen:** *display stabilization*.
- **Fixing it in the model:** *two-pass rescoring* (or *deliberation*).

"Retroactive correction" is not an established term; don't use it.

| Term | Meaning | Who uses it |
| --- | --- | --- |
| Partial / interim results | Words output while the user is still talking. They "can be revised before the ASR finalizes its hypothesis" | Google, Shangguan et al. 2020 ([arXiv:2006.01416](https://arxiv.org/abs/2006.01416)); Baumann et al. 2009 ([N09-1043](https://aclanthology.org/N09-1043/)); Deepgram (`interim_results`) [C] |
| Stability / word-stability estimation | How likely a partial is to stay as it is. Showing a word only once its estimated stability passes a threshold trades stability against lag; the newest words are the least stable | McGraw & Gruenstein 2012 ([Interspeech](https://www.isca-archive.org/interspeech_2012/mcgraw12_interspeech.html)); Google STT's `stability` field [C] |
| Flicker | The visible effect of revisions. It adds cognitive load | Google ASR, Translate and live captions ([blog 2021](https://research.google/blog/stabilizing-live-speech-translation-in-google-translate/), [blog 2023](https://research.google/blog/modeling-and-improving-text-stability-in-live-captions)) [C] |
| Display stabilization | Fixes applied on screen. *Masking*: hide the last few words until the sentence ends. *Biasing*: steer the new hypothesis towards what is already shown. *Alignment and merging*: apply only the changes that matter. With masking and biasing, erasure fell from 2.1 to 0.1 for 0.2 BLEU | Google Translate "Transcribe" (2021); Google AR captions, CHI EA 2023 [C] |
| Re-translation vs. streaming (prefix-to-prefix) | Re-translation re-decodes from scratch, so earlier output can change. Streaming only appends. Shakshuka today is the streaming kind | Arivazhagan et al. 2020 ([arXiv:2004.03643](https://arxiv.org/abs/2004.03643)) [C] |
| Two-pass rescoring / deliberation | A streaming first pass, then a second pass that rescores it. Deliberation also attends to the first-pass text | Google ([arXiv:1908.10992](https://arxiv.org/abs/1908.10992), [arXiv:2003.07962](https://arxiv.org/abs/2003.07962)) [C] |

**Metrics to report** when I-4 is built, next to final WER and latency:
- **Normalized Erasure:** erased words per final word; under 0.2 counts as acceptable (Arivazhagan 2020).
- **UPWR:** Unstable Partial Word Ratio, unstable words ÷ words in the final hypotheses (Shangguan 2020).
- **UPSR:** Unstable Partial Segment Ratio, revised segments ÷ utterances (Shangguan 2020).

Shangguan et al. also found that emitting partials every 200 ms instead of every 50 ms improves
stability a lot, for about 75 ms of extra mean delay [C].

### Apps that do it

| App | Rewrites words already shown? | Source |
| --- | --- | --- |
| Apple dictation (iOS, macOS) | Yes: it is seen "changing a word back-and-forth between two possibilities as you continue to speak" | [TidBits, 2020](https://tidbits.com/2020/08/31/how-ios-and-macos-dictation-can-learn-from-voice-controls-dictation/) (a user's account, not Apple docs) [C] |
| Google Translate, Transcribe | Yes, with masking and biasing | [Google blog 2021](https://research.google/blog/stabilizing-live-speech-translation-in-google-translate/) [C] |
| Aqua Voice | Yes: "refines as you speak" (Realtime Mode) | [aquavoice.com/mac](https://aquavoice.com/mac) (vendor) [C] |
| SuperWhisper | Shows a live preview, then replaces it with a full re-decode at the end | [staff reply](https://superwhisper.userjot.com/board/p/live-text-functionality) [C] |
| Deepgram, AssemblyAI, Google STT, Azure (APIs) | Yes: interim results replaced by finals | the vendor table above [C] |
| Gboard voice typing | Streams on device (RNN-T). No source found on whether it rewrites | [Google blog 2019](https://research.google/blog/an-all-neural-on-device-speech-recognizer/) [I] |
| Wispr Flow, Dragon, Windows Win+H, Otter, Teams/Zoom/Meet captions | Not documented. Settling it needs a screen recording of each | [I] |

## How the vendors expose it

They all work the same way: **text that is already committed, followed by a tentative tail that
each update replaces in full. An endpoint event then commits the tail.**

| Vendor | Tentative | Committed | Endpoint |
| --- | --- | --- | --- |
| Deepgram | `is_final:false` ("may change") | `is_final:true` | `speech_final:true` after `endpointing` ms of silence (default 10). `UtteranceEnd` after `utterance_end_ms` (1000–5000). Several `is_final` results can come before one `speech_final` [C] |
| AssemblyAI | each `Turn` message replaces the last one for that turn ("render the latest, do not append"). Per-word `word_is_final` | `end_of_turn` | `min_turn_silence` 400 ms, `end_of_turn_confidence_threshold` 0.4 [C] |
| Google STT | `is_final:false`, with a per-result `stability` score. One message can have a stable head and an unstable tail [C] | `is_final:true` | — |
| Azure | `recognizing` events | `recognized` event | — [C] |
| Apple (iOS 26) | `.volatileResults` | finalized results | — [C] |

Sources:
- <https://developers.deepgram.com/docs/understand-endpointing-interim-results>
- <https://developers.deepgram.com/docs/utterance-end>
- <https://www.assemblyai.com/docs/streaming/universal-streaming/message-sequence.md>
- <https://docs.cloud.google.com/speech-to-text/docs/reference/rpc/google.cloud.speech.v1>
- <https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-recognize-speech>
- <https://developer.apple.com/videos/play/wwdc2025/277/>

## Where the revisions come from (model side)

### Nemotron cache-aware streaming (Shakshuka's base)

- It is a FastConformer encoder with an RNNT decoder (not TDT). Every frame is processed once,
  with no overlap, and the attention and convolution states are cached [C].
- Under greedy decoding the output only ever grows. **Emitted words are final, so Shakshuka on
  its own gives no revisions** [I, from the architecture]. The hyprwhspr project builds on exactly
  this: its live typing needs "a model whose words never change once sent" [C].
- sherpa-onnx added `modified_beam_search` for streaming NeMo transducers in September 2026
  ([PR #3895](https://github.com/k2-fsa/sherpa-onnx/pull/3895)) [C]. Under beam search the best
  hypothesis can change, so the tail becomes revisable [I]. That gives a small revision window
  only: beam search does not add any lookahead.
- Latency modes: `att_context_size = [70, N]`. Stock WER without punctuation or capitalisation,
  from the [base model card](https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b) [C]:

  | Mode | `att_context_size` | Stock WER |
  | --- | --- | --- |
  | 80 ms | `[70,0]` | 8.43 |
  | 160 ms | `[70,1]` | 7.67 |
  | 560 ms | `[70,6]` | 7.07 |
  | 1120 ms | `[70,13]` | 6.93 |

### Parakeet TDT, run chunk by chunk

This does not work at low latency. NVIDIA's table on the
[parakeet-unified card](https://huggingface.co/nvidia/parakeet-unified-en-0.6b) [C] (the card
doesn't say which chunking method produced it):

| Model | Offline | 2.08 s | 1.12 s | 0.56 s | 0.40 s |
| --- | --- | --- | --- | --- | --- |
| parakeet-tdt-0.6b-v2 | 6.04 | 7.99 | 22.83 | 69.55 | 95.12 |
| nemotron-speech-streaming-en-0.6b | 6.92 | 7.46 | 6.92 | 7.09 | 9.52 |

That is why insert-as-you-go cuts at pauses, every 5–10 s. Below about 2 s Parakeet falls
apart. sherpa-onnx runs Parakeet TDT only through `OfflineRecognizer`
([issue #2918](https://github.com/k2-fsa/sherpa-onnx/issues/2918)) [C].

### Two-pass

- A streaming first pass shows words straight away. When an endpoint arrives, a stronger model
  decodes the finished segment again and its text replaces the first pass's.
- Google's RNN-T + LAS two-pass cut WER by 17–22% relative, for a small added latency
  ([arXiv:1908.10992](https://arxiv.org/abs/1908.10992)) [C].
- In practice this is the Deepgram behaviour: interim text, then a final that may differ.

### LocalAgreement (whisper_streaming)

- Re-decode a growing buffer and commit the prefix once n consecutive decodes agree on it. The
  disagreeing tail stays tentative ([ufal/whisper_streaming](https://github.com/ufal/whisper_streaming),
  now superseded by [SimulStreaming](https://github.com/ufal/SimulStreaming)) [C].
- It works with any model, Parakeet included. The costs: compute grows with the buffer, and
  latency is at least two update intervals. sherpa-onnx users call the growing-buffer workaround
  slow [C, #2918].

### One model for both passes: `parakeet-unified-en-0.6b`

- An RNNT model trained for both offline and buffered streaming use. Released on HF 2026-04-07,
  under the NVIDIA Open Model License [C].
- WER: offline 5.91; 6.29 at 1.12 s; 6.52 at 0.56 s; 8.44 at 0.16 s [C].
- It runs in sherpa-onnx, both offline and buffered online
  ([PR #3575](https://github.com/k2-fsa/sherpa-onnx/pull/3575),
  [#3602](https://github.com/k2-fsa/sherpa-onnx/pull/3602)) [C].
- **It cannot be fine-tuned yet.** The card says: "we provide only inference support … We will
  release the unified training pipeline soon." [C, 2026-10-22]

### Newer streaming models (none is a better base for Hebrish)

- Kyutai STT, 0.5 s or 2.5 s delay ([card](https://huggingface.co/kyutai/stt-1b-en_fr)).
- Moonshine v2 streaming.
- Voxtral Realtime, 4B ([arXiv:2602.12241](https://arxiv.org/abs/2602.12241)).
- Nemotron 3.5 ASR Streaming, multilingual: out of scope, because Hebrish outputs English.

## Runtime: sherpa-onnx

Both apps already use sherpa-onnx; the desktop is on 1.13.8.

- **Nemotron streaming runs on CPU through `OnlineRecognizer`** since
  [PR #3044](https://github.com/k2-fsa/sherpa-onnx/pull/3044) (v1.12.22) [C]. The export script is
  `scripts/nemo/nemotron-speech-streaming-en-0.6b/export_onnx.py` [C]:
  - each latency mode is a separate export (encoder, decoder, joiner, and int8 copies);
  - the cache shapes are stored in the ONNX metadata.

  Running the same script on a Shakshuka `.nemo` should work, because the architecture is
  unchanged [I, test it].
- Pin sherpa-onnx at 1.13.4 or later. OpenWhispr reports that earlier versions transcribed
  badly, and gave no error ([post](https://openwhispr.com/blog/local-streaming-speech-to-text)) [C].
- The online result now carries per-token log-probs and `num_trailing_blanks`
  ([#3893](https://github.com/k2-fsa/sherpa-onnx/pull/3893),
  [#3892](https://github.com/k2-fsa/sherpa-onnx/pull/3892)) [C]. These are useful for endpointing
  and for deciding when to commit text.

## Output side: applying a revision in another app

The desktop app inserts by clipboard plus a paste chord over uinput (Linux) or SendInput
(Windows) (`desktop/hebrish/inserter*.py`). A revision would mean N backspaces (`KEY_BACKSPACE`
through the same uinput device), then a paste of the corrected suffix.

| Approach | Who uses it | Problems |
| --- | --- | --- |
| Backspace and retype on every partial | nerd-dictation ([source](https://raw.githubusercontent.com/ideasman42/nerd-dictation/main/nerd-dictation)) | It deleted most of a sentence ([#67](https://github.com/ideasman42/nerd-dictation/issues/67)); keys arrived scrambled with xdotool ([#29](https://github.com/ideasman42/nerd-dictation/issues/29)); it re-fired macros ([#146](https://github.com/ideasman42/nerd-dictation/issues/146)) [C] |
| Append-only: type only immutable words, hold Enter and the trailing space until stop | hyprwhspr ([v1.47.0](https://newreleases.io/project/github/goodroot/hyprwhspr/release/v1.47.0)) [C] | No corrections |
| Android composing region: `setComposingText`, then `commitText` | Sayboard ([repo](https://github.com/ElishaAz/Sayboard)) [C] | Some apps duplicate words with composing text, so FUTO Keyboard fakes it with commit plus delete ([#1519](https://github.com/futo-org/android-keyboard/issues/1519)) [C] |
| Windows TSF composition | none found | Needs a TSF text service; SendInput has no notion of a composition [C] |

Risks in a terminal [I]:
- A backspace cannot undo an Enter that has already gone through.
- Readline, vi-mode or a TUI can bind a stray key to something else.
- Auto-closed brackets and autocomplete throw off the count of characters on screen.
- On Wayland the app can't read the field, so it knows only what it sent itself (as in idea I-3).

## Recommendation

**Use Shakshuka (Nemotron streaming) for the live text, and Sabich or Jachnun (Parakeet TDT,
offline) as the second pass on each finished phrase.** This is the Deepgram split, built from
models the project already has.

1. **Live pass:** Shakshuka through `OnlineRecognizer`, greedy, 560 ms mode (1120 ms if the
   CPU can't keep up). Words appear about half a second after they are spoken. They never
   change on their own, so they are safe to type into a terminal.
2. **Endpoint:** sherpa-onnx endpoint rules (trailing silence, `num_trailing_blanks`), at about
   300–600 ms. Pausing mid-thought is normal for a dictating speaker, so this needs tuning
   ([D-2026-10-22-02](../../planning/decisions.md) has the same tension for insert-as-you-go).
3. **Final pass:** decode the endpointed segment again with the user's chosen offline model.
   That is the existing `engine.py` path, so it adds no new runtime work. Where the text
   differs, apply one bounded correction:
   - compute the common prefix;
   - backspace only the differing tail, capped at the last ~5 words of that segment;
   - paste the replacement.
   Never revise across an Enter, a focus change or a key the user typed. In those cases keep
   the first-pass text.
4. **Per target:** a setting with three choices:
   - *revise* (default for normal text fields);
   - *append-only* (live Shakshuka, no correction);
   - *pieces* (today's insert-as-you-go).

   For terminals, start with append-only and find out whether revision is trustworthy there
   before turning it on. On Android, use the composing region for the open segment, and commit
   once the second pass returns. Keep FUTO's duplication problem in mind.

### Why not the alternatives

- **Parakeet chunked:** 22.83 WER at 1.12 s.
- **LocalAgreement over Parakeet:** more compute, and latency of at least twice the update
  interval, for a worse result than the two-pass split.
- **parakeet-unified:** the best single-model design, but it cannot be fine-tuned for
  code-switching until NVIDIA releases the training pipeline. Re-check that card before
  building step 3; it would let one model do both passes.

## Open before building

| # | Question | How to settle it |
| --- | --- | --- |
| 1 | Shakshuka's **streaming** WER. Every published Shakshuka number is offline (`Hebrish-App/data/results.json`: leaderboard and `compare` rows for PoC-2). Is 560 ms good enough on code-switched terms? | Run the ASR-Training `evaluate --stream 70,6`, which is already written and has never been run |
| 2 | Does `export_onnx.py` accept the Shakshuka `.nemo` unchanged? | Export the 560 ms mode and decode a few test clips in `OnlineRecognizer` |
| 3 | Can a laptop CPU run the streaming encoder and an offline second pass together, in real time? | Measure on the desktop app's test machine |
| 4 | Does Claude Code's input survive backspace-and-paste without leftover characters? Readline? | Manual test with a scripted uinput sequence |
| 5 | Is a pass that is only append-only Shakshuka already good enough? If so, ship it first and leave revision for later | Daniel's call after #1 |
