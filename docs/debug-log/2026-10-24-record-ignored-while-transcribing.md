---
date: 2026-10-24
platform: desktop-linux
environment: Ubuntu, KDE Plasma Wayland (Daniel's daily use); the logic is shared with Windows
component: desktop/hebrish/ui/app.py (Controller.start, stop, _done, _worker)
affected: "<= 1.000"
fixed_in: "next desktop release (unreleased, after 1.000)"
status: fixed
---

# I think I'm recording when I'm not, and the other way round

## Symptom

Daniel, 2026-10-24: on Ubuntu he sometimes believes the app is armed (recording) when it is
disarmed, and vice versa. It happens when he starts the next dictation before the previous one's
text has come back.

## Cause

`Controller.start()` returned at once unless the state was `idle`. After Stop the state is `busy`
until the take's text lands (`_done`), so a toggle press in that window was silently dropped: no
cue, no state change. Daniel then talked to a mic that wasn't open, and his next press, meant as
Stop, started a take. From there every press did the opposite of what he expected until he
noticed. (V, by reading the code: `start()`'s first line, and `hotkey.py` sending `start` for any
press while `is_recording()` is false.)

## How it was found

Read from the report: the only way a press can leave the user out of step is a press that does
nothing, and `start()` had exactly one such guard that applies to a normal take, `state != "idle"`.

## Ruled out

- Hotkey bounce or the double-tap Retake timer: those act while recording, not after Stop.
- Push-to-talk release logic: the report is about tap-tap.

## Fix

Takes may overlap (R-2026-10-24-6, B-43). `start()` now also runs when the app is busy only
because earlier takes are transcribing (`queued_ok`: `pending > 0` and no model load). The mic
opens at once; the decode worker already handles jobs in order, so the earlier take's text is
pasted first and the new take follows.

- A discarded take is now marked in `_dropped` instead of bumping `_take` (which would also have
  dropped the earlier, still-pending take's final job).
- `pending` counts stopped takes awaiting text; `_done` decrements it and only sets
  `idle`/`busy` when not recording. Stop times are a FIFO (`_stops`) for the latency stats.
- The Dictate tab starts a new text block when the worker reaches a take (`take_began`), not
  when the take starts, so late text from the earlier take stays in its own block.
- Cues for an earlier take (no speech, failed, copied) mute the recorder for their length if a
  take is recording, so they don't end up in it.
- The "Inserted" overlay flash is skipped while the next take records.
- UI: Talk stays enabled while transcribing ("Transcribing… Talk to start the next"); while
  recording with an earlier take pending: "Listening… (last take still transcribing)". Tray
  toggle and the overlay mic accept the press too.

## Verified / not verified

- (V) `tests/test_queued_takes.py`: start during busy records; two queued takes stay busy until
  both land; no start while a model loads; discard returns to busy; the worker decodes in order
  and skips a discarded take. Full suite 240 passed. `--selftest` OK.
- (I) Not yet tried live with the hotkey on Daniel's desktop, or with Shakshuka streaming
  (the per-take stream is reset on take change as before).

## Related

- `desktop/docs/maintaining.md`, "Overlapping takes".
- Android parity: B-43a, same day: the floating mic and keyboard ignored taps while
  transcribing (with a spinner showing); fixed the same way (`android/docs/maintaining.md`,
  "Overlapping takes").
