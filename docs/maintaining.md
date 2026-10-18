# Maintaining

Written 2026-10-18. (V) = verified, (I) = inferred / not yet tested on a device.

## Model updates (0.3.0+)

A new fine-tune reaches installed apps **without a new APK**. Pushing new
`sherpa-onnx/int8/` files to `main` of
`danielrosehill/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching` is all it takes.

How the app decides (`ModelStore.checkLatest`, `ModelDownload.check`/`update`):

1. `GET https://huggingface.co/api/models/<repo>/revision/main` → `sha` (the commit `main`
   points at now).
2. `GET https://huggingface.co/api/models/<repo>/tree/<sha>/sherpa-onnx/int8` → per file
   `size` and `lfs.oid` (= SHA-256). `tokens.txt` is a plain git file with no `lfs.oid`, so
   only its size is known.
3. Optional `GET https://huggingface.co/<repo>/resolve/<sha>/sherpa-onnx/int8/version.json`
   → `{"version": "v4", "run": "r4-en30"}`. It only sets the label. Without it the label is
   `rev <sha[:7]>`. The training repo's `export_sherpa` writes it (added 2026-10-18).
4. An update is offered when the four files' SHA-256 (size for `tokens.txt`) differ from the
   installed manifest's. The decision **compares weights, not revisions**: `main` moves on
   every model-card or eval commit (10 commits on 2026-10-18 alone, none of them weight
   changes), and comparing commits would offer a pointless 660 MB download each time.
5. **Update to vN** downloads into its own folder `<version>-<sha[:12]>`, pinned to the `sha`
   from step 1 so a push mid-download can't mix versions. Each file's SHA-256 is verified.
   Only then does the app unload the recognizer, record the new manifest
   (`Prefs.installedManifest`, JSON) and run `pruneOld`, which deletes the previous model
   folder. Cancel or a failure leaves the old model in use, and the `.part` files resume on
   the next tap. A free-space check runs first, because for a moment both models (~1.3 GB)
   are on disk.

Checks run when the setup screen opens, at most every 6 h (`Prefs.lastCheck`), plus a
**Check for update** button. The IME never checks; it just loads whatever is installed.
A first **Download** fetches the newest model on HF, and falls back to the bundled manifest
when HF can't be asked.

`ModelStore.BUNDLED` is v3 (run `r3-en30`, rev `92679110e821`). Its folder name
`v3-92679110e821` is the same one 0.1.0/0.2.0 used, so upgrading the APK keeps an existing
download. Change `BUNDLED` only to make a newer model the offline default.

The v3 values were read from the HF tree API on 2026-10-18 (V). The sherpa-onnx int8 files
at that revision were exported from `r3-en30`. Commit `728e6f88d4` published them, and the
pinned `92679110e8` is the model-card commit after it. The upstream `check_sherpa` matched
PyTorch on 4/5 clips (V, from the fine-tune repo's `docs/on-device.md`).

Verified 2026-10-18: it compiles (`assembleRelease`), and the three endpoints above return
the expected shapes for the live repo, where main is `d961d25643aa` with no `version.json`
and the same weights as v3, so the app would report "up to date". Not yet run on a
device (I).

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

## Returning to the keyboard (0.4.0)

This is the part voice IMEs most often get wrong, so it has three routes and several fallbacks.

Routes, all in `VoiceImeService`:
- **Keyboard key** (bottom left): `leave()`.
- **Back**, as a key or a gesture: `onKeyDown`/`onKeyUp` catch `KEYCODE_BACK` and call
  `leave()` in place of the default (which only hides the IME and leaves you with no
  keyboard). Toggle: `Prefs.backSwitches`, on by default. (I: Back reaches an IME's
  `onKeyDown` with gesture navigation too; not yet confirmed on the Nord 3.)
- **Long-press the keyboard key**: the system picker (`showInputMethodPicker`), which can't
  fail.

`leave()` never drops audio. A take that is recording or paused is transcribed and inserted
first, and one already being transcribed finishes first (`switchWhenDone`). Discard is the
explicit way to drop a take.

`switchBack()` tries, in order:
1. `Prefs.returnIme`, the keyboard chosen in setup, via `InputMethodService.switchInputMethod(id)`
   (API 28+).
2. `switchToPreviousInputMethod()`. It returns false when the system has no history, e.g.
   when this IME was chosen from the picker or after a reboot. That failure is the usual
   reason a voice IME strands the user.
3. `Prefs.lastOtherIme`: the system default keyboard as `MainActivity.noteDefaultIme` last saw
   it (`Settings.Secure.DEFAULT_INPUT_METHOD`, read whenever setup opens). After that,
   HeliBoard (`helium314.keyboard*`), then any other enabled IME.
4. The system picker.

Every candidate is checked against `enabledInputMethodList` first, so a keyboard that was
uninstalled or disabled is skipped instead of throwing.

## Takes and insertion (0.4.0)

- While a take is open, a row shows **Pause / Restart / Discard**. Pause stops `AudioRecord`
  and frees the mic, so the privacy indicator goes off, and keeps the samples. Resume appends
  to them. The 90 s cap counts the whole take across pauses. The status line shows elapsed
  time.
- Text is inserted automatically with `commitText` at the cursor, adding a space after a
  non-space character. `commitText` returns false on a dead connection, e.g. when focus left
  the field during transcription. In that case the keyboard does **not** switch away, even if
  the user asked to leave, and **Insert last transcript** stays one tap away.
- Every transcript is saved to `Prefs.lastTranscript`. SharedPreferences means it survives
  the process being killed. The button shows whenever the IME is idle and a transcript exists.

## Signing

The release key is **not** in the repo. GitHub Actions secrets: `RELEASE_KEYSTORE_B64`
(base64 of the .jks), `RELEASE_KEYSTORE_PASSWORD` (store and key password are the same),
`RELEASE_KEY_ALIAS` (`codeswitchvoice`). Daniel's local copy is
`~/.android/keystores/codeswitch-voice-release.jks`, with its password in the `.txt` next
to it. Losing it means users must uninstall before installing a newer APK.

## Not yet verified (as of 2026-10-18)

- The update flow on a device (first real test: v4).
- Back with gesture navigation; `switchInputMethod(id)` on OxygenOS; pause/resume on device.
- No on-device run has been recorded yet: model load time, RAM, and transcription speed
  on the Nord 3.
- The HeliBoard mic key landing on this IME.
