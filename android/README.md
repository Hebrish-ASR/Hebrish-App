[![Download APK v0.5.0](https://img.shields.io/badge/Download_APK-v0.5.0-24527A?logo=android)](https://cdn.hebrish.app/downloads/android/Hebrish-v0.5.0.apk)

[![Download APK v0.4.0](https://img.shields.io/badge/Download_APK-v0.4.0-24527A?logo=android)](https://cdn.hebrish.app/downloads/android/Hebrish-v0.4.0.apk)
[![Website: hebrish.app](https://img.shields.io/badge/Website-hebrish.app-1F6FEB?logo=googlechrome&logoColor=white)](https://hebrish.app)

**Website for the English-Hebrew code-switching model: [hebrish.app](https://hebrish.app)**: get the Hebrish keyboard for Android and the desktop apps, see the results, and find every model, dataset and demo in one place.

> **Early testing build.** Not yet run on a device under this name; see
> [`docs/maintaining.md`](docs/maintaining.md) for what is verified.

**What it does.** An Android voice input method (IME), plus an optional floating mic for any app, running NVIDIA **Parakeet TDT 0.6B v2**
**fully on the phone**. You choose which model it uses (below). Nothing you say is sent
anywhere; the only network use is downloading a model from Hugging Face and checking for a
newer version of it.

**Just want to hear it?** Install the APK, open the app, pick a model, let it download, and
tap **Try it now**. That opens a notepad with a mic button: tap, talk, tap again. No keyboard
setup is needed.

## Models

| Model | Status | What it is |
| --- | --- | --- |
| **Jachnun** | available | English + Hebrew vocabulary: the English-Hebrew code-switching fine-tune, Hebrew words in Latin letters. **Recommended**, and what a new install uses (0.6.0+) |
| **Sabich** | available | Hebrew vocabulary + tech vocabulary: code-switching plus tech terms, brand names and numbers |
| **Parakeet (stock)** | available | NVIDIA's release, unchanged. Standard English, without the Hebrew words |

The fine-tunes are trained on one speaker's voice; more voices are welcome (hebrish.app/contact?topic=samples).

The list comes from [`../shared/models.json`](../shared/models.json). The APK carries a copy,
and every update check fetches the current one from GitHub, so a model published later
shows up without installing a new APK. Hebrish ships only these three; the other fine-tunes are in
[Parlance](https://github.com/danielrosehill/Parlance-Dictation).

The app is a home screen with one screen per area (since 0.4.0): **Models**, **Voice keyboard**,
**Floating mic** (with a step-by-step guide to turning it on), **Dictation**, **Sound, microphone
and buttons**, **Install and updates** (the F-Droid repository, for anyone who installed the APK),
**Help and contact** and (0.6.0) **About**. Since 0.6.0 home opens with the **Setup checklist**
(microphone, a model, the voice keyboard or floating mic, battery unrestricted, "Pause app activity if
unused" off, optional all files access; the same steps with pictures at
[hebrish.app/setup](https://hebrish.app/setup)), has a side menu (☰) with every screen plus Explore
the lexicon and Contribute, and shows the app and model version at the bottom.

**Models** downloads any model whether or not it is the one in use: one at a time, or all of them
with **Download all** (they queue and download one after another; about 660 MB each). **Use this
model** switches the keyboard and floating mic to a downloaded model at once; models stay on the
phone until you **Delete** them, so switching back is instant.

**Help and contact** links to [hebrish.app](https://hebrish.app), the code-switching model's
website. Report a bug, Request a feature and Send feedback open your email app with a message to
feedback@hebrish.app; Suggest a word, Send voice samples and Get involved open the site's contact
form.

## Install (recommended setup)

1. Install **[HeliBoard](https://github.com/Helium314/HeliBoard/releases)** and make it your
   main keyboard.
2. Download the APK from the
   [APK (v0.5.0)](https://cdn.hebrish.app/downloads/android/Hebrish-v0.5.0.apk)
   and install it. You will need to allow installs from your browser or file manager.
3. Open **Hebrish** and work through it:
   - **Models**: **Download** a model (or **Download all**). It is about 660 MB, downloaded once; use Wi-Fi.
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
     Face, the Models screen shows **Update to vN**. The new model downloads alongside the old one, which you
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

Voice keyboard (0.6.0; control row 1.007): a header with the Hebrish mark and a settings gear,
one row of round, colour-coded buttons (Discard, Retake, the **mic** in the middle, Pause,
Insert last), always in place and dimmed when they don't apply, and the key row previous
keyboard · `,` · `.` · space · delete · enter.

- **Getting back to your keyboard:** tap the keyboard key or press **Back**. Long-press the
  keyboard key for the system picker. If you leave mid-take, what you said is still
  transcribed and inserted first. Under *Keyboard to return to* you can fix a target keyboard
  in case the automatic choice gets it wrong.
- **During a take:** the mic turns red with a stop square; **Pause / Resume** (gold while
  paused), **Retake** (throw it away and start again) and **Discard**.
- **Insert last transcript:** if no text field had focus when the transcript came back, it
  is kept, and this button types it in once you tap a field.

## Transcription history (since 0.8.1)

Every take is kept on the phone (text, audio length, model, transcription timings). **Dictation**
→ *Transcription history* → **Export CSV** saves it through the system file picker, so it can go
straight to Google Drive; the first columns match the desktop history export. *Keep
transcription history* turns it off and *Clear history* deletes it. Takes before 0.8.1 were not
stored.

## Floating mic (optional, since 0.3.0)

A mic button that floats over every app, so you can dictate without switching keyboards at
all: your regular keyboard stays up and the text goes straight into the field.

- **Turn it on:** home → **Floating mic** → **Turn it on: step by step**. In short:
  Accessibility settings → *Downloaded apps* → *Hebrish floating mic* → on. On Android 13+ an
  app installed from an APK is greyed out there: try once, then **App info** → ⋮ → *Allow
  restricted settings* (the ⋮ item only appears after that first try), then turn it on. The
  guide has a button for each settings page.
- **Dictate:** tap a text field, tap the mic and talk. While a take is open the mic turns red
  (it is now **Stop**) and a bar opens beside it with a timer, **Pause / Resume**, **Retake**
  (throw the take away and start again) and **Discard**. **Stop** transcribes and puts the text
  in at the cursor, with a space before it if needed. Takes can run 20 minutes (see Limits).
- **Missed the field:** if no text field has focus when the text is ready, the mic shows
  **Insert** (and ×). Tap a field, then **Insert**: the text goes in at its cursor. It is on
  the clipboard as well.
- **Where it sits:** drag the mic anywhere. With *Left edge* or *Right edge* it snaps to the
  nearer edge when you let go; with *Anywhere* it stays exactly where you drop it. The Floating
  mic screen sets the same things directly and moves the mic live: height in 0.1 % steps (plus
  ▲ ▼ nudges of 0.5 %), place across the screen (*Anywhere*), gap from the edge (0–48 dp),
  size (20–96 dp) and idle opacity (down to 1 %), each with − / + buttons for single steps.
  The icon can be the mic, the Hebrish H or the letter ע (1.000). New installs start on the
  left edge at 44 dp. *Show only while a text field is focused* hides the mic the rest of the time.
- **While you talk** (1.000): the bar opens towards the middle of the screen, by default along
  the edge as a narrow column (or across the screen). Drag it by its grip (⠿) to move it off
  what you are writing. Its size (50–100 %), background opacity, and a *clear bar* (buttons
  only, each on its own backdrop) are on the Floating mic screen.
- **How the text goes in** (2026-10-25): on Android 13+ the floating mic types the text at the
  cursor through its own input connection, like a keyboard: no clipboard, so no "pasted from
  your clipboard" notice. Where that isn't available or doesn't take, it falls back to pasting,
  then to rewriting the field, then to **Insert**, so the text lands in as many apps as possible.
- **"Pasted from your clipboard":** when the paste fallback is used (Android 12, or a field the
  input connection can't reach), Android shows this notice. Apps can't hide it; turn it off in
  Settings → Privacy → *Show clipboard access* (the Floating mic screen has a button there; 1.000).
  After updating, turn the floating mic off and on in Accessibility settings once if the notice
  keeps appearing on Android 13+ (I).
- **Long-press the idle mic** to insert the last transcript again.
- **Double-tap the idle mic** to shrink it to a small dot when it is in the way; tap the dot to
  bring it back (0.8.0).
- **Keep it running:** the guide's *Keep it running* step lets Hebrish run unrestricted on
  battery. Without it, phones such as OnePlus can stop the floating mic in the background.
- **Apps built with Jetpack Compose** (ChatGPT, for example): 0.3.0 often couldn't find the text
  field there. Since 0.4.0 the floating mic searches for the focused field more thoroughly.
  No "display over other apps" permission is needed or used.
- **Fields that refuse it** (some web pages and custom editors): each fallback above is tried
  in turn, and if all fail the text is held for **Insert** and left on the clipboard. Password fields are never touched.

It uses the same model and the same process as the voice keyboard; the two can be used side by
side.

## Model details

| | |
| --- | --- |
| Base | [`nvidia/parakeet-tdt-0.6b-v2`](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2) (v2 on purpose, not v3) |
| Stock | [`csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8`](https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8), files at the repo root |
| Code-switching | [`Hebrish/Jachnun-sherpa-onnx-int8`](https://huggingface.co/Hebrish/Jachnun-sherpa-onnx-int8), files at the root (since 2026-10-19; the main repo is gated). The app downloads whatever version is on HF `main` |
| Format | sherpa-onnx int8 (encoder, decoder, joiner, tokens), about 660 MB per model |
| Offline fallback (`ModelStore.BUNDLED`) | stock v2 at rev `1ab9323565dd`; code-switching v1.0 at rev `bb137e504b97` of the mirror (since 0.2.1). Used only when HF can't be reached on a first download |
| Runtime | [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 1.13.8, built from source (`app/src/main/cpp`), ONNX Runtime 1.28.0 from Maven Central, CPU, greedy search |

The code-switching model is trained on a single speaker's voice, so expect it to work best for that
voice. Output is punctuated and cased, numbers come out as digits, and Hebrew words are
written in Latin script (the v2 tokenizer has no Hebrew characters).

## Limits

- **Offline recognition, decoded in pieces.** The model is not a streaming one, but since
  0.4.0 a take is cut at pauses while you talk and each piece is transcribed straight away, so
  after you stop only the last few seconds remain. By default the text goes in at Stop;
  *Dictation → Type as you go* inserts each piece as soon as it is ready. Takes stop
  automatically at **20 minutes** (90 s before 0.4.0).
- The first transcription after the process starts loads the 650 MB encoder, which takes a
  few seconds. The floating mic loads it when it starts and whenever a text field gets focus;
  after that it stays in memory while Android keeps the app alive.
- arm64-v8a phones only, Android 9 (API 28) or newer.

## Build

```bash
git submodule update --init                           # sherpa-onnx and its dependencies (third_party/)
echo "sdk.dir=$HOME/Android/Sdk" > local.properties
JAVA_HOME=/path/to/jdk-21 ./gradlew assembleFdroidRelease   # compiles sherpa-onnx (NDK r26d, CMake 3.22.1)
```

Without the `RELEASE_*` env vars the release APK is unsigned (`app-fdroid-release-unsigned.apk`), as on F-Droid's build server; use `assembleFdroidDebug` for a build to install. Releases come
from `../.github/workflows/android.yml`: push an `android-vX.Y.Z` tag and it builds a signed APK and
attaches it to a GitHub release. Maintainer notes are in [`docs/maintaining.md`](docs/maintaining.md).

## Related

- Code-switching fine-tune project:
  [English-Hebrew-Codeswitching-Parakeet-Finetune](https://github.com/Hebrish-ASR/English-Hebrew-Codeswitching-Parakeet-Finetune)

## License

App code: MIT. The models carry their own licenses on Hugging Face; the base
model is NVIDIA's CC-BY-4.0.
