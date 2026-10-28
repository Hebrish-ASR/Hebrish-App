---
date: 2026-10-28
platform: desktop-linux, android
environment: desktop 0.7.6-1.007 (Ubuntu, CPU, 8 threads), Sabich v2.0-v2.2; Android not measured
component: desktop/hebrish/engine.py (transcribe_after, shorten_silences, stretch_pauses), android/core TakeDecoder
affected: "all versions; reduced in desktop 0.7.6 / Android 0.8.2"
fixed_in: unfixed
status: unfixed
---

# Sentence breaks and capitals in the middle of a sentence after a thinking pause, a filler, or a stop and restart

## Symptom

Daniel, 2026-10-28, mostly on the laptop, and in his view worse on Android: "whenever I stop for
thought, or I add a disfluency, it will infer a sentence break", and when he stops and restarts
recording it "will add a new sentence, a capital letter, in the middle of an existing sentence".
He corrects these by hand. He also feels it is worse than it was with Whisper. This is the
remainder of the 2026-10-23 reports
([android](2026-10-23-android-mid-sentence-capitals.md); desktop `maintaining.md`, "Context at
the seams (0.7.6)").

## How it was found

Desktop History database (`history.db`, table `dictations`, 2026-10-20 to 2026-10-28: 2,014
dictations, 111,725 words). The `original` column (set when a transcript is edited in the app)
was empty for every row: corrections are made in the target app, so the History has no record
of them (V). Two text heuristics instead, Sabich takes only, per minute of audio (`seconds`):

- mid-sentence capital: a common lowercase word (`the`, `and`, `so`, `is`, `that`, `this`, `just`,
  ...) capitalised after a letter or comma ("we could Use those", "for That would");
- false stop: `.?!` straight after `the`/`a`/`to`/`of`/`and`/`with`/... followed by a capital.

| App version | Takes | Audio min | Mid-sentence capitals / min | False stops after a function word / min |
| --- | --- | --- | --- | --- |
| up to 0.7.5 | 376 | 121 | 0.72 | 0.15 |
| 0.7.6-1.003 | 759 | 304 | 0.29 | 0.11 |
| 1.005-1.007 | 805 | 357 | 0.28 | 0.10 |

(V for the counts; the heuristics also catch some correct capitals, e.g. a sentence start with a
missing full stop, so they are a rate to compare, not an error count.) Takes under 8 s (one live
piece, no seam): 0 mid-sentence capitals in 18 min of 1.005+ audio (V).

## Cause

Three separate sources:

1. **Seams inside a take (partly fixed).** Live pieces decoded after 3 s of the previous piece
   (desktop 0.7.6, Android 0.8.2) cut the mid-sentence capital rate by about 60% in real use
   (table above, V), but did not remove it: about one every 3-4 minutes is left.
2. **Thinking pauses inside one decode.** Parakeet (TDT transducer, greedy) emits punctuation and
   case as tokens learned from training clips that are each a whole read sentence ending in a full
   stop; its prediction network is small, so a pause is decided mostly from the audio (I). The app
   adds to it: `stretch_pauses` pads quiet runs of 0.12-0.6 s to 0.6 s (a fix for lost words), and
   `shorten_silences` only trims runs over `VAD_LONG_S` 1.5 s down to `VAD_KEEP_S` 0.8 s, so every
   thinking pause reaches the model as 0.6-1.5 s of silence (V, from the code).
3. **Stop and restart (no handling at all).** Each take is decoded with no context: it always
   starts with a capital, and the previous take always ended with a full stop (V, from the code).
   Not visible in the History heuristics, since each take is its own row; probably the bulk of
   what Daniel corrects by hand (I).

There is no decoder setting that tunes how readily Parakeet ends a sentence: sherpa-onnx offline
transducer decoding exposes no punctuation threshold or token penalty (I). It is not an attention
problem.

## Ruled out

- Edits in History as a measure of corrections: there are none (above).
- Android: not measured. Its History is on the phone; an export is needed. Android cuts long takes
  into 8-28 s segments (desktop: ~5 s pieces), and on a phone takes are probably stopped and
  restarted more often (cause 3) (I).

## Fix

Unfixed. Planned as [Sprint: sentence boundaries](../../planning/sprints/2026-10-28-sentence-boundaries.md) (B-54 to B-64, 2026-10-28). Options, in the order proposed on 2026-10-28:

1. Context across takes: when a take starts within ~20 s of the last one, decode it after the last
   3 s of that take (as `transcribe_after` does for pieces). If the model continues the sentence,
   remove the full stop pasted before: on Android by reading `getTextBeforeCursor` (only if it is
   still there); on desktop (Wayland, cannot read the field) by one Backspace inside a short window.
2. Trim thinking pauses harder (`VAD_KEEP_S` ~0.4 s), measured first with
   `desktop/scripts/seam_bench.py` (false stops, lost stops, WER).
3. Training data for the next Sabich round: a dataset of mid-sentence pauses and fillers with no
   break in the transcript, and clips that start and end mid-sentence (lowercase start, no final
   mark).
4. A different base model for desktop: [research/desktop-base-model](../../research/desktop-base-model/README.md).

## Verified / not verified

- (V) History rates above; the code paths for causes 2 and 3.
- (I) That cause 3 is the larger share of hand corrections; the Android rate; the transducer
  explanation.

## Related

- [2026-10-23-android-mid-sentence-capitals.md](2026-10-23-android-mid-sentence-capitals.md)
- `desktop/docs/maintaining.md`, "Context at the seams (0.7.6)"
- [research/desktop-base-model](../../research/desktop-base-model/README.md)
