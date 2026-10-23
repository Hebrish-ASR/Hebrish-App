# Getting Hebrish into the main F-Droid repository

Goal: `app.hebrish.dictation` on f-droid.org. Today it is only in the project's own repository,
`https://fdroid.hebrish.app/repo` (`Hebrish-ASR/Hebrish-FDroid`). Researched 2026-10-20 from
the F-Droid docs (raw markdown in `gitlab.com/fdroid/fdroid-website`) and a sparse clone of
`gitlab.com/fdroid/fdroiddata`; merge-request dates from the GitLab API. **[C]** = confirmed in
a source, **[I]** = inferred. Nothing here has been submitted yet.

**Status 2026-10-23:** to-do step 1 is done for this app (branch `fdroid-from-source`, CI run
39987070650 green): sherpa-onnx is built from source, and the AAB holds
`libsherpa-onnx-jni.so` (3.7 MB, 1.13.8, no espeak/piper strings, 16 KB-aligned LOAD
segments, no build-id note) next to Maven's `libonnxruntime.so`. Daniel dictated with the
branch APK on his phone on 2026-10-23: works. Merged as PR #1.
Hebrish Keyboard still downloads the AAR (it already uses `ndkBuild` for HeliBoard's own
native code, and a module takes one `externalNativeBuild`, so it needs a separate approach).

## Release flow (decided 2026-10-23)

Daniel: future releases are planned "like this": one reproducible build serves both F-Droid
repositories. Per Android release:

1. `scripts/release-tag.sh android X.Y.Z --push` (also writes
   `app/fastlane/metadata/android/en-US/changelogs/<versionCode>.txt`, ≤500 characters).
2. `.github/workflows/android.yml` job `apk` builds and signs `Hebrish-X.Y.Z.apk` and makes the
   GitHub release. Job `repro` rebuilds the same commit unsigned in another path with another
   JDK 21 vendor and runs `apksigcopier compare` against it. **A red `repro` means f-droid.org
   will not publish the version**: fix it before announcing (the job prints a diffoscope report).
3. Our repository (`fdroid.hebrish.app`, Hebrish-ASR/Hebrish-FDroid) picks the GitHub release
   APK up within an hour, as before.
4. f-droid.org (once the MR is merged): its bot sees the `android-v*` tag, adds a Builds entry
   (`AutoUpdateMode: Version`), builds from source, and publishes **our signed APK** if the bytes
   match (`Binaries` + `AllowedAPKSigningKeys`). Same signature everywhere, so phones move freely
   between GitHub, the CDN, our repo and f-droid.org. Listing about 1–2 days after the tag **[I]**.

Never change the signing key, `applicationId`, the release APK name, the tag pattern or
`subdir` without updating the fdroiddata metadata in the same breath. Draft of what will be
submitted: [`fdroid/app.hebrish.dictation.yml`](fdroid/app.hebrish.dictation.yml).

Verified 2026-10-23 on branch `fdroid-main`, CI run 39992061068: `repro` green (unsigned
rebuild with Zulu 21 in a different checkout path; `apksigcopier compare` verified). fdroidserver's
`scanner.scan_source` over a fresh recursive clone: 51 problems, all in
`android/third_party/sherpa-onnx` (Flutter/Dart/Node examples without lock files, Wear OS
examples using Play Services); 0 with `scandelete: android/third_party/sherpa-onnx`, which
deletes only the flagged files (none is read by our CMake build). F-Droid's
`remove_signing_keys` (fdroidserver `common.py`) drops `signingConfigs { }` and lines matching
`^\s*signingConfig\s*[= ]\s*[^ ]*$`; our release `signingConfig` assignment is one `if` line so
that, with the block gone and no `RELEASE_*` env, the build is unsigned instead of debug-signed.

## Verdict

It can get in. There is **one hard blocker**: the prebuilt sherpa-onnx AAR. The downloaded
model (even a CC-BY-NC one), the network downloads and the accessibility service are
anti-features or nothing, not rejections. A near-identical app was accepted on 2026-10-15:
**Marmalade STT** (`app.marmalade.stt`), a voice keyboard with sherpa-onnx 1.13.8 built from
source, arm64, Parakeet models, reproducible. Copy its recipe.

## Blocker: sherpa-onnx is a prebuilt binary

- Policy **[C]** (<https://f-droid.org/docs/Inclusion_Policy/>): everything is built from
  source, except binaries from "trusted Maven repositories" (Maven Central, Google Maven, OSS
  Sonatype, OSS JFrog, JitPack.io, Clojars), which must still be FLOSS. GitHub release downloads
  are not on that list.
- Hebrish up to 0.10.0 **[C]**: `app/build.gradle.kts` task `fetchSherpaAar` downloaded
  `sherpa-onnx-1.13.8.aar` (Kotlin API + native `.so`, with onnxruntime) from GitHub releases
  into `app/libs/`. Replaced on 2026-10-23 by the Marmalade recipe below, without its patches
  (those are Marmalade features: Whisper, cancellable decodes).
- How Marmalade does it **[C]**
  ([metadata](https://gitlab.com/fdroid/fdroiddata/-/blob/master/metadata/app.marmalade.stt.yml),
  [CMakeLists](https://github.com/maxwhipw/marmalade-stt-android/blob/main/app/src/main/cpp/CMakeLists.txt),
  [MR 52088](https://gitlab.com/fdroid/fdroiddata/-/merge_requests/52088)): sherpa-onnx v1.13.8
  and its CMake FetchContent dependencies are pinned **git submodules**, built by the app's own
  CMake (`externalNativeBuild`) with `FETCHCONTENT_FULLY_DISCONNECTED`. onnxruntime comes from
  **Maven Central** (`com.microsoft.onnxruntime:onnxruntime-android`), its `.so` and headers
  extracted and passed through `SHERPA_ONNXRUNTIME_LIB_DIR` / `SHERPA_ONNXRUNTIME_INCLUDE_DIR`.
  The sherpa Kotlin API sources are copied into `com/k2fsa/sherpa/onnx`.
- Other routes seen in fdroiddata **[C]**: Anti-Vocale (`com.antivocale.app`) uses the
  `srclibs/sherpa_onnx.yml` srclib and builds the AAR in the `build:` step (that script fetches
  a prebuilt onnxruntime unless the ORT env vars are set; it was accepted anyway **[I]**).
  SherpaTTS (`org.woheller69.ttsengine`) uses JitPack `com.github.k2-fsa:sherpa-onnx`, whose
  `jitpack.yml` just re-serves the GitHub AAR. Tolerated because JitPack is allow-listed **[I]**;
  every newer sherpa app builds from source, so don't rely on it **[I]**.
- `android/core` is shared as source with Hebrish Keyboard, so the native build change lands in
  both apps **[I]**.

## Anti-features (labels, not blockers)

Source <https://f-droid.org/docs/Anti-Features/> **[C]**: "might not block it from inclusion".

| Anti-feature | Applies? |
|---|---|
| `NonFreeNet` | Expected: the model downloads from `cdn.hebrish.app` / Hugging Face. WhisperIME, SherpaTTS and Marmalade all carry it for model downloads **[C]** |
| `NonFreeAssets` | Once a CC-BY-NC model (v1.1 and later, see hebrish.app/terms) can be downloaded. Precedent **[C]**: Ramblr (`com.trevornk.ramblr`), "The optional on-device cleanup model is under a non-free license. It is downloaded only on request and requires consent." Not needed while only CC-BY-4.0 v1.0 is offered **[I]** |
| `Tracking` | Only if something phones home by default without consent. To check: `ModelStore.checkLatest` calls `huggingface.co/api/models/<repo>/revision/main` (or the CDN `manifest_url`); if `ModelDownload.updateAvailable` runs automatically, make it opt-in or expect this **[I]** |
| `NonFreeDep`, `TetheredNet` | No **[I]** (`TetheredNet` exempts a configurable server) |

Accessibility service: not mentioned in the inclusion policy or anti-features **[C]**; 16
fdroiddata apps use one (TalkBack, Voice Notify, …) **[C]**. No issue.

No country, sanctions or geography clause in either policy page **[C]** (only those two pages checked).

## Process

1. Open a **merge request to fdroiddata** ("New app: Hebrish", fill the template in
   [CONTRIBUTING.md](https://gitlab.com/fdroid/fdroiddata/-/blob/master/CONTRIBUTING.md)), not an
   RFP issue: the [RFP README](https://gitlab.com/fdroid/rfp/-/raw/master/README.md) asks authors
   to package it themselves **[C]**.
2. `metadata/app.hebrish.dictation.yml` **[C, field names]**: `Categories` (`Keyboard & IME`,
   `Speech Recognizer`), `License: MIT`, `AuthorName`, `SourceCode`, `IssueTracker`,
   `AntiFeatures`, `RepoType: git`, `Repo: https://github.com/Hebrish-ASR/Hebrish-App`, `Builds`
   (`versionName`, `versionCode`, `commit: android-vX.Y.Z`, `subdir: android/app`,
   `submodules: true`, `gradle: [yes]`, `ndk: <pinned>`, `scandelete`, `binary`),
   `AllowedAPKSigningKeys`, `AutoUpdateMode: Version`, `UpdateCheckMode: Tags ^android-v[\d.]+$`.
   Check with `fdroid lint`, `fdroid rewritemeta`, `fdroid build` (or the fdroiddata CI).
3. Monorepo: `subdir` handles it; `scandelete` anything binary under `desktop/` if the scanner
   complains **[I]**.
4. **Fastlane metadata in this repo** (strongly recommended **[C]**; added 2026-10-23 in
   `android/app/fastlane/metadata/android/en-US/`, because fdroidserver looks in the repo root
   and in `<subdir>/fastlane`, not in `android/fastlane`; no phone screenshots yet) with `short_description.txt` (<80 chars, no
   trailing dot), `full_description.txt`, `images/icon.png`, `images/phoneScreenshots/`,
   `changelogs/<versionCode>.txt` (≤500 chars; write one per release alongside
   `.github/android-release-notes.md`).
5. Timeline **[C]**: Marmalade STT 4 days (2026-10-11 → 10-15), Anti-Vocale ~10 days, Marmalade
   TTS ~1 month, Ramblr ~2.5 months (40 comments). Listed 24–48 h after merge; later version
   bumps are bot-merged.

## Signing: go reproducible

<https://f-droid.org/docs/Reproducible_Builds/> **[C]**: with `binary:` (the upstream APK URL,
e.g. the GitHub release asset) and `AllowedAPKSigningKeys` (SHA-256 of the release cert),
F-Droid publishes **our** signed APK if its own build matches byte for byte. Otherwise F-Droid
signs with its own key, and people who installed from GitHub, the CDN or fdroid.hebrish.app
cannot update from f-droid.org without uninstalling **[I]**. Switching later is hard **[C]**.

Reproducibility traps for a native app **[C]**: pin the NDK exactly; sign with `apksigner` from
build-tools 34 (35.0.0-rc1+ can produce APKs that fail verification); `--build-id=none` /
stripping differences (`doNotStrip`), `.shstrtab` changes with NDK r26+, non-deterministic
`baseline.prof`, absolute paths in native code (`-ffile-prefix-map`, as Marmalade does).
Verify locally by building twice from clean checkouts in different paths and diffing.

## To do, in order

1. ~~Replace `fetchSherpaAar` with a from-source sherpa-onnx build~~ (done for this app
   2026-10-23, see Status). Still to do in Hebrish Keyboard.
2. ~~Reproducible release APK~~ (done 2026-10-23): NDK r26d, Marmalade's settings, unsigned
   without keystore, CI job `repro` verifies every build. A Gradle lockfile was not added: the
   only dependency is ONNX Runtime at a fixed version.
3. Make any automatic model-update check opt-in (or accept `Tracking`).
4. ~~Add fastlane metadata and a changelog per `versionCode`~~ (done 2026-10-23; phone
   screenshots still missing, optional).
5. Open the fdroiddata MR with `NonFreeNet`; add `NonFreeAssets` when a CC-BY-NC model ships.
