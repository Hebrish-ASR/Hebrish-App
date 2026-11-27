---
date: 2026-11-27
platform: desktop, android
environment: Hebrish desktop 1.046 (.deb, Ubuntu, CPU, 8 threads, Silero VAD at Noise filter 60, live insertion every 6 s), Sabich v5.5 to v5.8
component: desktop/hebrish/engine.py (faint, faint_level, usual_update), desktop/hebrish/ui/app.py (Controller._worker), android/core VoiceDetection.kt, TakeDecoder.kt
affected: "desktop <= 1.046, Android <= 1.037"
fixed_in: "desktop 1.047, Android 1.038 (partly: see Verified)"
status: fixed
---

# "My mother's mother" still appears: whole takes of silence, and the first piece

## Symptom

After 1.046 (2026-11-23) a review of the desktop dictation history from 2026-11-24 to 2026-11-27 (about 620 takes) still
found the phrase (V): one 19.5 s take whose whole text was "My mother's mother", one 6-minute take with no speech that wrote it
four times, and one at the start of a real take. The rate fell from 14.6 and 17.8 per 1,000 takes (1.042) to 0 to 7 (1.046).

## Cause

`engine.faint()` judges a piece against the take's own speech level so far, so it can only act after the take has had
speech (V, code). A take's first piece, and every piece of a take with no speech, were compared with nothing (or with room
noise), and Silero, which sees each piece scaled to `PEAK`, passed breath and noise as speech (V, measured on 2026-11-23 takes).
Android's `VoiceDetection.faint` had the same gap (`takeLevel` 0 until the first text; V, code).

## How it was found

`scripts/hallucination_audit.py` (training repo) on the history rows since 2026-11-23, joined with each row's `decode` app
version and length. The seam and punctuation audit of the same rows found nothing new from the app (space before a mark and
doubled marks at 0 to 0.3 per 1,000 words); run-on sentences (5 to 7 per 1,000 words in segmented takes) are spoken style
and model punctuation, not seams, from reading the hits. No audio of the 1.046 cases exists (maintainer mode was off), so the
fix was measured on the 62 maintainer takes of 2026-11-23.

## Ruled out

- A rule on level alone for every opening: the two remaining "Mm-hmm." and "My name is Rem" openings are as loud and as long
  as a real short opening in the same takes; any threshold that drops them drops real words.
- A text filter for the phrase: some are real sentences.
- Scaling Silero by the usual level instead of the piece's own peak: would catch more silent takes, but changes detection for
  every piece and needs a decode run against quiet speech first. Not done.

## Fix

Remember the usual speech level (desktop: per mic in `levels.json`; Android: one value in prefs), learnt from every piece that
gives text, and, until a take has given text, skip a piece that is faint against it (under 1 s of speech frames, almost
nothing within 18 dB). `FAINT_LOUD_S` 0.06 to 0.08 s. Details and numbers: `desktop/docs/maintaining.md`, "Again: a take with
no speech, and the first piece"; `android/docs/maintaining.md`, "The first piece and takes with no speech".

## Verified / not verified

- (V) 62 takes of 2026-11-23: both known breath openings now skipped, no piece that gave real text skipped.
- (V) Silent takes built from the quiet stretches of those takes: 5 of 11 reached the decoder with 1.046, 2 with 1.047.
- (V) Desktop unit tests (`tests/test_live.py::test_first_piece_judged_by_usual_level`). Android compiled in CI only.
- (I) Word error rate unchanged (no decode run). Not tried on a real silent take, a mic swap, or a phone.

## Related

`2026-11-23-breath-pieces-invented-phrases.md` (the 1.046 fix this extends).
