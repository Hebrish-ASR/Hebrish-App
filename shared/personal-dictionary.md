# Personal dictionary (both apps)

Written 2026-10-23 for Android 0.9.0 and desktop 0.8.0 (request R-2026-10-22-32, backlog I-13).
(V) = verified, (I) = inferred.

A personal dictionary is a list of words the user wants written a certain way: names, brands,
Hebrew terms in their romanization, tech words. Each entry is a **word** (how it is written) and
optionally one or more **heard as** phrases (what the model writes instead, e.g. `hebrew ish` for
`Hebrish`).

## Where it sits: after the model, not inside it

The dictionary corrects the model's text after decoding. It never changes the model, the decoder
or the audio path. That means it cannot slow a take down measurably or make the model's own
output worse, and it works the same on every model. The cost of that: it only fixes words the
model writes *consistently* wrong, and cannot make the model hear a word it never produces.

Decoder biasing (sherpa-onnx `hotwords`) was considered and left for later: it needs
`modified_beam_search` instead of the `greedy_search` both apps use (slower), it is unverified
for NeMo transducers in sherpa-onnx, and an over-weighted boost inserts words that were not said.
Training data (the sentence banks) stays the real fix for words many users need.

Both apps apply it at the same point as ALL CAPS, to every piece of text a take hands over, and
read it once per take (a take never changes dictionary halfway). The seam rules ("Context at the
seams") run first, so a dictionary entry can't confuse them. A replacement does not span two
pieces: with insert-as-you-go, a "heard as" phrase cut in half by a pause stays as the model wrote it.

## Matching rules

Both apps implement exactly these rules; `dictionary-cases.json` is the shared test set
(`desktop/tests/test_dictionary.py` runs it; Android's `PersonalDictionary.kt` follows it).

1. **Boundaries.** A match must not have a letter, digit or underscore directly before or after
   it. `Git` does not match inside `GitHub`.
2. **Case-insensitive.** `hebrish`, `Hebrish` and `HEBRISH` all match `Hebrish`.
3. **Heard as.** Each phrase matches literally (case-insensitive), with any run of whitespace in
   it matching any run of whitespace in the text. It is replaced by the word.
4. **The word itself** matches too, so a correctly heard word gets the dictionary's spelling. For a
   word of four or more letters and digits, one space, hyphen or apostrophe may appear between any
   two of them (`git hub`, `Git-Hub` → `GitHub`; `whats app` → `WhatsApp`). Shorter words match
   only as written, so `AWS` never swallows `a w s`. (An entry matches every occurrence: adding
   `IT` turns every "it" into "IT".) Whitespace inside a multi-word entry matches any
   run of whitespace.
5. **Case of the replacement.** A word with any capital letter is written exactly as in the
   dictionary (`GitHub`, `iPhone`, `Sabich`). An all-lower-case word is a spelling, not a case:
   where the text already has it with the same characters (case aside), the text is left as the
   model wrote it (`Gonna` at a sentence start, `Teudat Zehut`); where a heard-as phrase or a
   split form matched, the word is written in lower case, with a capital first letter if the
   matched text started with one (`Gona go` → `Gonna go`).
6. **One pass, longest first.** All patterns are tried together in one left-to-right pass; at any
   position the longest source (heard-as phrase or word, by character count) wins. A replacement
   is never matched again, so entries cannot chain.
7. **Empty or whitespace-only words are ignored**, and so are empty heard-as phrases. Leading and
   trailing whitespace is trimmed from both.

## Where the entries come from

**Android** reads the system **personal dictionary** (`UserDictionary.Words`: the list keyboards
write to when you tap "Add to dictionary"; Settings → System → Languages → Personal dictionary).
Each row's `word` is the word and its `shortcut` (if any) is a heard-as phrase. Hebrish can add
words to it from its own Personal dictionary screen.

Android only lets an **enabled keyboard** or an enabled spell checker (and the system) read or
write that list; any other app gets an empty list and its writes are dropped, without an error
(V, AOSP `UserDictionaryProvider.canCallerAccessUserDictionary()`, read 2026-10-23: it compares
the caller's uid and package with `getEnabledInputMethodList()` and `getEnabledSpellCheckers()`).
The check is on the app, not on which keyboard is in use, so:

- Once Hebrish's voice keyboard is **enabled** in Settings (the setup's keyboard step; it does
  not have to be the keyboard in use), every part of the app, the floating mic included, reads
  and writes the system list. Words added with Hebrish Keyboard, HeliBoard, Gboard or the
  Settings screen work in Hebrish, and words added in Hebrish appear in those keyboards.
- Hebrish keeps a copy of the list each time it reads it, and its own copy of every word added in
  Hebrish. With the voice keyboard not enabled it uses those copies.

**Desktop** (Ubuntu and Windows) has no system dictionary, so it keeps its own:
`<config>/dictionary.json`, edited in the window's Dictionary tab.

```json
{"schema": 1, "words": [{"word": "Hebrish", "heard": ["hebrew ish"]}, {"word": "GitHub", "heard": []}]}
```

Syncing the two (accounts, I-7) is not built yet.
