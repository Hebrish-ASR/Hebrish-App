# Hebrish Dictation

**On-device dictation with NVIDIA Parakeet, for Android, Linux and Windows.** Made for the
English-Hebrew code-switching model; stock Parakeet is there too.

![Hebrish on Linux: the Models tab, one card per model with its own Download button](docs/screenshots/desktop-model.png)

Everything runs **on your device**. The only network traffic is downloading the model you
pick (~630 MB, once) and a periodic check for a newer version.

**Name:** the apps were first released as **Parlance** (0.1.0–0.1.2, 2026-10-19). Since
0.2.0 every identifier is Hebrish too: Android application ID `app.hebrish.dictation`, desktop
package and command `hebrish`, config and data under `hebrish`, default hotkey F14. Hebrish 0.2.0
is a fresh install. **Parlance continues as a separate general-purpose app**
([danielrosehill/Parlance-Dictation](https://github.com/danielrosehill/Parlance-Dictation)) that
keeps every `parlance` identifier and hotkey F13, so the two install side by side; an existing
0.1.x install becomes Parlance when Parlance 0.2.0 updates it. On first start the Hebrish desktop
app copies Parlance's settings (not its hotkey) and hardlinks its downloaded models.

**Website for the English-Hebrew code-switching model: [hebrish.app](https://hebrish.app)**: get the Hebrish keyboard for Android and the desktop apps, see the results, and find every model, dataset and demo in one place.

## Models

Every model is [Parakeet TDT 0.6B v2](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2),
run with sherpa-onnx (int8).

| Model | Status | For |
| --- | --- | --- |
| **Jachnun** | available | English + Hebrew vocabulary (*teudat zehut*, *arnona*, *bituach leumi*), written in Latin letters. Recommended; the Android app's default since 0.6.0. [Models](https://hebrish.app/models#parakeet) |
| **Sabich** | available | Hebrew vocabulary + tech vocabulary: code-switching plus tech terms, brand names and numbers. [Models](https://hebrish.app/models#sabich) |
| **Parakeet (stock)** | available | Standard English, without the Hebrew words. NVIDIA's release, unchanged |

The fine-tunes are trained on **one speaker's voice**; recordings from more voices are welcome
([hebrish.app/contact?topic=samples](https://hebrish.app/contact?topic=samples)). Those are the only
models Hebrish ships. The other Parakeet fine-tunes (technical vocabulary, personal voice) are in
[Parlance](https://github.com/danielrosehill/Parlance-Dictation), the general-purpose twin of this
app; `desktop/tests/test_shared.py` fails if any other model appears in this catalogue.

On held-out recordings, the code-switching model (v3, the latest benchmarked version) cut
word error rate on code-switched English from 10.9% to 5.3%, and plain English got slightly
better, not worse. Training data, every version's results and the roadmap:
[English-Hebrew-Codeswitching-Parakeet-Finetune](https://github.com/Hebrish-ASR/English-Hebrew-Codeswitching-Parakeet-Finetune).

To help improve it, both apps have **Report a bug**, **Request a feature** and **Send
feedback**, which open an email to [feedback@hebrish.app](mailto:feedback@hebrish.app) with the
app and OS version filled in, and link to hebrish.app's contact form to
[suggest a word](https://hebrish.app/contact?topic=word),
[send voice samples](https://hebrish.app/contact?topic=samples) or
[get involved](https://hebrish.app/contact?topic=involved). On Android they are in the
**Hebrish** section at the bottom of the setup screen; on the desktop, in the tray's
**Hebrish** submenu, the About tab, and on each Hebrish model's card in the Models tab.

## Download

| Platform | What it is |
| --- | --- |
| **Android** | A voice keyboard (IME), the companion voice input for HeliBoard or any keyboard, plus an optional floating mic that dictates into any app without switching keyboards (0.3.0+). Android 9+, arm64. For a full keyboard with dictation built in, see [Hebrish Keyboard](https://github.com/Hebrish-ASR/Hebrish-Keyboard), a HeliBoard fork |
| **Ubuntu** | A tray app for Ubuntu 26.04 amd64 (.deb) |
| **Windows** | A portable tray app (.zip): unzip and run `Hebrish.exe` |

Which features each platform has, and which released builds are behind the code: [`docs/feature-parity.json`](docs/feature-parity.json).

Builds are on the [releases page](https://github.com/Hebrish-ASR/Hebrish-App/releases):
tags `android-v*` carry the APK, tags `desktop-v*` the .deb and the Windows zip. The Windows
build and the Android app have not yet been tried on real hardware.

## Desktop app (Linux and Windows)

- **Dictate**: press a hotkey anywhere (or Talk in the window), talk, and the text is pasted
  where your cursor is, inserted as you go every ~10 s. Output can also be the clipboard or the
  window's text box. The Dictate tab shows the microphone in use, a switcher, a level meter with
  a clip lamp, and a voice-detection toggle. Feedback is beeps, short spoken prompts, or off.
  Two hotkeys, any key or a foot pedal: a toggle key (tap to start, tap to stop; holding it
  is push-to-talk too, unless you turn that off) and an optional push-to-talk key. An optional
  floating overlay, like the Android floating mic, shows the take with Pause, Retake and Discard.
- **File**: drop or open an audio file. The transcript fills an editable text box piece by
  piece; save it as .txt or .md.
- **Models**: a card per model (Jachnun, Sabich, stock Parakeet) with its own Download, Use
  and Delete; choose the folder the weights are stored in. History is optional (off by default).

Ubuntu: `sudo apt install ./hebrish_<version>-1_amd64.deb`, then
`sudo usermod -aG input $USER` for the hotkey, and log in again. It replaces Voice To
Hebrish and Parakeet-Type-Ubuntu, and keeps Voice To Hebrish's settings and downloaded
model. Details: [`desktop/README.md`](desktop/README.md).

## Android app

A voice keyboard (IME). Open the app, pick a model, and tap **Try it now** to test it in a
built-in notepad before setting anything up. Once it's set up, HeliBoard's mic key opens it,
you talk, and you're returned to HeliBoard with the text inserted. Details:
[`android/README.md`](android/README.md).

## Repository layout

| Path | What |
| --- | --- |
| `desktop/` | Linux + Windows app (Python, PySide6, sherpa-onnx). Only the hotkey and paste code differs per OS |
| `android/` | Android voice keyboard (Kotlin, sherpa-onnx AAR) |
| `shared/models.json` | The model catalogue both apps bundle and re-fetch; a test fails if either app's copy drifts |
| `shared/update-protocol.md` | How models are listed, downloaded and updated, and the quirks both apps work around |

Releases: tag `android-vX.Y.Z` builds the signed APK in CI. Tag `desktop-vX.Y.Z` builds the
Windows zip in CI; the Ubuntu .deb is built with `desktop/build-deb.sh` and added to the same
release. Then copy all three to the Hebrish CDN, `https://cdn.hebrish.app/downloads/{android,ubuntu,windows}/`,
and rewrite `downloads/latest.json` (the `r2-upload` skill in `parakeet-finetune-ops`). hebrish.app needs no
edit: since 2026-10-20 its buttons link `hebrish.app/get/<platform>`, which redirects to the file `latest.json`
names. The F-Droid repository (Hebrish-ASR/Hebrish-FDroid) checks GitHub releases hourly and picks up the new APK. Adding a model needs no release:
see `shared/update-protocol.md`.

## History

Hebrish Dictation (first released as Parlance, 2026-10-19) is the successor to all of the author's earlier Parakeet dictation
apps, and the only one maintained:

- **Voice To Hebrish** (2026-10-18), the Android + desktop monorepo this repo was copied
  from, history included. It ran only the code-switching model.
- Before that, *English-Hebrew-Codeswitching-Voice-Keyboard-Android* ("Codeswitch Voice")
  and *English-Hebrew-Codeswitching-Dictation-Linux* ("Codeswitch Dictation").
- **Parakeet-Type-Ubuntu** (`parakeet-dictation`), a KDE-only app with stock and
  code-switching profiles.

## License

Apps: MIT. Fine-tuned models: CC-BY-4.0. Stock Parakeet: CC-BY-4.0 (NVIDIA).
