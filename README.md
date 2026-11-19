# Hebrish Dictation

**On-device dictation with NVIDIA Parakeet, for Android, Linux and Windows.** Made for the
English-Hebrew code-switching model; stock Parakeet is there too.

![Hebrish 1.011 on Linux: the Models tab, Sabich in use and recommended, Sabich-Parakeet-110M below it, each with speed and accuracy dots and size](docs/screenshots/desktop-model.png)

Everything runs **on your device**. The only network traffic is downloading the model you
pick (about 660 MB for the main models, once) and a periodic check for a newer version.

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

### All models: which ones are maintained

Every Hebrish model with its status, update cycle, use case and platforms (generated from [hebrish.app/models/inventory](https://hebrish.app/models/inventory)). The apps themselves offer the models marked Android or Desktop under "In the Hebrish apps".

<!-- model-inventory:begin -->
> Every model here can still be downloaded, and access requests for the older and less maintained ones are still approved. We strongly recommend the up-to-date models (marked Recommended): they are the ones still being trained, so they recognise the widest vocabulary.

| Model | Status | Use case | Updates | Platforms | In the Hebrish apps | Latest | Last release |
|---|---|---|---|---|---|---|---|
| [Sabich](https://huggingface.co/Hebrish/Sabich-Rolling) | **Recommended** · Active | Dictation (speech to text) | Rolling: retrained from the latest weights as new recordings arrive | Android, Linux, Windows, macOS | Android + Desktop | Sabich v5.1 | 2026-11-19 |
| [Shakshuka](https://huggingface.co/Hebrish/Shakshuka) | **Recommended** · Occasional updates | Streaming dictation | Retrained now and then while its accuracy is worked on | Linux, Windows | Desktop | Shakshuka v2.2 | 2026-11-17 |
| [Falafel](https://huggingface.co/Hebrish/Falafel) | **Recommended** · Active | Voice commands | Updated alongside Sabich | Android, Linux, Windows | Android + Desktop | Falafel v1.1 | 2026-11-16 |
| [Meorav](https://huggingface.co/Hebrish/Meorav) | **Recommended** · Active | Text to speech | New versions as the TTS work moves on | GPU server | No | Meorav v3.0 | 2026-11-15 |
| [Jachnun](https://huggingface.co/Hebrish/Jachnun) | Available as is · Occasional updates (use [Sabich](https://hebrish.app/models/sabich) instead) | Dictation (speech to text) | Occasional updates, no schedule | Browser, Linux, Windows, macOS | No | Jachnun v1.0 | 2026-10-19 |
| [Sabich-Canary-Qwen-2.5B](https://huggingface.co/Hebrish/Sabich-Canary-Qwen-2.5B) | Available as is · Frozen (use [Sabich](https://hebrish.app/models/sabich) instead) | Dictation (speech to text) | None planned | GPU server | No | Sabich-Canary-Qwen-2.5B v1.0 | 2026-10-21 |
| [Sabich-Parakeet-110M](https://huggingface.co/Hebrish/Sabich-Parakeet-110M) | Available as is · Frozen (use [Sabich](https://hebrish.app/models/sabich) instead) | Dictation (speech to text) | None planned | Android, Low-power / wearables | No | Sabich-Parakeet-110M v1.0 | 2026-10-21 |
| [Sabich-Qwen3-ASR-1.7B](https://huggingface.co/Hebrish/Sabich-Qwen3-ASR-1.7B) | Available as is · Proof of concept (use [Sabich](https://hebrish.app/models/sabich) instead) | Dictation (speech to text) | None: a one-off experiment | GPU server | No | Sabich-Qwen3-ASR-1.7B v1.0 | 2026-10-21 |
| [Sabich-asr4all](https://huggingface.co/Hebrish/Sabich-asr4all-S) | Available as is · Frozen (use [Sabich](https://hebrish.app/models/sabich) instead) | Dictation (speech to text) | None planned | Low-power / wearables | No | Sabich-asr4all-S and -M v1.0 | 2026-10-21 |
| [Meorav-Daniel](https://huggingface.co/Hebrish/Meorav-Daniel) | Available as is · Frozen | Text to speech | None planned | GPU server | No | Meorav-Daniel v1.0 | 2026-11-15 |
| [Meorav-Multi-Voice](https://huggingface.co/Hebrish/Meorav-Multi-Voice) | Available as is · Frozen (use [Meorav](https://hebrish.app/models/meorav) instead) | Text to speech | None planned | GPU server | No | Meorav-Multi-Voice v1.0 | 2026-11-16 |
| [Hebrew-Latin Token Classifier](https://huggingface.co/Hebrish/Hebrew-Latin-Token-Classifier) | Available as is · Frozen | Accessory (text tools) | None planned | Linux, Windows, macOS, GPU server | No | v1 | 2026-10-15 |
| [Whisper Hebrish](https://huggingface.co/danielrosehill/Whisper-Hebrish) | Legacy · Superseded (use [Sabich](https://hebrish.app/models/sabich) instead) | Dictation (speech to text) | None | GPU server | No | Version 2 | 2026-10-17 |
| [Whisper Hebrish Small ACFT](https://huggingface.co/Hebrish/Whisper-Hebrish-Small-ACFT) | Legacy · Superseded (use [Sabich](https://hebrish.app/models/sabich) instead) | Dictation (speech to text) | None | Android | No | small-en-en30-acft | 2026-10-17 |
| [Fritter](https://huggingface.co/Fritter-ASR/Fritter) | Separate project · Active | Dictation (speech to text) | Regular incremental updates | Linux, Windows, macOS, Android | No | Fritter v1.2 | 2026-11-05 |
| [Gefilte](https://huggingface.co/Hebrish/Gefilte) | Separate project · Proof of concept | Dictation (speech to text) | Early development | Linux, Windows, Low-power / wearables | No | Gefilte PoC-1 | 2026-11-17 |

Generated 2026-11-19 from [hebrish.app/models/inventory](https://hebrish.app/models/inventory) ([JSON](https://hebrish.app/data/model-inventory.json)).
<!-- model-inventory:end -->

### In the apps

Models come in **lines**, named for what they are trained on, and each line has **versions on
different base models**, from the most accurate to the fastest. Both apps show them that way
(Android 0.7.0+, desktop 0.6.0+): pick a line, then a version, with a speed and accuracy rating
(1–5, estimates, the same as [hebrish.app/models/choose](https://hebrish.app/models/choose)), the download size, the hardware it needs and a one-line "who it's for", all in plain words ("Base model: Parakeet 0.6B v2 by NVIDIA");
formats, runtimes and repo ids are under each model's **Technical details**. The
desktop app also has **Help me choose**: device, graphics card and VRAM (detected where it can
be), and whether speed or accuracy matters more, and answers with the same rules as the website's chooser. The list is `shared/catalogue.json`.

![Help me choose: an AMD GPU with 16 GB and accuracy first suggests Sabich-Qwen3-ASR-1.7B via llama.cpp, and Sabich in the app](docs/screenshots/desktop-choose.png)

| Line | Version | Base model | Status in the apps | For |
| --- | --- | --- | --- | --- |
| **Sabich** (everything: Hebrew words + tech vocabulary) | **Sabich** | Parakeet TDT 0.6B v2 | available, **recommended** | Start here: phone or any recent computer, no GPU. [Models](https://hebrish.app/models#sabich) |
| | Sabich-Qwen3-ASR-1.7B | Qwen3-ASR 1.7B | listed; not runnable in the apps yet | Most accurate. Desktop GPU: about 2.2 GB VRAM for the Q8_0 GGUF via llama.cpp, 5 GB for bf16 |
| | Sabich-Canary-Qwen-2.5B | Canary-Qwen 2.5B | listed; not runnable in the apps yet | Best on plain English, behind Qwen3-ASR on Hebrew words. Desktop GPU, about 6 GB VRAM (NeMo) |
| | Sabich-Parakeet-110M | Parakeet TDT-CTC 110M | available | Older phones, wearables: a fifth of the size (137 MB), faster, more mistakes |
| | Sabich-asr4all-M / -S | FUTO asr4all 56M / 28M | listed; not runnable in the apps yet | Tiny, for wearables; writes numbers as words |
| **Jachnun** (code-switching only) | **Jachnun** | Parakeet TDT 0.6B v2 | available | English + Hebrew vocabulary (*teudat zehut*, *arnona*, *bituach leumi*), in Latin letters. Recommended until 2026-10-21. [Models](https://hebrish.app/models#parakeet) |
| **Shakshuka** (streaming) | **Shakshuka** | Nemotron speech streaming 0.6B | desktop 0.7.0+ (streams while you talk); not on Android yet | Live text while you talk |
| **Falafel** (voice commands, added 2026-11-10) | **Falafel** | Parakeet TDT 0.6B v2 | listed; "Coming soon" until its first release is on the CDN (1.028+), then downloadable | Short spoken commands to a computer or phone, Hebrew words included. [Model card](https://huggingface.co/Hebrish/Falafel) |
| | Falafel-Parakeet-110M | Parakeet TDT-CTC 110M | as Falafel | Voice commands on a phone or laptop: a fifth of the size, faster, more mistakes |
| **Parakeet (stock)** | | Parakeet TDT 0.6B v2 | available | Standard English, without the Hebrew words. NVIDIA's release, unchanged |

Everything the apps can run today is a sherpa-onnx int8 offline transducer. A version on an
engine the app doesn't have yet is shown greyed, with where it runs instead and its model card.

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

## Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org)
(applied for 2026-11-17; Windows builds are unsigned until it is approved).

- Signed: the Windows desktop builds (the Velopack installer, `Hebrish.exe` and the portable zip's executables), built from this
  repository by GitHub Actions on GitHub-hosted runners (`.github/workflows/desktop.yml`).
- Committers and reviewers: [members of Hebrish-ASR](https://github.com/orgs/Hebrish-ASR/people).
  Approvers: [owners of Hebrish-ASR](https://github.com/orgs/Hebrish-ASR/people?query=role%3Aowner). Every release is approved by hand.
- Privacy: the app does not upload audio or transcripts and has no telemetry; it contacts `cdn.hebrish.app` only to download models
  and updates. [Privacy policy](https://hebrish.app/privacy). Full policy: [hebrish.app/code-signing](https://hebrish.app/code-signing).

## Desktop app (Linux and Windows)

- **Dictate**: press a hotkey anywhere (or Talk in the window), talk, and the text is pasted
  where your cursor is, inserted as you go every ~5 s and whenever you pause (Fast, Normal, Relaxed or a custom interval). An optional Stop and send key submits only once the last words are in. Output can also be the clipboard or the
  window's text box. The Dictate tab shows the microphone in use, a switcher, a level meter with
  a clip lamp, and a voice-detection toggle. Feedback is beeps, short spoken prompts, or off.
  Two hotkeys, any key or a foot pedal: a toggle key (tap to start, tap to stop; holding it
  is push-to-talk too, unless you turn that off) and an optional push-to-talk key. An optional
  floating overlay, like the Android floating mic, shows the take with Pause, Retake and Discard.
- **File**: drop or open an audio file. The transcript fills an editable text box piece by
  piece; save it as .txt or .md.
- **Models**: each line (Sabich, Jachnun, Shakshuka, stock Parakeet) with its versions under it,
  each with speed and accuracy dots, size, hardware, a one-line recommendation and its own
  Download, Use and Delete; **Help me choose** recommends one from your device, GPU and priority.
  Choose the folder the weights are stored in. History is optional (off by default).

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
| `android/` | Android voice keyboard (Kotlin, sherpa-onnx built from source) |
| `shared/catalogue.json` | The model catalogue (schema 2: lines and variants) both apps bundle and re-fetch since Android 0.7.0 / desktop 0.6.0; a test fails if either app's copy drifts |
| `shared/models.json` | The schema-1 catalogue, kept for older builds; a test fails if it disagrees with `catalogue.json` |
| `shared/updates-android.json` | Android's in-app What's new list (Updates screen), baked from hebrish.app's changelog by `scripts/bake_updates.py`, Android entries only (by each entry's `data-platforms`, 2026-10-31); copied into the APK as `assets/updates.json` at build time. The desktop's list (Desktop and Site entries) is `desktop/hebrish/data/updates.json`, written by the same script |
| `shared/update-protocol.md` | How models are listed, downloaded and updated, and the quirks both apps work around |
| `planning/` | Public project tracking: feature requests, backlog (with ideas for future versions), decision log |
| `CLAUDE.md` | Agent instructions, public on purpose. The maintainer's skills are private since 2026-11-09; the public [`hebrish` marketplace](https://github.com/Hebrish-ASR/Hebrish-Claude-Plugins) has `hebrish-setup` for users |

Versions are `M.NNN` (three digits after the point): 1.000 (2026-10-24) was the first, for both
apps, and every GitHub release before it was deleted that day (the `*-v0.*` tags remain).
Before tagging, add the release's entry to hebrish.app's changelog: `scripts/release-tag.sh` runs
`scripts/bake_updates.py`, which bakes the changelog up to that day into the apps' What's new list
(one per app: `shared/updates-android.json` and `desktop/hebrish/data/updates.json`, the last 20 entries for that platform, offline) and commits it with the version.
Release channels (Daniel, 2026-10-31): **beta** is the default release, the Android APK and
the Ubuntu .deb; **stable** is a beta promoted to every platform, adding the AppImage and the
Windows zip. Tag `android-vM.NNN` builds the signed APK in CI. Tag `desktop-vM.NNN` (beta)
builds the Ubuntu 26.04 .deb in CI (an `ubuntu:26.04` container), installs and self-tests it, and
attaches it to a release titled "(beta)". Promoting it to stable: `gh workflow run desktop.yml -R
Hebrish-ASR/Hebrish-App -f stable=true -f tag=desktop-vM.NNN` builds the AppImage (`ubuntu:22.04`,
self-tested in `fedora:43`) and the Windows zip from that tag, attaches both and retitles the
release "(stable)". The .deb (APT, `files.ubuntu`) follows beta; the AppImage and the zip
(`files.appimage`, `files.windows`) follow stable. Then overwrite the one stable file per platform on the Hebrish CDN
(`https://cdn.hebrish.app/apps/{android,ubuntu,linux,windows}/`: `Hebrish-latest.apk`,
`hebrish-latest-amd64.deb`, `Hebrish-latest-x86_64.AppImage` (latest.json key `appimage`),
`Hebrish-latest-windows-x64.zip`; since 2026-10-21, old versions
stay only on the GitHub releases) and rewrite `downloads/latest.json` (the `r2-upload` skill in
`voice-model-training`). hebrish.app needs no edit: its buttons link
`hebrish.app/get/<platform>`, which redirects to the file `latest.json` names. The F-Droid
repository (Hebrish-ASR/Hebrish-FDroid) builds from the GitHub releases, not the CDN; it checks
hourly, and every Android release also runs its `publish.yml` and checks the index lists the new version. Adding a model needs no release:
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
