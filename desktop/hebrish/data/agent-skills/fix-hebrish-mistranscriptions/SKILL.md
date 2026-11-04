---
name: fix-hebrish-mistranscriptions
description: 'Find words and phrases the Hebrish desktop app (hebrish.app) keeps getting wrong and add find-and-replace rules for them to its personal dictionary through the local API at http://127.0.0.1:8723, testing each rule against the user''s real transcript history first. Handles names, brands and multi-word phrases, for example My Word Prompts written for My Weird Prompts. Use when a user says Hebrish keeps mishearing or misspelling something, asks to add a replacement or dictionary word, or asks to find recurring errors. Do NOT use for one-off typos in a single transcript, for words the model never produces at all (no rule can create them), or for the Android app.'
license: MIT
compatibility: The Hebrish desktop app (Ubuntu or Windows), 1.018 or later, running with Settings, Local API and its control option on; curl. Works offline.
---

# Fix Hebrish mistranscriptions

Hebrish is Daniel Rosehill's dictation app, a personal project (hebrish.app). Its **personal
dictionary** is a find-and-replace list applied to the model's text after decoding. An entry is a
`word` (how it should be written, which can be a whole phrase or sentence) and `heard` phrases (what
the model writes instead). This skill finds good rules and proves them against the user's own
transcript history before adding them.

## Rules for the agent

- The API is `http://127.0.0.1:8723` unless the user changed the port in Settings, Local API.
- Do not send an `Origin` header: requests with one are refused (403).
- **Preview every rule before adding it.** Preview writes nothing.
- A pair the user named outright: preview it, add it, report the result. Pairs you found yourself:
  show the table in step 3 and add only what the user agrees to.
- Write Hebrew words in the user's romanization, never in Hebrew script.

## How matching works

- Case does not matter, whole words only, and any run of spaces or line breaks matches any other.
- Each `heard` phrase is otherwise **literal**: `my word prompts` does not match `my word, prompts`.
  Add the punctuated form as a second phrase if history shows it. A phrase can run across sentences
  if it is written with the punctuation the model uses.
- A `word` with a capital letter is always written exactly as entered.
- The `word` itself also matches, so one entry fixes capitalisation too (`My Weird prompts`). This
  means an entry `IT` turns every "it" into "IT".
- The longest match wins, and a replacement is never matched again.
- With insert-as-you-go on, each piece is corrected alone, so a phrase cut in two by a pause is
  missed. Nothing can be done about that from the dictionary.

## 1. Check that control is on

```bash
curl -s http://127.0.0.1:8723/health
```

`"control": true` means go on. `"control": false`: ask the user to open Hebrish, **Settings → Local
API**, and tick *Let agents read history and control the app*. No `control` key: the app is too old,
use the `update-hebrish` skill. Connection refused: Hebrish is not running, or the local API is off.

Read what is there, so you do not add duplicates:

```bash
curl -s http://127.0.0.1:8723/v1/dictionary
```

## 2. Find candidates

Skip this if the user named the pair. Otherwise look in this order:

1. **The user's own corrections**, the strongest evidence. `original` is the model's text and `text`
   is what the user changed it to. Diff them, and keep what recurs:

   ```bash
   curl -s 'http://127.0.0.1:8723/v1/history?edited=1&limit=1000'
   ```

2. **Variants of a known term.** For a name the user mentions, search its parts and read the
   neighbouring words, since `q` matches words, not misspellings:

   ```bash
   curl -s -G http://127.0.0.1:8723/v1/history --data-urlencode 'q=prompts' -d limit=200
   ```

3. **Oddities in recent text.** Read the last few hundred transcripts for phrases that make no sense
   in context, and for a name spelled several ways.

Keep a candidate only if it recurs. One sighting is a typo, not a rule.

## 3. Preview each rule

```bash
curl -s -X POST http://127.0.0.1:8723/v1/dictionary/preview \
  -H 'Content-Type: application/json' \
  -d '{"word": "My Weird Prompts", "heard": ["my word prompts"], "limit": 20}'
```

The reply has `rows_scanned`, `rows_changed`, `replacements`, `by_source` (each form found, with its
count) and `samples` (`id`, `before`, `after`, with context).

Read the samples and judge:

- **Every sample is a fix:** keep it.
- **Some samples were right as they were:** the phrase is too broad. Lengthen it with a neighbouring
  word and preview again. Never add a rule on a common word by itself (`word` → `weird`).
- **`rows_changed` is 0:** the phrase is not in the history. Check the spelling against a real
  transcript. Add it only if the user is sure it happens.
- **`by_source` shows a form you did not expect:** read that sample. It is usually the `word`
  matching its own split or lower-case form, which is fine.

For rules you found yourself, show the user: rule, rows changed, one sample, your verdict.

## 4. Add the rule

```bash
curl -s -X POST http://127.0.0.1:8723/v1/dictionary \
  -H 'Content-Type: application/json' \
  -d '{"word": "My Weird Prompts", "heard": ["my word prompts"]}'
```

Adding to an existing `word` merges the phrases and keeps the old ones (reply 200; a new word is
201). It applies from the next take, with no restart, and the Dictionary tab updates by itself.

To undo, a word or just one phrase:

```bash
curl -s -X DELETE -G http://127.0.0.1:8723/v1/dictionary \
  --data-urlencode 'word=My Weird Prompts' --data-urlencode 'heard=my word prompts'
```

Leave out `heard` to remove the whole word.

## Limits

- Old transcripts are not rewritten. Rules apply to new text.
- A rule fixes a word the model writes wrongly **and consistently**. If it writes something
  different each time, each form needs a phrase, and retraining is the real fix: tell the user to
  send it through <https://hebrish.app/feedback>.
- The desktop dictionary is not synced with Android, which uses the phone's personal dictionary.
