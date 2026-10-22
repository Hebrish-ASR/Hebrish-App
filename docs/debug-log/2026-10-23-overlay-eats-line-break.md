---
date: 2026-10-23
platform: android
environment: Android, floating mic (accessibility overlay); target app not recorded
component: android/app/src/main/java/app/hebrish/dictation/FloatingMicService.kt (insertInto)
affected: "<= 0.7.5"
fixed_in: "0.7.6"
status: fixed
---

# The floating mic deletes the line break before the dictated text

## Symptom

Daniel, 2026-10-23: dictating with the overlay, a deliberate line break between paragraphs
typed before the take is removed when the transcript arrives, "it seems to inject a backspace".
The on-screen keyboard (IME) path was not reported as affected.

## Cause

(I) The overlay inserts with `ACTION_SET_TEXT`, which replaces the whole field. The new value is
built from `node.text` (what the app reports) and `textSelectionStart/End`. When the reported text
is missing the trailing line break(s) but the cursor index still counts them, the cursor is past
the end of the reported text. The code clamped it to the end of the shorter text and wrote
`reported + " " + transcript` back. The break is deleted and a space takes its place, which looks
like a backspace. Apps that report text this way were not identified; WebView/contenteditable
editors are the usual suspects (I).

## How it was found

Reading the insertion path. `insertInto` was the only place in the overlay that can remove
characters: SET_TEXT rewrites the field, and the clamp
`if (start !in 0..current.length ...) start = current.length` silently accepts a cursor the text
cannot hold. No device is attached to the build machine, so it was not reproduced.

## Ruled out

- The keyboard (IME) path: `commitText` only inserts, and the separator check reads
  `getTextBeforeCursor(1)`, so a `\n` before the cursor gets no space. (V, by reading)
- The placeholder rule (`isPlaceholder`): it never fires on text containing `\n`. It could fire if
  an app reports a trimmed single line with no cursor, but then it would replace the whole field,
  which is not the reported symptom. (I)
- The transcript itself: `Transcriber` trims the decoded text, which removes only leading and
  trailing whitespace of the transcript, not anything in the field. (V)

## Fix

0.7.6: when the cursor is past the reported text, paste at the field's cursor (clipboard +
`ACTION_PASTE`), which inserts without deleting. If the paste is refused, rewrite with the missing
characters restored as `\n`. All other cases are unchanged. Not covered: a trimmed text with no
cursor reported (-1); that still appends at the end with a space.

## Verified / not verified

- Compiles (`assembleDebug`). (V)
- On a device: not tried. Daniel tests the release.

## Related

Paragraph breaks from the model: the Parakeet-family vocabularies shipped in the app (Jachnun
v1.0, Sabich v2.0, Shakshuka v2.0) were checked on 2026-10-23 and none has a newline token
(1,025 tokens each, `tokens.txt`). The models cannot output a paragraph break whatever the
training data contains. The harness would also lose a break at a segment boundary: `TakeDecoder`
joins segments with a space and `Transcriber` trims each one. Breaks have to come from a vocabulary
change or a post-processor (ASR-Paragraph-Breaks).
