# Hebrish for Android: on-device voice keyboard

[![Download APK v0.2.2](https://img.shields.io/badge/Download_APK-v0.2.2-24527A?logo=android)](https://cdn.hebrish.app/downloads/android/Hebrish-v0.2.2.apk)
[![Website: hebrish.app](https://img.shields.io/badge/Website-hebrish.app-1F6FEB?logo=googlechrome&logoColor=white)](https://hebrish.app)

**Website for the English-Hebrew code-switching model: [hebrish.app](https://hebrish.app)**: get the Hebrish keyboard for Android and the desktop apps, see the results, and find every model, dataset and demo in one place.

> **Early testing build.** Not yet run on a device under this name; see
> [`docs/maintaining.md`](docs/maintaining.md) for what is verified.

**What it does.** An Android voice input method (IME) running NVIDIA **Parakeet TDT 0.6B v2**
**fully on the phone**. You choose which model it uses (below). Nothing you say is sent
anywhere; the only network use is downloading a model from Hugging Face and checking for a
newer version of it.

**Just want to hear it?** Install the APK, open the app, pick a model, let it download, and
tap **Try it now**. That opens a notepad with a mic button: tap, talk, tap again. No keyboard
setup is needed.

## Models

| Model | Status | What it is |
| --- | --- | --- |
| **Parakeet (stock)** | available | NVIDIA's release, unchanged. General English, any speaker. The default |
| **English-Hebrew code-switching** | available | Fine-tuned on English with Hebrew words in it, written in Latin letters. One speaker's voice |
| **Technical vocabulary** | coming soon | Software, AI and infrastructure terms |
| **Personal (general)** | coming soon | General English in one speaker's (Irish-accented) voice |

The list comes from [`../shared/models.json`](../shared/models.json). The APK carries a copy,
and every update check fetches the current one from GitHub, so a model published later
shows up without installing a new APK. "Coming soon" models are listed but can't be picked.

Picking a model in **1. Model** switches the keyboard to it at once. If it isn't on the phone
yet, the screen offers **Download** (about 660 MB per model, once). Models you downloaded
earlier stay on the phone, so switching back is instant; **Delete other models…** removes
them.

The **Hebrish** section at the bottom of the setup screen links to
[hebrish.app](https://hebrish.app), the code-switching model's website. Report a bug, Request a
feature and Send feedback open your email app with a message to feedback@hebrish.app; Suggest
a word, Send voice samples and Get involved open the site's contact form.

## Install (recommended setup)

1. Install **[HeliBoard](https://github.com/Helium314/HeliBoard/releases)** and make it your
   main keyboard.
2. Download the APK from the
   [APK (v0.2.2)](https://cdn.hebrish.app/downloads/android/Hebrish-v0.2.2.apk)
   and install it. You will need to allow installs from your browser or file manager.
3. Open **Hebrish** and work through it:
   - **Pick a model** and **Download** it. It is about 660 MB, downloaded once; use Wi-Fi.
     The download resumes if interrupted and is checked against SHA-256.
   - Optional, **Model location → Choose folder**: keep the model in a shared folder
     (internal storage or SD card) instead of app storage, so other on-device ASR apps can
     load the same files. This needs Android's *All files access* permission, because
     sherpa-onnx opens model files by path. The app writes into
     `<chosen folder>/<HF repo name>/<version>/`, one folder per model (e.g.
     `sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8/v2-1ab9323565dd/`), holding
     `encoder.int8.onnx`, `decoder.int8.onnx`, `joiner.int8.onnx` and `tokens.txt`: a standard
     sherpa-onnx NeMo transducer. Already-downloaded models are copied there; a model already
     present there is used as is.
   - **Model updates**: when a newer version of the selected model is published on Hugging
     Face, the setup screen shows **Update to vN**. The new model downloads alongside the old one, which you
     keep using until the new files have been downloaded and checked. Then the old one is
     deleted. The screen checks when you open it, or tap **Check for update**.
   - **Grant** the microphone.
   - **Keyboard settings**: turn on *Hebrish*.
4. In HeliBoard, make the voice input key visible (toolbar key or the key by the space bar).

HeliBoard is the main keyboard and this app is its companion voice input method. Tapping
HeliBoard's mic opens Hebrish, which **starts recording at once**. Tap the mic again
to stop. The transcript is inserted and you are **taken back to HeliBoard**. Both behaviours
can be switched off in the app. Any keyboard that opens a "voice" input method works the
same way, and you can also switch to Hebrish directly from the system keyboard
picker.

Voice keyboard keys: previous keyboard · delete · **mic** · space · enter.

- **Getting back to your keyboard:** tap the keyboard key or press **Back**. Long-press the
  keyboard key for the system picker. If you leave mid-take, what you said is still
  transcribed and inserted first. Under *Keyboard to return to* you can fix a target keyboard
  in case the automatic choice gets it wrong.
- **During a take:** **Pause / Resume**, **Restart** (throw it away and start again) and
  **Discard**.
- **Insert last transcript:** if no text field had focus when the transcript came back, it
  is kept, and this button types it in once you tap a field.

## Model details

| | |
| --- | --- |
| Base | [`nvidia/parakeet-tdt-0.6b-v2`](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2) (v2 on purpose, not v3) |
| Stock | [`csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8`](https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8), files at the repo root |
| Code-switching | [`Hebrish/Jachnun-sherpa-onnx-int8`](https://huggingface.co/Hebrish/Jachnun-sherpa-onnx-int8), files at the root (since 2026-10-19; the main repo is gated). The app downloads whatever version is on HF `main` |
| Format | sherpa-onnx int8 (encoder, decoder, joiner, tokens), about 660 MB per model |
| Offline fallback (`ModelStore.BUNDLED`) | stock v2 at rev `1ab9323565dd`; code-switching v1.0 at rev `bb137e504b97` of the mirror (since 0.2.1). Used only when HF can't be reached on a first download |
| Runtime | [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 1.13.8 Android AAR, CPU, greedy search |

The fine-tunes are trained on a single speaker's voice, so expect them to work best for that
voice. Output is punctuated and cased, numbers come out as digits, and Hebrew words are
written in Latin script (the v2 tokenizer has no Hebrew characters).

## Limits

- **Offline (whole-utterance) recognition.** Text appears after you stop, not while you
  speak. Takes stop automatically at **90 s**.
- The first transcription after the process starts loads the 650 MB encoder, which takes a
  few seconds. Later ones are fast while Android keeps the app alive.
- arm64-v8a phones only, Android 9 (API 28) or newer.

## Build

```bash
echo "sdk.dir=$HOME/Android/Sdk" > local.properties
JAVA_HOME=/path/to/jdk-21 ./gradlew assembleRelease   # downloads the sherpa-onnx AAR on first build
```

Without the `RELEASE_*` env vars the release APK is signed with the debug key. Releases come
from `../.github/workflows/android.yml`: push an `android-vX.Y.Z` tag and it builds a signed APK and
attaches it to a GitHub release. Maintainer notes are in [`docs/maintaining.md`](docs/maintaining.md).

## Related

- Code-switching fine-tune project:
  [English-Hebrew-Codeswitching-Parakeet-Finetune](https://github.com/Hebrish-ASR/English-Hebrew-Codeswitching-Parakeet-Finetune)

## License

App code: MIT. The models carry their own licenses on Hugging Face; the base
model is NVIDIA's CC-BY-4.0.
