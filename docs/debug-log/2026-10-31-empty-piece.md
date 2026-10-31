---
date: 2026-10-31
platform: desktop-linux
environment: Ubuntu 26.04, Sabich v2.3 int8 (sherpa-onnx 1.13.8 in the dev venv; the 1.012 .deb bundles 2.0.1)
component: desktop/hebrish/engine.py (Engine.transcribe_chunks)
affected: "<= 1.013"
fixed_in: "1.014"
status: fixed
---

# A file transcribed with voice detection on loses its last ~15 seconds

## Symptom

Found while testing the local API (B-73), not reported by a user. On a 40 s voice note (speech fading from about -27 to -47
dBFS as the speaker walks away, a child talking in the background), Transcription Mode's path
(`transcribe_chunks(vad=True)`, the default `tm_vad`) returned text for the first ~18 s and nothing for the remaining ~20 s. Hebrish-ASR/Server, run on the same clip with the same
model, transcribed it to the end (V).

## Cause

Sabich v2.3 sometimes decodes a whole piece to an empty string. The piece here was 18.0-37.9 s
of the shortened take (19.9 s). Decoding it (V, 2026-10-31):

| Audio decoded | Text |
| --- | --- |
| the whole piece | empty |
| seconds 0-10, 0-15 | empty |
| seconds 5-20, 10-20 | the speech in that span |
| the piece minus its first 1 s | complete |
| minus its first 2 s | empty |
| minus its first 3 s | partial |

So it is all or nothing, and it depends on exactly where the piece starts, not on its level or
length alone. Voice detection was only how the piece boundaries landed on a bad start: without
it, `split_points` cut at 18.1 and 26.0 s and every piece decoded (V). The same failure can
happen with voice detection off, on another file (I).

## How it was found

`/tmp` probe scripts driving `Engine` with the real model: `transcribe_chunks` with `vad` on (3
non-empty pieces) and off (5); the speech frames from the energy rule and from Silero (both keep
about 34 of 40 s, so silence shortening was not removing speech); `split_points` with and
without shortening; then decoding the failing piece with whole-take gain and per-piece gain
(both empty) and the sub-ranges above.

## Ruled out

- **Voice detection dropping speech:** the energy rule and Silero both keep about 34 s of 40, and
  the dropped seconds are pauses (V).
- **Level:** normalising the piece on its own (per-piece gain instead of whole-take gain) still
  gives an empty result (V).
- **Piece length:** the 17.9 s last piece without voice detection decodes fine, and the failing
  piece decodes once its first second is dropped (V).

## Fix

`Engine._decode_retry`: when a piece that has speech (`has_speech`) decodes to an empty string,
cut it at the quietest 100 ms between 35% and 65% of its length and decode the two halves, up to
two levels (halves, then quarters; `EMPTY_RETRY_DEPTH`), never into halves under 2 s
(`EMPTY_RETRY_MIN_S`). A real silence is never retried. The cost is only paid on a piece that
would otherwise be lost. Logged at INFO ("empty piece of N s with speech: ...").

Only `transcribe_chunks` uses it: Transcription Mode, the local API, and Voice Typing takes
decoded whole. `transcribe_after` (insert-as-you-go pieces with context) and the streaming
Shakshuka path are unchanged.

## Verified / not verified

- (V) With voice detection on, the clip now transcribes to the end: the lost ~20 s are back, a
  few words rougher than without voice detection.
- (V) `desktop/tests/test_empty_piece_retry.py`: recovery, bounded depth, silence not retried.
- (I) How often this happens across real files: not measured. A benchmark pass counting empty
  pieces would tell.
- Not done on Android, which has its own decoder loop: check whether its Transcription Mode shows
  the same empty pieces before porting.

## Related

- B-73 (local API), which found it; `desktop/docs/maintaining.md`, "Local API".
