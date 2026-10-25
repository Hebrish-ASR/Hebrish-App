---
date: 2026-10-25
platform: desktop-linux
environment: KDE Plasma 6.6 Wayland, Ubuntu 26.04, Hebrish desktop 1.002 (APT), Sabich, insert as you go Normal (5 s), voice detection on, USB headset (Jabra EVOLVE 30 II) at its default gain, dictating into Claude Code in Konsole
component: desktop/hebrish/engine.py (_speech_frames, has_speech, shorten_silences, transcribe_after); desktop/hebrish/ui/app.py (Controller._worker, _insert, _update_tray)
affected: "insert-as-you-go takes on every desktop version with voice detection (0.5.0+); the paste half is unexplained"
fixed_in: "next desktop release after 1.002"
status: fixed (the speech-gate half; the paste half is mitigated and now logged)
---

# The last words of a take never arrive after Stop

## Symptom

Daniel, 2026-10-25 (R-2026-10-25-3): "I'll hit the stop transcription button, I'll get the
transcription, but it's missing the last few words ... that chunk never self-injects, so it ...
looks as if it never made it." He typed the missing words by hand. Two takes in the app's journal
(`journalctl --user _PID=<hebrish pid>`) show two different failures:

- **A (12:19:19):** the take's transcript ends "...in terms of the system tray icon state, I'm not
  sure how we could do that, but"; he typed "it's a bit confusing the way it is currently". Stop
  to transcript took **24 ms**, far too fast for a decode: the last piece was rejected before
  the model saw it.
- **B (12:18:16):** the transcript in the log *does* end "...you can think of a couple more I think
  that would be really slick." (the last piece decoded, 0.5 s after Stop), yet he typed
  "think that would be really slick" himself: the last piece's paste never showed up.

## Cause

**A: the speech gate judged the last piece alone. (I)** With insert as you go, the audio after the
last cut is decoded at Stop as its own piece, and with voice detection on it first has to pass
`engine.has_speech`. That gate looks at the piece's own levels: if its loudest frames (95th
percentile) stay under `VAD_QUIET` (−40 dBFS) the piece is dropped as silence, with no message,
because the take already has text. The few seconds spoken just before Stop are short and often
trail off, and on this headset at its default gain soft speech sits around −41 dBFS (B-46's
measurement the same day), so they fell under the line. `shorten_silences` had the same blind
spot: on a quiet last piece it took the speech for a long silence and cut it to 0.8 s. Inferred
from the 24 ms and the levels: no take audio is kept (D-2026-10-22-20), so the piece can't be replayed.

**B: not found.** The final piece's text reached `Controller._insert` (it is in the transcript, and
`_insert` runs before the transcript is emitted), and no error was logged. Up to 1.002 nothing
logged individual pastes, so it can't be told whether the paste ran late, ran into the
previous paste, or was taken by Claude Code and dropped. Claude Code reads the clipboard itself
on Ctrl+V with two `wl-paste` runs (see 2026-10-22-paste-flicker-claude-code.md), so a paste that
follows the previous one closely may change the clipboard while Claude Code is still reading it. (I, not shown)

## Fix

- **The take judges its pieces.** `has_speech`, `_speech_frames` and `shorten_silences` take a
  `ref`: the take before the piece (up to `REF_S` = 30 s, built in `Controller._worker` by
  `_before`). With `ref`, levels come from the take and the piece together; a frame is speech
  when it clears the old rule on those levels **or** stands `VAD_REL_DB` (15 dB) above the take's
  noise floor (its 5th percentile), and always above `VAD_DEAD` (−70 dBFS). Room noise after the
  last words still yields nothing. The whole-take gate is unchanged (B-46 owns it).
- **Pastes are spaced.** `Controller._insert` waits until `PASTE_GAP_S` (0.4 s) has passed since
  the previous paste chord. A mitigation for B, not a proven fix.
- **Every paste and the last piece are logged** (`pasted N chars`, `last piece: N s of audio, N
  words`), so the next occurrence of B can be traced.
- **The tray says the last words are on the way.** After Stop, while the take's text is still
  being decoded or pasted, the tray icon is amber with three dots (`tray-finishing.svg`) and the
  tooltip reads "finishing, the last words are on the way" (I-1 asked for this, 2026-10-22).
- **Longer pieces, as asked:** insert-as-you-go presets Fast 4, Normal 6, Relaxed 10 s (were
  3/5/8); configs on a preset move once. This doesn't change the cut at a 1 s pause after 2 s
  (`LIVE_BREAK_S`, `LIVE_MIN_S`), so short last pieces still happen; the gate fix is what keeps them.

## Ruled out

- **Pressing Enter before the last words landed** (R-2026-10-22-2): in B the typed words sit inside
  the same message, before the next take's text, so nothing was submitted in between. (V)
- **Focus taken by the overlay or the "No text field" check:** `overlay` is `off` and
  `detect_no_field` is `false` in the config. (V)
- **The decode failing:** B's text is in the logged transcript; A raised no error. (V)

## Checked

- (V) `tests/test_live.py::test_last_piece_is_judged_by_the_take`: a 1.5 s piece at −45 dBFS after
  a take at −30 dBFS with a −76 dBFS floor is rejected alone and accepted with `ref`; 2 s of noise
  at −74 dBFS is still rejected. `test_last_piece_keeps_its_soft_speech`: `shorten_silences` no
  longer shortens it. Full suite: 321 passed.
- (I) Not yet run on dictation through the app, nor on the benchmark: whether the 15 dB rule lets
  breathing through as stray words ("Yeah.") on some mic is unmeasured. If it does, raise
  `VAD_REL_DB`.
- (I) B: if it happens again, the journal now shows whether the last `pasted N chars` line came.
