---
date: 2026-11-12
platform: desktop-linux
environment: KDE Plasma Wayland, Ubuntu 26.04, Hebrish 1.031 (.deb)
component: desktop/hebrish/ui/transcribe.py, desktop/hebrish/ui/app.py
affected: "1.012 - 1.031"
fixed_in: "1.032"
status: fixed
---

# Transcription: levels look fine, but no transcript ever shows up in the Notepad

## Symptom
Daniel recorded a few seconds on the Transcription tab. The level meter moved, but nothing
appeared in the Notepad. He suspected the text was going to the system cursor instead.

## Cause
Two behaviours, both by design and both surprising:
1. **Stop didn't transcribe.** The square Stop button only held the recording; the transcript
   came from the separate green Transcribe (send arrow) button. (V) The 5.2 s recording made at
   23:51:56 was still in `~/.local/share/hebrish/recordings/`, untranscribed: with Save audio off
   a transcribed recording is deleted, and a failed transcription shows a dialog.
2. **Voice Typing was kept out of the Notepad.** Since 1.012, when the Notepad had focus a Voice
   Typing take was neither pasted nor put in the box: it went to the clipboard and History only.
   (V) History row 89 ("Testing 123, 123.", source `dictate`, 23:51:50) was taken a few seconds
   before the recording, with the tab open.

Nothing was being pasted at the system cursor from the Transcription recorder: its transcript has
only ever gone into its own box (`_place`).

## How it was found
History DB rows around the report time, the recordings folder (the held .wav, its length from
the WAV header), the config (`tm_save_audio` false), and reading `_stop` / `_transcribe_tape` and
`Controller._insert`.

## Fix
1.032: Stop stops and transcribes; Transcribe shows only for a recording the recorder held by
itself. With focus anywhere on the Transcription tab, a Voice Typing take (and Paste last) goes
into the Notepad at its cursor. Rules in `desktop/docs/maintaining.md`, Transcription Mode.

## Verified / not verified
- (V) Off-screen tests: `tests/test_notepad.py` (Stop calls the transcription path, Transcribe
  hidden until a recording is held, focus on the tab routes dictation into the Notepad).
- (I) Not yet run with a real hotkey take on the Transcription tab of the installed build.
