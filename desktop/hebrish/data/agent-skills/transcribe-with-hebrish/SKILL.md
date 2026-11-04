---
name: transcribe-with-hebrish
description: 'Transcribe audio files (voice notes, recordings, meetings; mp3, wav, m4a, ogg, flac and anything ffmpeg reads) on this computer with the Hebrish desktop app (hebrish.app) through its local API at http://127.0.0.1:8723, an OpenAI-compatible endpoint that needs no key and sends nothing off the machine. English with Hebrew words written correctly in romanized form (makolet, arnona). Use when a user asks to transcribe an audio file or folder of recordings locally, with Hebrish, or without a cloud service. Do NOT use for live dictation into apps (that is the Hebrish hotkey), for installing Hebrish (use install-hebrish-linux), or for audio that is entirely in Hebrew.'
license: MIT
compatibility: The Hebrish desktop app (Ubuntu or Windows) with Settings, Local API (added after 1.013), running with a model loaded; curl. Works offline.
---

# Transcribe with Hebrish

Hebrish is Daniel Rosehill's dictation app, a personal project (hebrish.app). Its desktop app can serve
the model it has loaded as a **local API**: a program on the same computer posts an audio file
and gets the text back. Nothing leaves the computer and there is no API key. The output is
English with Hebrew words in romanized form (*makolet*, *arnona*), never Hebrew script.

## Rules for the agent

- The API is `http://127.0.0.1:8723` unless the user changed the port in Settings, Local API.
  It only answers on this computer.
- Send files as they are: the app converts any format ffmpeg reads. Do not resample or split
  them first; long files are split by the app.
- Do not send a browser-style `Origin` header: requests with one are refused (403).
- One request at a time is enough; the app decodes on the CPU and queues requests behind
  each other and behind the user's own dictation.
- The text has no paragraphs. If the user wants paragraphs or a summary, do that yourself from
  the returned text, and say so.

## 1. Check that the API is up

```bash
curl -s http://127.0.0.1:8723/health
```

- `{"status": "ok", ... "model": {...}}`: ready. Tell the user which model answers
  (`model.name`).
- `{"status": "no_model", ...}`: Hebrish is running but no model is loaded yet (still
  downloading or loading). Wait, or ask the user to pick a model on the Models tab.
- Connection refused, or no reply: the local API is off, or Hebrish is not running. Ask the user
  to open Hebrish, go to **Settings → Local API** and tick *Serve transcription to apps on this
  computer*. If they would rather you do it, set `"local_api": true` in the config file
  (`~/.config/hebrish/config.json` on Linux, `%APPDATA%\Hebrish\config.json` on Windows) while
  Hebrish is closed, then start Hebrish again. If Settings has no Local API card, the app is
  too old: update it (on Ubuntu, `sudo apt update && sudo apt install hebrish`).
- The Local API card says the port is in use: another program has 8723. The user can choose
  another port there; use that port below.

## 2. Transcribe a file

Plain text:

```bash
curl -s http://127.0.0.1:8723/v1/audio/transcriptions \
  -F file=@"/path/to/note.mp3" -F response_format=text
```

JSON, with the audio length and processing time:

```bash
curl -s http://127.0.0.1:8723/v1/audio/transcriptions \
  -F file=@"/path/to/note.mp3" -F response_format=verbose_json
```

`response_format` is `json` (default, `{"text": "..."}`), `text` or `verbose_json`
(`text`, `duration`, `processing_s`, `model`). Expect roughly 5 to 10 seconds of processing
per minute of audio on a recent laptop CPU.

Errors come back as `{"error": {"message": "..."}}`: 400 the file could not be read as audio
(install `ffmpeg` for formats other than wav, flac, ogg and mp3), 503 no model loaded, 413 a
file over 1 GB.

## 3. A folder of recordings

Write each transcript next to its recording, skipping ones already done:

```bash
for f in /path/to/folder/*.{mp3,m4a,wav,ogg,flac}; do
  [ -e "$f" ] || continue
  out="${f%.*}.txt"
  [ -e "$out" ] && continue
  curl -sf http://127.0.0.1:8723/v1/audio/transcriptions \
    -F file=@"$f" -F response_format=text > "$out" || { rm -f "$out"; echo "failed: $f"; }
done
```

Ask before writing into a folder the user did not name.

## 4. From code

The endpoint follows the OpenAI audio transcription API, so the OpenAI SDKs work with a
different base URL; the SDK wants a key, and any value does (`export OPENAI_API_KEY=local`):

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8723/v1")
with open("note.mp3", "rb") as f:
    print(client.audio.transcriptions.create(model="hebrish", file=f).text)
```

`model` is ignored: the model loaded in the app answers. To change it, the user picks another
model on the Hebrish Models tab.

## Limits

- The models are trained on one speaker's voice; other voices work, with more errors.
- Speech that is entirely in Hebrew is not what Hebrish is for: it writes English, with Hebrew
  words romanized.
- Transcription Mode in the app gives the same text, plus paragraphs and the optional clean-up
  model; the API returns the text without them, and nothing is saved in the app's History.
