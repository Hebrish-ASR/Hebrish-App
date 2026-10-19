# Hebrish engine (`android/core`)

The on-device dictation engine, shared as **source** by two apps:

| App | How it compiles these files |
| --- | --- |
| Hebrish voice keyboard (`android/app`, this repo) | `sourceSets["main"].java.srcDir("../core/src/main/java")` in `app/build.gradle.kts` |
| Hebrish Keyboard (`Hebrish-ASR/Hebrish-Keyboard`, HeliBoard fork) | This repo is a git submodule at `hebrish/`; its `app/build.gradle.kts` adds `../hebrish/android/core/src/main/java` the same way |

Package `app.hebrish.core`: `Catalogue`, `ModelStore`, `ModelDownload`, `ModelPrefs`, `Recorder`,
`Transcriber`. Split out of the voice keyboard on 2026-10-19.

Why a source folder and not a Gradle library module: the two apps use different Android Gradle
Plugin generations (this repo AGP 8.9 with the Kotlin plugin; HeliBoard AGP 9.1 with built-in
Kotlin, which rejects `org.jetbrains.kotlin.android`). One `build.gradle.kts` cannot serve both,
and the engine has no resources or manifest of its own, so plain sources are enough.

Rules for code here:

- No `R`, no resources, no references to either app's classes. Anything an app must supply
  (the sherpa-onnx AAR, `models.json` as an asset, `RECORD_AUDIO` and `INTERNET` permissions)
  each app's build declares itself.
- Must compile on minSdk 21 (HeliBoard's) as well as 28 (this app's).
- Changing a public signature here breaks Hebrish Keyboard's build at its next submodule bump;
  build both after changing anything.
