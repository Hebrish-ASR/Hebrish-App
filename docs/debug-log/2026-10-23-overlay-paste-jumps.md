---
date: 2026-10-23
platform: android
environment: Android, floating mic (accessibility overlay); target app not recorded
component: android/app/src/main/java/app/hebrish/dictation/FloatingMicService.kt (insertInto)
affected: "<= 0.9.0"
fixed_in: "0.9.1"
status: fixed
---

# The floating mic makes the field jump on insert, and still deletes the line break before it

## Symptom

Daniel, 2026-10-23, on 0.9.0: "it seems to jump around when I paste, so when the text injection
happens. and it's clearing a preceding line break, which isn't desired because it removes the
paragraph breaks." The line break half was reported on 0.7.5 and treated in 0.7.6
([2026-10-23-overlay-eats-line-break.md](2026-10-23-overlay-eats-line-break.md)); it was still
there.

## Cause

(I) Both symptoms come from the same call. The overlay wrote every piece of a take with
`ACTION_SET_TEXT`, which replaces the whole field with a value built from the text the app
*reports*, and then moved the cursor with `ACTION_SET_SELECTION`.

- **Jumping:** a full rewrite resets the editor's scroll position, then the selection change
  scrolls back to the cursor. With type-as-you-go that happens once per piece.
- **Line break:** 0.7.6 only pasted when the reported cursor was past the end of the reported
  text, i.e. when the cursor gave the hidden break away. An app that drops the trailing break from
  the text *and* reports the cursor within the shorter text (or no cursor, -1) still got a rewrite
  without the break and with a space added. The 0.7.6 entry had listed the -1 case as not covered.

## How it was found

1. `VoiceImeService` (keyboard path) only calls `commitText` and reads one character before the
   cursor for the separator: nothing in it can delete or rewrite. So the report is about the
   overlay, which matches "paste".
2. In `FloatingMicService`, `insertInto` → `setText` is the only code that rewrites a field. Every
   piece of every take went through it unless the 0.7.6 condition (cursor past the text) held.
3. `TakeDecoder.join` and the seam rules (0.8.2) only add text at the start of a piece (`" "` or
   `". "`); they never remove characters. Ruled out below.

No device is attached to the build machine; not reproduced.

## Ruled out

- The keyboard path, as in step 1. (V, by reading)
- The held full stop and seam logic (0.8.2) and the personal dictionary (0.9.0): they change the
  transcript only, never the field. (V, by reading `TakeDecoder.process`)
- The placeholder rule: it requires single-line text, so a field with a visible `\n` is never a
  placeholder. If an app reports trimmed one-line text with no cursor it could fire, but that
  would replace the whole field, not just the break. (I)

## Fix

0.9.1, `insertInto`: clipboard + `ACTION_PASTE` at the field's own cursor first for every piece;
`ACTION_SET_TEXT` only when the paste is refused, or first when the reported text is a placeholder
that has to be replaced. The paste inserts and deletes nothing, and the app's own editor keeps its
scroll position. The separator is still `TakeDecoder.join`, judged from the reported text before
the cursor (a hidden tail counts as a line break: no space).

Cost: every dictated piece now goes through the clipboard, so the transcript is on the clipboard
after a take (as it already was on the fallback path) and the user's previous clip is lost.
Android 13+ may show its clipboard preview each time (I, not checked).

Left over (I): an app that hides a trailing break and reports a cursor within the shorter text
gets the right insert from the paste, but the separator can't see the break and adds a space at
the start of the new paragraph.

## Verified / not verified

- Compiles (`assembleDebug`). (V)
- On a device: not tried. Daniel tests the release.

## Related

[2026-10-23-overlay-eats-line-break.md](2026-10-23-overlay-eats-line-break.md) (0.7.6, the first
round of the line break).
