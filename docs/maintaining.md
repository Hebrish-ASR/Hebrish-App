# Maintaining

Written 2026-10-18. (V) = verified, (I) = inferred / not yet tested on a device.

## Moving to a new model version

All model identity lives in `app/src/main/java/com/danielrosehill/codeswitchvoice/ModelStore.kt`:

- `MODEL_VERSION`: display label ("v3").
- `REVISION`: full 40-char HF commit of
  `danielrosehill/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching`. Downloads use
  `resolve/<REVISION>/sherpa-onnx/int8/<file>`, so pushes to `main` never change an
  installed app.
- `FILES`: `size` and `sha256` per file, from
  `https://huggingface.co/api/models/<repo>/tree/<REVISION>?recursive=1` (`size`,
  `lfs.oid`). `tokens.txt` is a plain git file with no `lfs.oid`, so only its size is
  checked.

The model directory is `filesDir/models/<MODEL_VERSION>-<REVISION[:12]>`.
`ModelStore.pruneOld` deletes other directories when a download starts, so an upgrade
frees the old 660 MB.

The v3 values were read from the HF tree API on 2026-10-18 (V). The sherpa-onnx int8 files
at that revision were exported from `r3-en30`. Commit `728e6f88d4` published them, and the
pinned `92679110e8` is the model-card commit after it. The upstream `check_sherpa` matched
PyTorch on 4/5 clips (V, from the fine-tune repo's `docs/on-device.md`).

## sherpa-onnx API notes (1.13.8 AAR, read with javap 2026-10-18)

- The AAR on GitHub releases (`sherpa-onnx-<ver>.aar`, 50 MB) contains the Kotlin API
  (`com.k2fsa.sherpa.onnx.*`) and JNI libs for four ABIs. It is not on Maven, which is why
  `app/build.gradle.kts` downloads it in a `fetchSherpaAar` task (gitignored).
- `OfflineRecognizer(assetManager = null, config)` loads from absolute file paths. Pass
  `assetManager` only when the model is bundled in `assets/`.
- Parakeet uses `modelType = "nemo_transducer"`. `FeatureConfig.featureDim = 80` is the
  constructor default. sherpa-onnx's NeMo transducer path takes the feature settings
  (128 mels) from the ONNX metadata (I: this is the behaviour of upstream's own Parakeet
  examples; not yet checked on a device).
- `OfflineStream.release()` frees the native stream. Call it after every decode.

## IME registration: `overridesImplicitlyEnabledSubtype`

0.1.0 installed but did not register as a usable keyboard on the Nord 3 (reported
2026-10-18). Its only subtype was `imeSubtypeMode="voice"`, `languageTag="en-US"`, with no
`overridesImplicitlyEnabledSubtype`. When an IME is enabled without explicitly chosen
subtypes, Android implicitly enables only its keyboard-mode subtypes that match the system
locale, plus any subtype flagged `overridesImplicitlyEnabledSubtype`. A voice-only IME
without the flag therefore has no enabled subtype, and the picker and HeliBoard's voice-IME
lookup skip it. 0.2.0 adds the flag, as the working `android_transcribe_app` voice IME does
(I: the cause is reasoned from AOSP's subtype rules and that comparison; not yet confirmed
on the device). If 0.2.0 still doesn't appear, run `adb shell ime list -a` to see whether
the system parsed the service at all, then try adding a second subtype with
`imeSubtypeMode="keyboard"`.

## Model location

`Prefs.modelRoot` is null (app storage, `filesDir/models/<version>`) or an absolute path the
user picked; the model then lives in
`<root>/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching/<version>`. `pruneOld` only clears
that dedicated subfolder, never the user's folder. The picker is `ACTION_OPEN_DOCUMENT_TREE`;
its tree URI is turned into a path (`primary:X` → `/storage/emulated/0/X`, `<uuid>:X` →
`/storage/<uuid>/X`) because sherpa-onnx loads by file path, so a SAF URI alone is useless
and `MANAGE_EXTERNAL_STORAGE` is required (API 30+; `WRITE_EXTERNAL_STORAGE` on 28–29).
`ModelDownload.relocate` copies (different filesystems, so no rename) and deletes the source
only when it was app storage; a shared copy is left for other apps. It unloads the
recognizer first. If all-files access is later revoked, `isReady` is false and the IME
reports the model as missing. (I: written 2026-10-18, compiled but not run on a device.)

## HeliBoard integration

HeliBoard's mic key switches to an enabled IME that has a subtype with
`imeSubtypeMode="voice"` (`res/xml/method.xml`) (I: AOSP LatinIME's shortcut-IME
behaviour, which HeliBoard inherits). After committing text the service calls
`switchToPreviousInputMethod()` (API 28+, hence `minSdk 28`) and falls back to the system
picker if that fails.

## Signing

The release key is **not** in the repo. GitHub Actions secrets: `RELEASE_KEYSTORE_B64`
(base64 of the .jks), `RELEASE_KEYSTORE_PASSWORD` (store and key password are the same),
`RELEASE_KEY_ALIAS` (`codeswitchvoice`). Daniel's local copy is
`~/.android/keystores/codeswitch-voice-release.jks`, with its password in the `.txt` next
to it. Losing it means users must uninstall before installing a newer APK.

## Not yet verified (as of 2026-10-18)

- No on-device run has been recorded yet: model load time, RAM, and transcription speed
  on the Nord 3.
- The HeliBoard mic key landing on this IME.
