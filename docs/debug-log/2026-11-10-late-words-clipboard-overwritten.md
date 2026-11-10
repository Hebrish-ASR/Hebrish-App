---
date: 2026-11-10
platform: desktop-linux
environment: Ubuntu, KDE Plasma (Wayland), desktop 1.028 (.deb), Parakeet with insert-as-you-go every 6 s
component: desktop/hebrish/ui/app.py
affected: "1.007 to 1.028, with enter_guard = late and out_clipboard on"
fixed_in: "unreleased (next desktop release)"
status: fixed
---

# After an early Enter, pasting the late words pastes the whole take again

## Symptom

Daniel, 2026-11-10: when Enter goes in before the last words, "the repaste thing ... doesn't just send
what didn't come in, it sends like the entire transcription again ... most times".

## Cause

Two clipboard writes raced, and the wrong one won (V, code and log):

1. The worker emits `transcribed` → `_done`, which with `out_clipboard` on schedules the **whole take**
   to the clipboard after `CLIPBOARD_AFTER_PASTE_MS` (600 ms).
2. Right after, `_finish_take` emits `late` → `_show_late`, which puts the **late words** on the clipboard at once
   and says so in the status line.
3. 600 ms later the first timer fires and overwrites the late words with the whole take. Ctrl+V then
   pastes everything.

The overlay's Paste button and the Paste last key were not affected: both paste `_late_text` /
`_late_last` through the inserter (B-88). Only the clipboard, which the status line points to, was wrong.

## How it was found

The journal for the take of 2026-11-10 17:53 (`journalctl --user | grep hebrish`): Stop at 17:53:36.76,
the pending piece pasted at 37.87, the send key at 38.40 ("send key before the last words: keeping
take(s) [1]"), transcript at 38.597, "kept 25 chars after an early Enter" at 38.865. No paste from the app
followed, so the repaste was the user's Ctrl+V. The user's config had `out_clipboard: true`, `overlay:
"off"`. Reading `_done` showed the 600 ms timer.

## Ruled out

- The late words themselves being the whole take: the log says 25 chars, out of a ~300 char transcript.
- B-88 (Paste last falling back to the whole take): fixed in 1.021 and in the installed 1.028.

## Fix

`Controller._copy_whole(whole)` replaces the timer's direct `_copy_take`: it skips the copy when
`_late_last` is set and the take ends with it (so late words from an earlier overlapping take don't stop
this take's copy). The late words stay on the clipboard.

The same report asked for a sign that words are still coming. New overlay mode `finishing` (default for
new installs): the overlay shows only from Stop until the last words are in (spinner, then the check), so
an Enter pressed too early is visibly early. See `desktop/docs/maintaining.md`, "Floating overlay".

## Verified / not verified

- (V) Unit tests: `tests/test_paste_last.py` (`test_whole_take_does_not_overwrite_late_words_on_the_clipboard`,
  `test_whole_take_still_copied_without_late_words`), `tests/test_overlay.py`
  (`test_finishing_mode_shows_only_until_the_last_words_are_in`); full desktop suite passes.
- (I) Not run in a live session (agents don't run record-and-paste on the maintainer's desktop).

## Related

- `desktop/docs/maintaining.md`, "Enter guard (B-50, 1.007)"; backlog B-88, B-102.
