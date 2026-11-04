---
name: read-hebrish-history
description: 'Read, search and export what the user dictated from the Hebrish desktop app''s transcript history (hebrish.app) through its local API at http://127.0.0.1:8723. Nothing leaves the computer unless the user asks. Use when a user asks what they dictated, to find or recover something they said, to export or summarise their transcripts, or for dictation stats. Do NOT use for transcribing an audio file (use transcribe-with-hebrish), for correcting recurring errors (use fix-hebrish-mistranscriptions), or for the Android app.'
license: MIT
compatibility: The Hebrish desktop app (Ubuntu or Windows), 1.018 or later, running with Settings, Local API and its control option on; curl. Works offline.
---

# Read Hebrish history

Hebrish is Daniel Rosehill's dictation app, a personal project (hebrish.app). The desktop app keeps
every transcript on this computer, and its **local API** serves them to programs on the same
computer. The text is English with Hebrew words romanized (*makolet*, *arnona*).

## Rules for the agent

- The API is `http://127.0.0.1:8723` unless the user changed the port in Settings, Local API.
- Do not send an `Origin` header: requests with one are refused (403).
- Transcripts are private. Fetch what the task needs, and do not paste long stretches back or send
  them to another service unless the user asks.
- The API reads only. Editing or deleting transcripts is done in the app's History tab.

## 1. Check that control is on

```bash
curl -s http://127.0.0.1:8723/health
```

`"control": true` means go on. `"control": false`: ask the user to open Hebrish, **Settings → Local
API**, and tick *Let agents read history and control the app*. No `control` key: the app is too old,
use the `update-hebrish` skill. Connection refused: Hebrish is not running, or the local API is off.

## 2. Latest transcripts

```bash
curl -s 'http://127.0.0.1:8723/v1/history?limit=20'
```

The reply is `{"object": "list", "total": N, "limit": ..., "offset": ..., "data": [...]}`, newest
first. Each row has `id`, `uid`, `at` (unix time), `text`, `words`, `seconds`, `model`, `source`
(`dictate`, `record`, `file`, `import`) and `original` (the model's text, when the user edited it;
otherwise null).

## 3. Search and filter

```bash
curl -s -G http://127.0.0.1:8723/v1/history --data-urlencode 'q=arnona bill' -d limit=50
```

`q` is a keyword search, best match first, and adds `snippet` with the matches in `[brackets]`.
Other query parameters, which combine with it:

| Parameter | Meaning |
| --- | --- |
| `limit`, `offset` | Page size (1 to 1000, default 50) and start |
| `since`, `until` | Unix time; `until` is exclusive |
| `source` | One of the `source` values above |
| `edited=1` | Only transcripts the user corrected by hand |

Yesterday, on Linux:

```bash
curl -s -G http://127.0.0.1:8723/v1/history \
  -d since=$(date -d 'yesterday 00:00' +%s) -d until=$(date -d 'today 00:00' +%s) -d limit=1000
```

One transcript: `curl -s http://127.0.0.1:8723/v1/history/123`.

## 4. Export everything

Page through `offset` until a page comes back short:

```bash
offset=0
while :; do
  page=$(curl -sf "http://127.0.0.1:8723/v1/history?limit=1000&offset=$offset") || break
  echo "$page" | jq -c '.data[]' >> hebrish-history.jsonl
  [ "$(echo "$page" | jq '.data | length')" -lt 1000 ] && break
  offset=$((offset + 1000))
done
```

Needs `jq`. Ask where to write it if the user did not say. The app's Settings, Your data also
exports and backs up.

## Limits

- `GET /v1/app/status` has `keep_history`. When it is false the app is not saving new transcripts,
  so an empty result says nothing about what was dictated.
- History is per computer. The Android app's history is not here.
- Files sent to the local API for transcription are not saved in History.
