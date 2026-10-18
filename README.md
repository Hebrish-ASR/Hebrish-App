# Voice To Hebrish

**Dictation for Anglos in Israel.** It knows *makolet* isn't *Macaulay*.

*"Voice To Hebrish" is a working title. It is also, frankly, a gag.*

You say *"I'll grab bamba from the makolet, then I have to deal with the arnona,"* and
ordinary speech recognition writes *"Micollette"* and gives up on the rest. These apps run a
fine-tune of NVIDIA's Parakeet that was trained on exactly that kind of English: English
with Hebrew words dropped in, written in Latin letters (*teudat zehut*, *bituach leumi*,
*rishayon iski*). Linguists call it code-switching. Everybody else calls it Hebrish.

Everything runs **on your device**. The only network traffic is the one-time model download
(~660 MB) and a periodic check for a newer fine-tune.

## Download

| Platform | Get it | What it is |
| --- | --- | --- |
| **Android** | [APK](https://github.com/danielrosehill/Voice-To-Hebrish/releases/download/android-v0.5.0/VoiceToHebrish-v0.5.0.apk) | A voice keyboard, the companion voice input for HeliBoard. Android 9+, arm64 |
| **Ubuntu** | [.deb](https://github.com/danielrosehill/Voice-To-Hebrish/releases/download/desktop-v0.2.0/voice-to-hebrish_0.2.0-1_amd64.deb) | A tray app for Ubuntu 26.04 amd64 |
| **Windows** | [.zip](https://github.com/danielrosehill/Voice-To-Hebrish/releases/download/desktop-v0.2.0/VoiceToHebrish-v0.2.0-windows-x64.zip) | A tray app, portable: unzip and run `VoiceToHebrish.exe` |

All releases: [github.com/danielrosehill/Voice-To-Hebrish/releases](https://github.com/danielrosehill/Voice-To-Hebrish/releases).
These are **proof-of-concept** builds. The Windows build and the Android app have not yet been tried on real
hardware; see each app's notes.

## Desktop app (Linux and Windows)

There are two ways to work:

- **Dictate**: press a hotkey anywhere, talk, and the text is pasted where your cursor is.
  The hotkey can be any key or a foot pedal. Tap it to start and stop, or hold it while
  you talk.
- **Transcribe**: the long-form workflow. Record with a level meter, a timer and pause,
  or open or drop an audio file (WAV, MP3, M4A, OGG, FLAC…). The transcript fills an
  editable text box piece by piece, and you can save it as .txt or .md.

It downloads the model on first run, checks for new fine-tunes on a schedule, and can keep
old versions so you can switch back. It also has a tray icon and an About tab with the
model's training data and benchmark numbers.

Ubuntu: `sudo apt install ./voice-to-hebrish_0.2.0-1_amd64.deb`, then
`sudo usermod -aG input $USER` for the hotkey, and log in again. Details:
[`desktop/README.md`](desktop/README.md).

## Android app

A voice keyboard (IME). HeliBoard's mic key opens it, you talk, and you're returned to
HeliBoard with the text inserted. It updates the model by itself when a new fine-tune is
published. Details: [`android/README.md`](android/README.md).

## The model

[`danielrosehill/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching`](https://huggingface.co/danielrosehill/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching)
is Parakeet TDT 0.6B v2, fine-tuned on several hours of English sentences with Hebrew
words, the speaker's own plain English, and LibriSpeech. On held-out recordings (v3, the
latest benchmarked version), word error rate on Hebrish fell from 10.9% to 5.3%, and plain
English got slightly better, not worse. On a frozen public benchmark it gets 67.4% of
Hebrew words right, against 45.9% for Whisper Large V3 and 32.6% for stock Parakeet.

It is trained on **one speaker's voice** (an Anglo in Jerusalem), so it works best for
voices like that one. The project hub, with the training data, every version's results
and the roadmap:
[English-Hebrew-Codeswitching-Parakeet-Finetune](https://github.com/danielrosehill/English-Hebrew-Codeswitching-Parakeet-Finetune).

## Repository layout

| Path | What |
| --- | --- |
| `desktop/` | Linux + Windows app (Python, PySide6, sherpa-onnx). Only the hotkey and paste code differs per OS |
| `android/` | Android voice keyboard (Kotlin, sherpa-onnx AAR) |
| `shared/model.json` | Where both apps get the model; a test fails if either app drifts from it |
| `shared/update-protocol.md` | How both apps decide a new model is out, and the model's quirks they work around |

Releases: tag `android-vX.Y.Z` builds the signed APK in CI. Tag `desktop-vX.Y.Z` builds the
Windows zip in CI, and the Ubuntu .deb is built with `desktop/build-deb.sh` and added to
the same release.

## History

Until 2026-10-18 these were two repos: *English-Hebrew-Codeswitching-Voice-Keyboard-Android*
("Codeswitch Voice"), which this repo was renamed from, and
*English-Hebrew-Codeswitching-Dictation-Linux* ("Codeswitch Dictation"), merged into
`desktop/` with its history intact.

## License

Apps: MIT. Model: CC-BY-4.0.
