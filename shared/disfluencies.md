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
(agreement; *mm* is also millimetres), *err* (a verb), *like*, *you know* and *I mean*. Repeated
words were left to the models until 1.007; they are now rules 5-7 below. A filler written in capitals of two or more letters
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

## Repeated words, false starts, ellipses (1.007, 2026-10-27)

Request R-2026-10-27-3, decision D-2026-10-27-01. Run after rules 1-4, in this order, so
"We, um, we should" loses the filler first and then the repeat. A **word** here is letters and
digits, with inner apostrophes or hyphens. Two words are **next to each other** when only spaces,
one `,` or `;`, or an ellipsis is between them, or a `.`, `?` or `!` and spaces when the second
word starts in lower case (the model didn't start a new sentence). Case is ignored when comparing.

5. **A run of one word** is cut to one: `I really wanted, wanted to go` → `I really wanted to go`;
   `could we change, change, change? change the dataset` → `could we change the dataset`. The first
   word stays as written (its capital, if any); everything after it through the last repeat goes.
   **Twice on purpose:** a word in the keep-twice list keeps two and loses the rest
   (`really, really, really` → `really, really`): intensifiers and interjections (*really, very, so,
   no, yes, yeah, bye, ha, haha, much, more, many, far, long, ever, again, now, well, there, too,
   please, quick, slowly, bit, little, away, hey, okay, ok, knock, go, come*), doubles English
   grammar allows (*had had, that that, is is, was was, do do, did did*), particles (*round, around,
   over, out, on, off, up, down*) and Hebrew doubles (*tov, ken, lo, yalla, nu, dai, kol, od*).
   **Numbers are never cut** (number words *zero ... ten, oh, double, triple*, and anything with a
   digit): `five five five` is a phone number.
6. **Across a seam:** a piece that starts with the word the take's text so far ends on (only
   spaces, `,` or `;` after it) drops that first word, unless it is in the keep-twice list or a
   number. A held full stop counts as there (`Wanted.` then `Wanted to go` is two sentences).
7. **A phrase of two or three words** said again straight away is a false start and is cut once:
   `It was... it was fine` → `It was fine`; `I want to, I want to go home` → `I want to go home`.
   The longer phrase is tried first; a phrase of numbers only is kept.
8. **Ellipses** (`…` or three or more dots) are a thought trailing off, not punctuation to keep.
   Before a lower-case word or a digit: a space (`go… next` → `go next`). Before `.?!,;:`: removed.
   Before a capital or at the end of the piece: a full stop (`next... That one` → `next. That one`;
   `And then...` → `And then.`).

Known limits: deliberate repeats not on the list are cut ("Thank you, thank you" → "Thank you");
a repeat across a seam where the earlier piece already ended a run can't take back what was
pasted; Transcription Mode chunks are chopped one at a time, without rule 6.

There is no repetition control at decoding: sherpa-onnx's transducer search has no repetition
penalty, and the repeats are faithful to the audio. The lasting fix is training transcripts that
leave false starts out (the disfluency dataset); this is the deterministic layer that works with it.

The shared test set is `disfluency-cases.json` (desktop `tests/test_disfluency.py`; Android
`scripts/check_disfluency.sh` runs it on the JVM). The patterns use only lookarounds,
`\p{L}`/`\p{N}` (Kotlin) or `[^\W_]` (Python) and case-insensitive matching (I: ICU, Android's
regex engine, supports all of them).

## Known limits

- A capitalised filler alone at the end of a piece (insert-as-you-go) cannot capitalise the next
  word, which arrives in the next piece.
- The source patterns and their risk notes: `ASR-Regex-Post-Processing/topics/disfluencies.md`
  (Daniel's regex notebook).
