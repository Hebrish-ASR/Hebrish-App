# Maintaining

Written 2026-10-18, as Voice To Hebrish; updated 2026-10-19 for Parlance. (V) = verified, (I) = inferred / not yet tested on a device.

## Models and the catalogue (Parlance 0.1.0, 2026-10-19)

Parlance replaces Voice To Hebrish (app ID `com.danielrosehill.codeswitchvoice`, last 0.6.0).
The new app ID is `com.danielrosehill.parlance`, so it installs alongside and keeps none of
the old app's downloads or settings. Version numbers restarted at 0.1.0 / versionCode 1.

The models come from [`../../shared/models.json`](../../shared/models.json), shared with the
desktop app (`Catalogue.kt`):

- **Bundled:** the gradle `copyCatalogue` task copies `../shared/models.json` into
  `app/build/generated/catalogue/`, which is an assets source dir, so the APK has
  `assets/models.json` (V: present in the debug APK, 2026-10-19). Never hand-copy it.
- **Remote:** every update check (`ModelDownload.check`) first calls `Catalogue.refresh`,
  which fetches `catalogue_url` (the file on GitHub `main`). If it parses with `schema` 1 and
  lists at least one available model, it is cached in `Prefs.catalogueJson` and used from
  then on. Otherwise the current one stays. So publishing a model = add its repo to
  `models.json` with `status: "available"` and push; no APK release (I: not yet run on a device).
- A model with `status: "planned"` (tech, personal) is shown disabled as "coming soon".
- `version_label` (stock: `v2`) is the label for a repo without `version.json`.
- A schema change that old apps can't read must bump `schema`; old apps then ignore the
  remote copy and keep their cached or bundled one.

Per model (`ModelStore`, every function takes a `Catalogue.Model`, default `Catalogue.selected`):

- Folder: `filesDir/models/<id>/<version>-<sha12>/`, or `<root>/<repo name>/<version>-<sha12>/`
  in a shared folder (`ModelStore.sharedFolder`).
- Installed manifest: `Prefs.installedManifest(id)` (key `installed_manifest_<id>`), else
  `ModelStore.BUNDLED[id]`. `stock` is pinned to rev `1ab9323565dd` and `codeswitch` to v3
  rev `92679110e821`, hashes from the HF tree API (V, 2026-10-19 for stock). A model with no
  bundled manifest gets one from `checkLatest` before its first download.
- `subdir` may be empty (the stock repo has its files at the root). URLs are built with
  `ModelStore.path`, which skips empty parts, so there is no `//`.
- `pruneOld` deletes old versions of one model only. Other models' downloads stay until the
  user deletes them (**Delete other models…** → `ModelStore.delete`).
- Switching model (`MainActivity.renderPicker`) sets `Prefs.selectedModel`, unloads the
  recognizer, clears a stale download failure and checks HF for that model. `Transcriber`
  also remembers which folder it loaded and reloads if the selected model's folder differs,
  so the IME can't keep transcribing with the previous model.
- Relocation (`ModelDownload.relocate`) moves every ready model, not just the selected one.

## Model updates

The protocol and the model's quirks are shared with the desktop app: [`../../shared/update-protocol.md`](../../shared/update-protocol.md).
**Trailing silence:** the model needs ≥0.6 s of silence at the end, or it can drop the last sentence (measured on desktop). `Transcriber.transcribe` appends 1 s of zeros before `acceptWaveform` (I: compiled, not yet run on a device).

A new version of a model reaches installed apps **without a new APK**: push new files to
`main` of that model's repo, in the catalogue's `subdir`.

How the app decides (`ModelStore.checkLatest`, `ModelDownload.check`/`update`), for the
selected model only:

1. `GET https://huggingface.co/api/models/<repo>/revision/main` → `sha`.
2. `GET https://huggingface.co/api/models/<repo>/tree/<sha>[/<subdir>]` → per file `size` and
   `lfs.oid` (= SHA-256). `tokens.txt` is a plain git file with no `lfs.oid`, so only its
   size is known.
3. Optional `GET https://huggingface.co/<repo>/resolve/<sha>[/<subdir>]/version.json` →
   `{"version": "v4", "run": "r4-en30"}`. It only sets the label. Without it the label is
   the catalogue's `version_label`, else `rev <sha[:7]>`.
4. An update is offered when the four files' SHA-256 (size for `tokens.txt`) differ from the
   installed manifest's. The decision **compares weights, not revisions**: `main` moves on
   every model-card or eval commit (10 commits on 2026-10-18 alone for the code-switch repo,
   none of them weight changes).
5. **Update to vN** downloads into its own folder, pinned to the `sha` from step 1, verifies
   each file's SHA-256, then unloads the recognizer, records the new manifest and runs
   `pruneOld` for that model. Cancel or a failure leaves the old version in use, and the
   `.part` files resume on the next tap. A free-space check runs first, because for a moment
   both versions (~1.3 GB) are on disk.

Checks run when the setup screen opens, at most every 6 h (`Prefs.lastCheck`), when the
model is switched, and on **Check for update**. The IME never checks; it loads whatever is
installed for the selected model.

Verified 2026-10-19: `assembleDebug` compiles with JDK 21 and the APK contains
`assets/models.json`. Not run on a device (I).

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

`Prefs.modelRoot` is null (app storage, `filesDir/models/<id>/<version>`) or an absolute path
the user picked; each model then lives in `<root>/<repo name>/<version>`. `pruneOld` only clears
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

## hebrish.app links (2026-10-19)

`Hebrish.kt` is the one place for the hebrish.app URLs: `Hebrish.LINKS` pairs a string
resource (`hebrish_*` in `strings.xml`) with the site or a `/contact?topic=bug|word|samples|involved`
URL. `MainActivity` builds the buttons of the **Hebrish** section (`@id/hebrish_links`, last on
the setup screen) from that list, so adding or retiring a link touches only `Hebrish.kt` and
its label string. Checked with `./gradlew --offline compileDebugKotlin` (V, 2026-10-19, JDK 17
at `/usr/lib/jvm/java-17-openjdk-amd64`; daniellaptop's shell `JAVA_HOME` points at a
non-existent `/usr/lib64/jvm/java-17-openjdk`, so set it per command). Not yet seen on a device.

## Signing

The release key is **not** in the repo. GitHub Actions secrets: `RELEASE_KEYSTORE_B64`
(base64 of the .jks), `RELEASE_KEYSTORE_PASSWORD` (store and key password are the same),
`RELEASE_KEY_ALIAS` (`codeswitchvoice`: the key was carried over from Voice To Hebrish, alias
unchanged). The secrets must be set on the Parlance-Dictation repo too. Daniel's local copy is
`~/.android/keystores/codeswitch-voice-release.jks`, with its password in the `.txt` next
to it. Losing it means users must uninstall before installing a newer APK.

## Not yet verified (as of 2026-10-19)

- The update flow and the model picker on a device; the remote catalogue fetch.
- Back with gesture navigation; `switchInputMethod(id)` on OxygenOS; pause/resume on device.
- No on-device run has been recorded yet: model load time, RAM, and transcription speed
  on the Nord 3.
- The HeliBoard mic key landing on this IME.
