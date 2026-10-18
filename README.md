# Codeswitch Voice: English–Hebrew voice keyboard for Android

[![Download APK](https://img.shields.io/github/v/release/danielrosehill/English-Hebrew-Codeswitching-Voice-Keyboard-Android?label=Download%20APK&logo=android&color=2E7D6B)](https://github.com/danielrosehill/English-Hebrew-Codeswitching-Voice-Keyboard-Android/releases/latest)
[![Model on HF](https://img.shields.io/badge/%F0%9F%A4%97%20Model-Parakeet%20TDT%200.6B%20v2%20EN--HE%20(v3)-yellow)](https://huggingface.co/danielrosehill/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching)
[![Dataset on HF](https://img.shields.io/badge/%F0%9F%A4%97%20Dataset-Read--Aloud--Voice--Sentences-yellow)](https://huggingface.co/datasets/danielrosehill/Read-Aloud-Voice-Sentences)

> **Early testing build.** This app exists to test English–Hebrew code-switching
> dictation on Android with a fine-tuned **Parakeet TDT 0.6B v2**. It is not a finished
> keyboard.

**What it does.** This is an Android voice input method (IME). You speak English with
Hebrew words mixed in ("I'll meet you at the *makolet* after *Shabbat*"), and it types the
English with the Hebrew words **romanized**. Recognition runs **fully on the phone**; nothing
is sent anywhere. The only network use is a single model download from Hugging Face.

## Install (recommended setup)

1. Install **[HeliBoard](https://github.com/Helium314/HeliBoard/releases)** and make it your
   main keyboard.
2. Download the APK from the
   [latest release](https://github.com/danielrosehill/English-Hebrew-Codeswitching-Voice-Keyboard-Android/releases/latest)
   and install it. You will need to allow installs from your browser or file manager.
3. Open **Codeswitch Voice** and work through it:
   - **Download** the model. It is about 660 MB, downloaded once; use Wi-Fi. The download
     resumes if interrupted and is checked against SHA-256.
   - Optional, **Model location → Choose folder**: keep the model in a shared folder
     (internal storage or SD card) instead of app storage, so other on-device ASR apps can
     load the same files. This needs Android's *All files access* permission, because
     sherpa-onnx opens model files by path. The app writes into
     `<chosen folder>/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching/<version>/`
     (`encoder.int8.onnx`, `decoder.int8.onnx`, `joiner.int8.onnx`, `tokens.txt`: a standard
     sherpa-onnx NeMo transducer). An already-downloaded model is copied there; a model already
     present there is used as is.
   - **Grant** the microphone.
   - **Keyboard settings**: turn on *Codeswitch Voice*.
4. In HeliBoard, make the voice input key visible (toolbar key or the key by the space bar).

HeliBoard is the main keyboard and this app is its companion voice input method. Tapping
HeliBoard's mic opens Codeswitch Voice, which **starts recording at once**. Tap the mic again
to stop. The transcript is inserted and you are **taken back to HeliBoard**. Both behaviours
can be switched off in the app. Any keyboard that opens a "voice" input method works the
same way, and you can also switch to Codeswitch Voice directly from the system keyboard
picker.

Voice keyboard keys: previous keyboard · delete · **mic** · space · enter.

## The model

| | |
| --- | --- |
| Base | [`nvidia/parakeet-tdt-0.6b-v2`](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2) (v2 on purpose, not v3) |
| Fine-tune | **v3** (training run `r3-en30`), English–Hebrew code-switching |
| Model card | [danielrosehill/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching](https://huggingface.co/danielrosehill/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching) |
| Training data | [danielrosehill/Read-Aloud-Voice-Sentences](https://huggingface.co/datasets/danielrosehill/Read-Aloud-Voice-Sentences) (code-switching subset: [English-Hebrew-Codeswitching-Sentences](https://huggingface.co/datasets/danielrosehill/English-Hebrew-Codeswitching-Sentences)) |
| Format used here | `sherpa-onnx/int8/` (encoder, decoder, joiner, tokens), about 660 MB |
| Pinned HF revision | `92679110e821baf9425f620c9deb9920ce9b7539` |
| Runtime | [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 1.13.8 Android AAR, CPU, greedy search |

The fine-tune is trained on a single speaker's voice, so expect it to work best for that
voice. Output is punctuated and cased, numbers come out as digits, and Hebrew is written in
Latin script (the v2 tokenizer has no Hebrew characters).

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
from `.github/workflows/release.yml`: push a `vX.Y.Z` tag and it builds a signed APK and
attaches it to a GitHub release. Maintainer notes are in [`docs/maintaining.md`](docs/maintaining.md).

## Related

- Fine-tune project tracker:
  [English-Hebrew-Codeswitching-Parakeet-Finetune](https://github.com/danielrosehill/English-Hebrew-Codeswitching-Parakeet-Finetune)

## License

App code: MIT. The model and dataset carry their own licenses on Hugging Face; the base
model is NVIDIA's CC-BY-4.0.
