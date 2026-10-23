---
date: 2026-10-23
platform: android
environment: Android voice keyboard, floating mic and Try it; any long take (over 8 s) with pauses
component: android/core/src/main/java/app/hebrish/core/TakeDecoder.kt, Transcriber.kt
affected: "<= 0.8.1"
fixed_in: "0.8.2"
status: fixed
---

# Capitals (and full stops) in the middle of sentences on Android

## Symptom

Daniel, 2026-10-23: "I'm also getting the mid-sentence capitals on Android." The same symptom
was fixed on desktop the same day (desktop 0.7.6): after a pause in the middle of a sentence the
next word starts with a capital, often after a stray full stop ("word. Capital", "word Capital").

## Cause

(I, by reading the code; the mechanism is the one measured on desktop) `Recorder` cuts a take
longer than 8 s into segments at pauses of 0.6 s or more (`Recorder.Segmenting`), and
`TakeDecoder` decoded each segment on its own and joined the texts with a space. Parakeet treats
each segment as a complete utterance: it capitalises the first word and closes the last with a
full stop. Nothing at the seam corrected either.

## How it was found

The desktop session diagnosed and measured it on 2026-10-23 (`desktop/docs/maintaining.md`,
"Context at the seams"; `desktop/scripts/seam_bench.py`). Reading `TakeDecoder` showed Android
had the same per-segment decode with a bare `" "` join and no held-stop handling at all (desktop
had had a `CONTINUES` rule since 0.7.1).

## Ruled out

- Takes under 8 s: one segment, so no seam; not affected (V, `Recorder.Segmenting.MIN_SECONDS`).
- A text-only rule alone (desktop 0.7.1-0.7.5's `CONTINUES` list) left most bad seams on
  desktop, mainly after pieces that ended with no mark at all (desktop measurement).

## Fix

Port of desktop 0.7.6: decode each segment after the last 3 s of the previous one and keep only
the tokens timed after the context (`Transcriber.transcribeAfter`); hold a closing full stop and
let the model's own mark at the seam decide (`TakeDecoder.afterHeldStop`, with the `CONTINUES`
fallback when there is no context); ALL CAPS after the seam. Callers space pieces with
`TakeDecoder.join` so a held stop handed over as ". Next" attaches to the word before it. Rules
and costs: `android/docs/maintaining.md`, "Context at the seams (0.8.2)".

## Verified / not verified

- (V) Compiles (both flavors). The seam helpers (`afterHeldStop`, `join`, `holdStop`) were run
  from the compiled classes on the desktop examples and match desktop's output.
- (V, desktop only) 108-clip seam benchmark: mid-sentence capitals 73 → 30, false full stops
  27 → 10, WER 6.38 % → 6.07 %, about 21 % more decode time.
- (I) Not run on a device: Android's seam counts and its extra decode time are unmeasured; the
  history export's `context_s`, `decode_s` and `wait_s` columns will show them.

## Related

- Desktop: `desktop/hebrish/engine.py` (`transcribe_after`, `hold_stop`, `after_held_stop`).
