# Disfluency chop (both apps)

Written 2026-10-24 (request R-2026-10-24-1, backlog B-38, decision D-2026-10-24-04).
(V) = verified, (I) = inferred.

Hesitation sounds are removed from the model's text after decoding, on every platform and with
every model. There is no setting: Daniel, 2026-10-24, "I can't think there's any reason why people
would want those disfluencies." The fine-tunes are trained to drop them too; this is the
deterministic fallback for the models and checkpoints that still write them.

## Where it sits

First, straight after decoding: before the seam rules, the personal dictionary and ALL CAPS, so
none of them sees a filler. It works on one piece of text at a time, so it runs with insert-as-you-go
and with Shakshuka's streamed words. It reaches History (History holds what was meant).

## What is removed

A **filler** is a whole word (no letter, digit, apostrophe or hyphen directly before or after it)
matching, case-insensitively:

| Pattern | Covers |
| --- | --- |
| `u+h+m*` | uh, uhh, uhm |
| `u+m+` | um, umm |
| `e+h+m*` | eh, ehh, ehm (the Israeli filler) |
| `er`, `e+r+m+` | er, erm, ermm |
| `h+m+` | hm, hmm, hmmm |

Kept on purpose: *ah* and *oh* (interjections with meaning), *mm*, *mhm*, *mm-hmm*, *uh-huh*
(agreement; *mm* is also millimetres), *err* (a verb), *like*, *you know*, *I mean* and repeated
words (meaning-dependent: left to the models). A filler written in capitals of two or more letters
is kept (`ER`, the emergency room; `UM`): the models write a filler in lower case or with only its
first letter capitalised.

## How it is removed

1. The filler goes with the spaces before it and a comma or semicolon straight after it:
   `So um, I think` → `So I think`; `I think, um, we` → `I think, we`.
2. A filler that **starts a sentence** (only whitespace before it in the piece, or a `.`, `!` or `?`
   then whitespace) also takes the punctuation and spaces after it: `Um. So we` → `So we`;
   `Yes. Uh, we can` → `Yes. We can`. Spaces at the very start of the piece stay (Shakshuka's words
   carry their own leading space).
3. If the filler's first letter was a capital, the next letter is capitalised (it starts the
   sentence now). A lower-case filler leaves the next word alone, since a piece can start mid-sentence.
4. Cleanup: a comma left before `.`, `!` or `?` is dropped (`and then, um.` → `and then.`);
   a space left before `,.!?;:` is dropped; a piece that is only fillers becomes empty.

The shared test set is `disfluency-cases.json` (desktop `tests/test_disfluency.py`; Android
`scripts/check_disfluency.sh` runs it on the JVM). The patterns use only lookarounds,
`\p{L}`/`\p{N}` (Kotlin) or `[^\W_]` (Python) and case-insensitive matching (I: ICU, Android's
regex engine, supports all of them).

## Known limits

- A capitalised filler alone at the end of a piece (insert-as-you-go) cannot capitalise the next
  word, which arrives in the next piece.
- The source patterns and their risk notes: `ASR-Regex-Post-Processing/topics/disfluencies.md`
  (Daniel's regex notebook).
