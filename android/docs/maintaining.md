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
- A model with `status: "planned"` is shown disabled as "coming soon". Hebrish lists none: the
  technical and personal fine-tunes were removed from its catalogue on 2026-10-20 (they belong to
  Parlance only; `test_shared.py::test_hebrish_ships_only_stock_and_codeswitch` guards it).
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
  user deletes them (Models screen → **Delete** → `ModelStore.delete`; not offered for the model in use).
- Switching model (`ModelsActivity.use`, **Use this model**, only for a downloaded model) sets
  `Prefs.selectedModel`, unloads the recognizer, preloads the new one, clears a stale download
  failure and checks for updates. `Transcriber`
  also remembers which folder it loaded and reloads if the selected model's folder differs,
  so the IME can't keep transcribing with the previous model.
- Relocation (`ModelDownload.relocate`) moves every ready model, not just the selected one.

## Downloading any model (0.4.0, 2026-10-20)

`ModelDownload.download(ctx, model)` downloads any available model, selected or not;
`start(ctx)` is the selected-model shortcut the HeliBoard fork still calls. Only one job runs at a
time; a download asked for while one runs goes into `ModelDownload.queue` and starts when the
current job ends with `Done` (posted to the main thread). `downloadAll` queues every available
model that isn't ready. Cancel and failure both clear the queue; `failedId` names the model a
`Failed` status belongs to, so the Models screen shows it on the right card. `install` unloads the
recognizer only when the model it just installed is the selected one. `check` now also checks
every downloaded model (one manifest GET each), so updates show on every card; the
`updateAvailable` / `update` functions take the model (default: selected). (I: compiled
2026-10-20, not run on a device.)

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

Checks run when the home or Models screen opens, at most every 6 h (`Prefs.lastCheck`), when the
model is switched, and on **Check for update**. The IME never checks; it loads whatever is
installed for the selected model.

Verified 2026-10-19: `assembleDebug` compiles with JDK 21 and the APK contains
`assets/models.json`. Not run on a device (I).

## sherpa-onnx API notes (1.13.8, read with javap from the AAR 2026-10-18)

- Since 1.000 (2026-10-23) sherpa-onnx is built from source for F-Droid (`fdroid-main.md`):
  submodules in `third_party/` (sherpa-onnx at tag v1.13.8 plus every FetchContent dependency,
  pinned to the tags its `cmake/*.cmake` names), `app/src/main/cpp/CMakeLists.txt`, ONNX Runtime
  from Maven Central. The Kotlin API is five unmodified files in
  `app/src/main/java/com/k2fsa/sherpa/onnx/` (their README says how to bump). Up to 0.10.0 the
  app downloaded the GitHub release AAR (`sherpa-onnx-<ver>.aar`, 50 MB, Kotlin API + JNI libs);
  Hebrish Keyboard still does.
- Bumping sherpa-onnx: move `third_party/sherpa-onnx` to the new tag, re-pin each dependency
  submodule to the version in that tag's `cmake/<dep>.cmake` (kissfft and kaldifst are named by
  kaldi-native-fbank's and kaldi-decoder's own cmake files), recopy the Kotlin files, change
  `sherpaVersion`. A dependency left unpinned fails configure (`FETCHCONTENT_FULLY_DISCONNECTED`).
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

## Model location (retired in 0.8.0, 2026-10-21)

**Retired** (Daniel, 2026-10-21: "retire the custom model storage location feature … eke our way
towards compliance"). Google Play allows all-files access only for file managers, backup and
similar apps, and the feature needed it, so it went from both builds, not just `play`. Removed:
`MANAGE_EXTERNAL_STORAGE`, `WRITE_EXTERNAL_STORAGE`, `requestLegacyExternalStorage`, the Models
screen's location section, and setup step `files`. Models live only in `filesDir/models/<id>/<version>`.
Migration: `MainActivity.retireModelLocation` calls `ModelDownload.relocate(ctx, null)` when
`model_root` is still set. It copies what is still readable, or, when nothing is (Android revokes
all-files access once the update drops the permission, I), just switches, and the models
download again. The root support in `core` (`ModelPrefs.modelRoot`, `ModelStore.base(root)`,
`relocate`) stays, because Hebrish Keyboard compiles the same sources (it pins `core` at 0.5.0 today).
Until a user opens the app after updating, the IME and the floating mic report the model as missing.

How it worked, for the record: `Prefs.modelRoot` was null (app storage, `filesDir/models/<id>/<version>`) or an absolute path
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

Password fields (0.8.0): `VoiceImeService` treats text `PASSWORD` / `VISIBLE_PASSWORD` /
`WEB_PASSWORD` and number `PASSWORD` variations as off limits. It doesn't auto-start, the mic
shows `ime_password`, and `commit` refuses. Before 0.8.0 only the floating mic skipped password
fields (found while writing hebrish.app/privacy, 2026-10-21).

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
resource (`hebrish_*` in `strings.xml`) with the site, a `/contact?topic=word|samples|involved`
URL, or (since 0.1.1) a `mailto:feedback@hebrish.app?subject=…` link for bug reports, feature
requests and feedback. `MainActivity.open()` sends `mailto:` links as `ACTION_SENDTO` and appends
the app version, Android release and device model to the body; with no email app it shows a
toast naming the address. `MainActivity` builds the buttons of the **Hebrish** section (`@id/hebrish_links`, last on
the Help and contact screen, `ContactActivity`) from that list, so adding or retiring a link touches only `Hebrish.kt` and
its label string. Checked with `./gradlew --offline compileDebugKotlin` (V, 2026-10-19, JDK 17
at `/usr/lib/jvm/java-17-openjdk-amd64`; daniellaptop's shell `JAVA_HOME` points at a
non-existent `/usr/lib64/jvm/java-17-openjdk`, so set it per command). Not yet seen on a device.

## Floating mic (0.3.0, 2026-10-20)

`FloatingMicService` (AccessibilityService, config `res/xml/floating_mic.xml`) puts a mic over
every app in a `TYPE_ACCESSIBILITY_OVERLAY` window (no `SYSTEM_ALERT_WINDOW` needed), not
focusable, so the field keeps input focus. Built from `docs/plans/accessibility-overlay.md`.
Compiled with `assembleDebug` (V, 2026-10-20, JDK 21); **not yet run on a device** (I for
everything below that describes runtime behaviour).

- **Controls:** idle mic → tap starts a take. Open take: mic = Stop (transcribe + insert), and a
  bar with timer, Pause/Resume (`Recorder.pause`/`start`, as in the IME), Retake (cancel + new
  take into the same target field), Discard. Idle long-press = insert `Prefs.lastTranscript`.
- **Position (0.4.0):** `Prefs.bubbleSide` (`left`/`right`/`free`), `bubbleY` (0–1 of
  `displayMetrics.heightPixels` minus the mic), `bubbleX` (0–1 of width minus the mic; `free`
  only), `bubbleEdge` (dp gap, 0–48, default 6), `bubbleSize` (dp, 36–96; 0.3.0 stored one of
  44/56/68, still valid), `bubbleAlpha` (idle opacity %, 25–100), `bubbleOnlyTyping`. All keys
  start `bubble_`; the service listens to the prefs file and re-places itself on any `bubble_*`
  change, so the Floating mic screen's controls move it live, and that screen listens too, so
  a drag updates its sliders. `place()` works out the mic's left edge (`micLeft`), then anchors
  the window to whichever half of the screen the mic's centre is in (gravity LEFT or RIGHT,
  x measured from that side, minus the 4 dp window padding), so the WRAP_CONTENT bar grows
  inwards (children reversed when anchored right). A drag on an edge side saves the nearer
  side; on `free` it saves `bubbleX`.
- **Drag and look (0.5.0, Daniel, 2026-10-20: "drag it around while you're doing it",
  opacity, background opacity, colour):** every part of the bubble has a `Drag` touch listener:
  the mic, the timer, each bar button and the root (the bar's padding). `Drag(tap, hold)`:
  a move past the touch slop is a drag; buttons pass `performClick` as `tap` (and keep their
  click listener for TalkBack). On a long-press `hold()` runs; if it returns false (the mic
  during a take, or any bar part) the bubble is "picked up": a haptic buzz, then any move drags
  without the slop. Before this, only the mic dragged, and holding still past the long-press
  timeout blocked the drag. The idle mic's long-press still inserts the last transcript and
  does not drag. New prefs: `bubbleBarAlpha` (`bubble_bar_alpha`, 20–100 %, default 100: the
  bar's `GradientDrawable` alpha only, so the mic and buttons stay opaque) and `bubbleColor`
  (`bubble_color`, ARGB, one of `Prefs.BUBBLE_COLORS`: Hebrish blue `#24527A` = the old fixed
  `R.color.accent`, green `#0F6B5C`, purple, orange, slate, black; no red, which means
  recording). Compiled with `assembleDebug` (V, 2026-10-20, JDK 21: `JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64`,
  the shell's default `JAVA_HOME` points at a missing JDK 17 path); not run on a device (I).
- **Stays up (0.7.3, Daniel, 2026-10-22: "if I exit out a bit, I lose the
  overlay … I can't reposition it", R-2026-10-22-36):** with *only while typing* on, visibility
  used to follow `editableFocused` both ways, so the bubble vanished as soon as the field lost
  focus (keyboard dismissed to read what it covered, or focus lost during a drag) and could not be
  moved out of the way before tapping. Now only the rising edge counts: a field getting focus sets
  `stuck`; losing focus changes nothing, so once shown it stays up.
- **No close button (0.7.4, Daniel, 2026-10-22, testing 0.7.3 on his phone):** 0.7.3 put a × next
  to the idle mic that hid it until the next field focus. It sat where a finger lands to grab the
  mic, so every attempt to drag the mic hit × and closed it: there was no way to move it without
  closing it. The × is gone; the only way to hide the floating mic is to turn it off in settings
  (Daniel's choice over a deliberate gesture such as a pull-down to close). Move it first, then
  tap: `savePosition` stores the drag and `place()` opens the bar from there, towards the middle
  of the screen. If a close is ever wanted again, it must not be a target next to the mic.
- **Missed field (0.4.0):** when `deliver` finds no editable focused node, or the node refuses
  both SET_TEXT and PASTE, the text goes into `pending` (appended if something is already
  waiting) and onto the clipboard, and the bar shows **Insert** + ×. Insert runs the same
  `insertInto` on whatever has input focus at that moment; × drops it. The bar is shown while
  something is pending even with *only while typing* on.
- **Finding the field (0.4.0, after "doesn't work in ChatGPT", Daniel, 2026-10-20):** 0.3.0 used
  `findFocus(FOCUS_INPUT)` alone and required `isEditable` on the result, and only listened for
  `typeViewFocused` / `typeWindowStateChanged`. It worked in View-based apps and failed in
  ChatGPT. Diagnosis from the code, **not confirmed on the device**: ChatGPT is a Jetpack Compose
  app, and Compose text fields are virtual nodes under one `AndroidComposeView`. There
  `findFocus(FOCUS_INPUT)` can return the host view (not editable) or null, depending on the
  Compose version, and focus changes often arrive without a `TYPE_VIEW_FOCUSED`. The result is
  "no text field" (text held for Insert) or, with *only while typing* on, a hidden mic.
  `focusedField()` now tries findFocus, then a focused editable node under it, then the last
  editable node any event came from (still focused, or the keyboard is up), then a bounded
  search (1500 nodes) of every application window, active first. The config also listens for
  `typeWindowsChanged`, `typeViewTextSelectionChanged`, `typeViewTextChanged` and
  `typeViewClicked`, and sets `flagIncludeNotImportantViews`. *Only while typing* counts the
  keyboard's window being on screen (`AccessibilityWindowInfo.TYPE_INPUT_METHOD`) as typing.
  Ruled out: a missing "display over other apps" permission. `TYPE_ACCESSIBILITY_OVERLAY` needs
  no `SYSTEM_ALERT_WINDOW` and draws above app and keyboard windows, and the mic did show in
  ChatGPT. If it still fails there, the next suspect is Android 14's
  `accessibilityDataSensitive` (views hidden from services without `isAccessibilityTool`).
  Check with `adb shell uiautomator dump` whether the field appears at all.
  `onAccessibilityEvent` is wrapped in `runCatching`, because a service that crashes gets
  turned off by Android.
- **Battery (0.4.0):** the guide has a *Keep it running* step that asks for
  `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` (falls back to the battery optimisation list) and shows
  whether the exemption is held (`Setup.batteryExempt`). OxygenOS kills background services, and an
  accessibility service that is killed stays off until it is toggled again (I).
- **Insertion** (`deliver`): target = the field `focusedField()` finds, captured when the take starts
  (re-checked with `refresh()`), else the field found at insert time. `ACTION_SET_TEXT` replaces the
  Since 0.9.1, clipboard + `ACTION_PASTE` at the field's own cursor goes first for every piece
  (separator from `TakeDecoder.join` on the reported text before the cursor). Fallback, and first
  only to replace a placeholder: `ACTION_SET_TEXT`, which replaces the whole field, built as
  `before + [space] + text + after` from `text` and `textSelectionStart/End`, then
  `ACTION_SET_SELECTION` to the end of the insert. The old clip is not restored because a
  background service can't read the clipboard on Android 10+. Password nodes are skipped. See
  "Floating mic pastes instead of rewriting (0.9.1)".
- **No foreground service for the mic.** The system binds every enabled accessibility service
  with `BIND_FOREGROUND_SERVICE_WHILE_AWAKE | BIND_INCLUDE_CAPABILITIES`
  (AOSP `AccessibilityServiceConnection.bindLocked()`), which gives the process foreground
  importance and the while-in-use capabilities, microphone included. Source: Ramblr's
  `docs/adr/0002-background-transcription.md` (trevornk/ramblr, read 2026-10-20), which records
  from its accessibility service the same way. (I) until tried on the Nord 3.
- **No system accessibility button on purpose.** `flagRequestAccessibilityButton` makes Android
  (targetSdk 30+) classify the service as INVISIBLE_TOGGLE and tie its enabled state to its
  shortcut: turning the shortcut off turns the service off. Ramblr ships that as a separate,
  disabled-by-default service component; do the same if the button is ever wanted.
- **Restricted settings:** `FloatingMicGuideActivity` walks through it with a button per
  settings page (Accessibility settings, App info). On Android 13+ the ⋮ → *Allow restricted
  settings* item only appears after the user has tried the switch once, so the guide says to
  try first. Daniel's own setup on the Nord 3 (2026-10-20): allow restricted settings, then
  Accessibility → Downloaded apps → Hebrish floating mic.
- Ramblr (GPL-3.0) was read for design only; no code was copied (this app is MIT).

## Sound, microphone and buttons (0.6.0, 2026-10-20)

Screen `ControlsActivity`. Compiled (V, 2026-10-20); not run on a device (I below).

- **Feedback** (`Feedback.kt`): `Prefs.beeps` (default off), `Prefs.vibrate` (default on). Tones
  are synthesised into an `AudioTrack` with `USAGE_ASSISTANCE_SONIFICATION` at 35% amplitude and
  4 ms fades (no sound files). Cues: START 660→990 Hz, STOP 990→660, RESTART 990·gap·990, DISCARD
  330 Hz. Played by the floating mic, the IME and the Try screen.
- **Retake flash:** a retake turns the floating mic's bar `R.color.bubble_retake` (#B26A00) and
  shows "↺ New take" for `FLASH_MS` = 1000 ms; the IME flashes its status line the same way.
  Daniel asked for it so a retake is obvious with beeps off. While recording, the mic background
  pulses (alpha 255↔120, 700 ms).
- **Microphone** (`Mic.kt`): `Prefs.micChoice` = `Mic.AUTO` or a key `"<type>:<productName>"`
  (device ids change on reconnect, so they are not stored). Auto order: Bluetooth (SCO, or BLE
  headset type 26), then wired/USB headset, then the phone mic. Bluetooth is routed with
  `AudioManager.setCommunicationDevice` on API 31+, `startBluetoothSco` below; `Mic.release`
  undoes it after every take. `Recorder.preferredDevice` (engine, additive) calls
  `AudioRecord.setPreferredDevice`; `Recorder.routedDevice` reports what Android actually used,
  and that label ("Bluetooth: X") is shown next to the timer. Needs `MODIFY_AUDIO_SETTINGS`.
  Since 0.7.2 the floating mic shows `Mic.shortLabel` in its own chip instead (see below); the
  keyboard and Try keep `Mic.label`.
- **External control** (`Remote.kt`): broadcast intents and learned keys; reference for users in
  `docs/external-control.md`.

## Setup checklist, side menu, About, model cards, keyboard layout (0.6.0, 2026-10-20)

Asked for by Daniel on 2026-10-20 after using 0.5.0. Compiled with `assembleDebug` (V, 2026-10-20,
JDK 21); **not run on a device** (I for runtime behaviour below).

- **Setup checklist** (`SetupActivity`, reached from a card at the top of home and from the side
  menu). Steps and ids, the same as hebrish.app/setup's `#step-<id>` anchors (keep both in step;
  never rename an id): `mic` (prompt; after a refusal the prompt no longer appears, so the button
  opens App info: `Prefs.micAsked`, key `mic_asked`), `model` (Models screen), `keyboard`
  (`ACTION_INPUT_METHOD_SETTINGS`), `floating` (the guide), `battery`
  (`ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`), `unused` (API 30+:
  `Intent.ACTION_AUTO_REVOKE_PERMISSIONS` with `package:` opens App info's "Pause app activity if
  unused" / "Remove permissions if app is unused"; done when `PackageManager.isAutoRevokeWhitelisted`),
  `files` (API 30+: `ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION`; done when
  `Environment.isExternalStorageManager`). `Checklist.progress` counts the required ones for home's
  "3 of 5": mic, model, keyboard **or** floating mic, battery, unused (API 30+). `floating` and
  `files` are optional. The website's step 1, Install, has no in-app counterpart (the app is installed).
- **Side menu** (`Page.addDrawer`, home only; ☰ replaces Up there): every screen, Explore the
  lexicon and Contribute (hebrish.app `/lexicon`, `/support`), Help and contact, About; footer
  `Page.versionSummary()` ("Hebrish 0.6.0 · Jachnun v1.0"). Hand-built (scrim + panel in a
  FrameLayout, slide animation, Back closes it) because the app has no androidx dependency; adding
  DrawerLayout would mean androidx and an AppCompat theme for one widget.
- **About** (`AboutActivity`): what Hebrish is, the lexicon, contribute (samples, word, support),
  website / source / terms, version. URLs in `Hebrish.kt`.
- **Version at the bottom of home** (`versionSummary()`), with the detailed `version_line`
  (HF revision, for bug reports) under it.
- **Models as cards** (`ModelsActivity.card`): mark (`res/drawable-nodpi/model_jachnun.png` and
  `model_sabich.png`, rendered at 192 px with inkscape from `Hebrish-Mgmt/brand/logo/{jachnun,sabich}.svg`;
  stock has `drawable/model_stock.xml`, a slate disc with the mic), name, the catalogue `summary` as the
  one-line description, a Recommended / In use badge.
- **Catalogue: Jachnun recommended and first** (`shared/models.json`, Daniel: "the default one
  should be English Hebrew code switching, because that's what's unique about this app"). Names are
  now `Jachnun`, `Sabich`, `Parakeet (stock)`; summaries are plain ("English + Hebrew vocabulary: …",
  "Hebrew vocabulary + tech vocabulary: …"); order codeswitch, sabich, stock. New key
  `recommended: "codeswitch"`. **`default` stays `stock` on purpose:** builds up to Android 0.5.0
  and desktop 0.2.2 fetch this file and fall back to `default` when the user never picked a model;
  changing it would switch those users to a model they have not downloaded and break their keyboard.
  `Catalogue.selected` (0.6.0) with no pick: a model already on the phone (recommended first, then
  `default`), else the recommended one; home then pins whatever is ready into `ModelPrefs.selectedModel`
  so a later catalogue change can't move it. The desktop app still reads `default` (unchanged).
- **Model location:** the default is now shown too, with its path (`filesDir/models`). **Back to the
  default** (was "Use app storage") asks first, then `ModelDownload.relocate(null)` copies every ready
  model back into app storage; the shared copies stay for other apps (unchanged behaviour).
- **Voice keyboard layout** (`res/layout/ime_view.xml`): header row with the Hebrish mark
  (`drawable/ic_hebrish.xml`, the mark's H on the green square) and name, the status line, and a gear
  that opens the app; the mic directly under it, always at the top; level bar, take controls and
  Insert last below; key row keyboard · `,` · `.` · space · delete · enter. `,` and `.` drop a space
  just before the cursor first (`VoiceImeService.punctuate`), so they attach to the last word.
- **Retake flash, stronger:** besides the amber bar / status line, the mic itself turns amber for
  `FLASH_MS` and its icon spins back once (−360°, 500 ms). Floating mic: `render()` keeps the mic
  amber while `flashing()`; IME: `backgroundTintList` on the mic.

## Placeholder text (0.6.0, 2026-10-20)

Reported by Daniel: in WhatsApp the floating mic left "Message" in the field and dictation landed
after it. `insertInto` already treated `isShowingHintText` as empty, so WhatsApp evidently does not
set it (I: inferred from the report). `FloatingMicService.isPlaceholder` now also treats the text as
the placeholder when it equals `node.hintText`, and, when `Prefs.clearPlaceholder` is on (key
`clear_placeholder`, **default on**, switch on the floating mic screen), when the text is at most
`PLACEHOLDER_MAX` = 40 chars, one line, and has no real cursor (selection −1 or 0..0). The risk,
accepted by Daniel: a real one-word draft with the cursor at its start gets replaced; the switch
turns that off. It never applies after the current take has already typed text, so a take's own
segments are not wiped. Replacement is logged (`HebrishFloatingMic`, "Replaced placeholder text").
Not yet tried in WhatsApp.

## Inference speed (0.4.0, 2026-10-20)

What makes the wait after Stop short, in order of effect (I: none of it timed on a device yet;
measure with Try it, whose status line reports the seconds from Stop to text):

1. **Decoding during the take.** `Recorder(onSegment = …)` cuts the take at pauses while it is
   recorded and hands each segment to a `TakeDecoder`, which decodes it on one worker thread.
   At Stop only the audio since the last cut is decoded. Cut rules (`Recorder.Segmenting`): no
   cut before 8 s of audio; then a cut once 0.6 s of silence has passed (the silence stays at the
   end of the segment, which the model needs); a hard cut at 28 s at the quietest 100 ms chunk of
   the last 4 s. "Silence" is a chunk's RMS under max(0.004, 3 × a slowly tracked noise floor).
   Short takes (< 8 s) are one segment, exactly as before.
2. **No 90 s cap.** Each decode is at most ~28 s, so the full-attention memory growth that set
   the 90 s cap no longer applies; segmented takes stop at `MAX_SEGMENTED_SECONDS` (20 min), a
   battery guard for a forgotten mic. Audio already decoded is dropped, so memory stays flat.
   `MAX_SECONDS` (90) still applies to a `Recorder` without `onSegment` (the HeliBoard fork).
3. **Silence trim.** `Transcriber.trim` drops audio before the first and after the last speech
   (20 ms frames above noise + 10 % of the take's loud level), keeping 0.35 s each side, then
   0.8 s of zeros is appended (was a flat 1 s on untrimmed audio). Audio with no clear speech is
   decoded whole. The encoder's cost grows with input length, so this saves the 1–2 s of
   reach-for-the-button silence most takes have.
4. **Warm-up.** `Transcriber.load` decodes 0.5 s of zeros right after creating the recognizer,
   so ONNX Runtime's first-run allocations happen during the preload, not on the first take.
5. **Preload earlier.** The floating mic loads the model when the service connects and on any
   editable field getting focus (`Transcriber.preload`, a no-op when loaded). The service's
   process has foreground importance, so the model normally stays resident (~0.7 GB RAM) while
   the floating mic is on.

Text joins: up to 0.8.1 segment texts were joined with a space, and a mid-sentence pause could
produce an extra full stop and capital. Since 0.8.2 each segment is decoded with the end of the
one before it as context and a closing full stop is held back: see "Context at the seams (0.8.2)".
*Type as you go*
(`Prefs.typeAsYouGo`) inserts each segment when decoded (keyboard: `commitText`; floating mic:
`deliver` into the take's field), and Discard then drops only what isn't in yet.

Considered and not done: NNAPI (`provider = "nnapi"`; ONNX Runtime's Android build has the NNAPI EP)
is unlikely to help the dynamically quantised int8 graph (MatMulInteger / DynamicQuantizeLinear
are poorly supported by NNAPI and would fall back to CPU with copy overhead); untested. More
than 4 threads: the Nord 3's Dimensity 9000 has 4 big cores, and the little cores slow a
parallel op down. A true streaming model would show text while you speak; the Nemotron
streaming fine-tune (no name yet) is the candidate.

## Capture and decode robustness (0.7.1, 2026-10-21)

From a review of speed and reliability of inference (code review, compiled; I: not run on a device).

- `Recorder.start` checks `AudioRecord.state` and only sets `running` after `startRecording()`
  succeeded. Up to 0.7.0 a failed start (mic held by another app, `STATE_UNINITIALIZED`) left
  `running = true`, so the next Resume returned without a capture thread and the take silently
  stopped growing.
- A negative `read()` (`ERROR_DEAD_OBJECT`: Bluetooth headset off, audio server restart) ends the
  take through `onLimit`, so what was heard is decoded. Up to 0.7.0 the capture thread spun on
  `read()` at full CPU until Stop.
- `Transcriber.transcribe` holds the recognizer lock for the decode. `load` of another model
  (e.g. `preload` on field focus after the selection changed) and `unload` call `release()` on
  the native recognizer under that lock; a decode outside it could use freed native memory.
- Not changed, for a device test first: desktop skips takes with no speech (`engine.has_speech`,
  stray "Yeah." from silence) and stretches 0.12–0.6 s pauses (sentences dropped after short
  gaps). Android does neither; its `trim` decodes a speechless take whole. Both thresholds were
  measured on a desktop mic, and Android's `VOICE_RECOGNITION` source levels are unmeasured.

## App screens (0.4.0, 2026-10-20)

The single setup screen (`activity_main.xml`, removed) became a home screen plus one screen
per area, all `Page` subclasses built in code (`Page.kt`: headings, text, buttons, switches,
sliders, nav rows, the `mailto:`-aware `open`): `MainActivity` (home: status, Try it, mic
grant, links to the rest), `ModelsActivity`, `KeyboardActivity`, `FloatingMicActivity`,
`FloatingMicGuideActivity`, `DictationActivity`, `InstallActivity` (F-Droid repository, values
in `Hebrish.kt`: `FDROID_REPO`, `FDROID_FINGERPRINT`, same as hebrish.app/download#fdroid;
**Add the Hebrish repository** opens `fdroidrepos://…?fingerprint=…`, which F-Droid clients
register, and falls back to the https link) and `ContactActivity`. Setup checks shared by
screens are in `Setup` (MainActivity.kt). Every screen but home has `parentActivityName`
`.MainActivity` and an Up arrow. Prefs keys did not change, so 0.3.0 settings carry over.

## Version and tag (2026-10-21; M.NNN since 2026-10-24)

Since 2026-10-24 versions are `M.NNN`: Android and desktop both restarted at **1.000** (Daniel:
"we'll use three decimal places of version releases, so v1.000 is this"), then 1.001, 1.002, ...;
`release-tag.sh` refuses anything else. 0.11.0 and 0.11.1 were tagged that day, cancelled in CI
before anything was published, and the tags deleted; their work shipped as 1.000 (versionCode 24).
All earlier GitHub releases (Android 0.1.0-0.10.0, desktop 0.1.0-0.8.0) were deleted the same day;
their `android-v0.*` / `desktop-v0.*` tags were kept. D-2026-10-24-01.

Release with `scripts/release-tag.sh android <ver> --push` (repo root): it sets `versionName`
to `<ver>` and `versionCode` + 1 in `app/build.gradle.kts`, commits only that file and
`.github/android-release-notes.md` (which must start with `**<ver>`), and pushes the annotated
tag `android-v<ver>`. The tag is the source of truth; `android.yml`'s first step, "Tag matches
version", fails a tag whose name differs from `versionName`. Don't tag by hand.

## Signing

The release key is **not** in the repo. GitHub Actions secrets: `RELEASE_KEYSTORE_B64`
(base64 of the .jks), `RELEASE_KEYSTORE_PASSWORD` (store and key password are the same),
`RELEASE_KEY_ALIAS` (`codeswitchvoice`: the key was carried over from Voice To Hebrish, alias
unchanged). The secrets must be set on the Hebrish-App repo too. Daniel's local copy is
`~/.android/keystores/codeswitch-voice-release.jks`, with its password in the `.txt` next
to it. Losing it means users must uninstall before installing a newer APK.

## Models by line, catalogue v2 (0.7.0, 2026-10-21)

The Models screen lists **lines** (Sabich, Jachnun, Shakshuka, stock), each with its
**variants** under it (Daniel, 2026-10-21: "you choose Sabich, and under Sabich we show the
versions available … with a short recommendation for each … a speed–accuracy gradient").

- `Catalogue.kt` reads `shared/catalogue.json` (schema 2; asset `catalogue.json`, pref
  `catalogue_v2`, fetched from `catalogue_v2_url`). Protocol: `../../shared/update-protocol.md`,
  "Catalogue v2". `Data.models` holds only variants this build can run
  (`SUPPORTED_ENGINES = setOf("sherpa_offline_transducer")`, `PLATFORM = "android"`), planned
  included, so `ModelDownload` and `ModelStore` are unchanged; `Data.lines` holds all of them.
- `ModelsActivity`: `lineHeader` (mark, name, summary, "About <line>" link), then `card` per
  variant: name, badge, base model, the recommendation sentence, `tiers()` (Speed ●●●○○ /
  Accuracy ●●●●○, "(estimates)", `Html.fromHtml`), size and hardware, state and buttons. A variant
  this build can't run is drawn at 60% alpha with "Not in this app yet. Runs on: …" and a "Model
  card" link, and no buttons. Expected size before download: manifest, else `download_mb`.
- No "Help me choose" dialog on Android yet (the desktop has one); the recommendation sentences
  and tiers carry it here.
- `Transcriber` passes the variant's `featureDim` (catalogue `feature_dim`; after 0.7.0, which
  passed 80 for every model and relied on sherpa-onnx reading the real value from the encoder
  metadata, verified on desktop 2026-10-21). Sabich-Parakeet-110M (80 mels) became downloadable
  on 2026-10-21 by a catalogue change, no APK needed.
- Compiled, not run on a device.

## Floating mic bar: button order, source chip (0.7.2, 2026-10-21)

Daniel, 2026-10-21: a long Bluetooth name ("Bluetooth: <product name>" after the timer) stretched
the bar and pushed Retake along; "just say bt and then truncated name and for the phone just call
it internal"; Retake should have a different background, Retake and exit "should always be easy to
click"; tapping the name should toggle Bluetooth / internal. Then: "pause and restart ... should be
to the left and then the timer can be to the right".

- Bar order (`FloatingMicService.addBubble`, `takeControls`): Pause, Retake, Discard, timer, source
  chip, left to right, **whichever edge the mic is on**. `place()` no longer mirrors the bar for a
  right-parked mic; only the mic moves to the end nearest its edge (so with the mic on the right,
  the timer sits next to the mic).
- Retake has a filled `bubble_retake` circle (the retake-flash amber), Discard a `bubble_discard`
  (#7A2E2E) circle, 2 dp margins between bar items.
- Source chip: `Mic.shortLabel` = "BT <name>" (name cut to 10 chars with "…"), "Internal",
  "Wired", "USB <name>"; the TextView is also capped at `SOURCE_MAX_DP` = 110 dp with end
  ellipsis. The timer no longer carries the mic name.
- Tap the chip → `switchMic()` → `Mic.toggle` (decided from the chosen mic since 1.008, see "One-tap
  mic source"): from the phone mic to `Mic.AUTO` (Bluetooth first;
  refuses with a toast if no Bluetooth or headset mic is connected), from anything else to the
  built-in mic's key. The choice is **saved in `Prefs.micChoice`**, so it holds for later takes
  and the Controls screen shows it (decision made without asking: a take-only override would
  silently revert). Mid-take, the recorder pauses, `Mic.release` + `Mic.prepare` re-route, and
  `Recorder.start()` resumes into the same take (it re-reads `preferredDevice` on each start);
  paused, the switch applies on Resume.
- Compiled, not run on a device.

## Build channels: `fdroid` and `play` flavors, targetSdk 36 (unreleased, 2026-10-21)

For Google Play (plan: Hebrish-ASR/Hebrish-App-Planning `google-play.md`). One flavor dimension,
`channel`, in `app/build.gradle.kts`:

- **`fdroid`**: the build every channel used before: GitHub release APK, CDN, fdroid.hebrish.app.
  CI: `assembleFdroidRelease` → `apk/fdroid/release/app-fdroid-release.apk`, renamed to
  `Hebrish-X.Y.Z.apk` as before (Hebrish-FDroid's `fetch_apks.sh` matches the asset name, unchanged).
- **`play`**: the Google Play AAB. CI: `bundlePlayRelease` → workflow artifact `play-aab`
  (`Hebrish-X.Y.Z-play.aab`), not attached to the GitHub release. It is signed with the upload key from
  secrets `PLAY_UPLOAD_KEYSTORE_B64` / `PLAY_UPLOAD_KEYSTORE_PASSWORD` / `PLAY_UPLOAD_KEY_ALIAS`, or
  with the release key when those don't exist. Play App Signing accepts the app signing key as the upload key.
- Same `applicationId`, `versionCode`, `versionName` and app signing key in both, so a phone can move
  between channels without reinstalling (plan §4).

What `play` drops, and why (Play policy, plan §5 to §7):

| Removed in `play` | Where | UI effect ([Channel]) |
| --- | --- | --- |
| `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` | `src/play/AndroidManifest.xml` (`tools:node="remove"`) | Battery buttons open `ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS` (the list), label and text from `src/play/res/values/strings.xml` |
| `flagRequestFilterKeyEvents`, `canRequestFilterKeyEvents` | `src/play/res/xml/floating_mic.xml` (keep its other attributes identical to main) | Controls → no Learn/Clear per action; intents only |
| Install screen (F-Droid repo) | code only | Hidden from home and the side menu (Play doesn't allow pointing users at another store) |

All-files access was first dropped from `play` only, then retired from both builds the same day
("Model location"). Verified 2026-10-21 by building both flavors (JDK 21) and dumping them with
`aapt2`: `play` has only `INTERNET`, `MODIFY_AUDIO_SETTINGS`, `RECORD_AUDIO`, `VIBRATE`, and
`accessibilityFlags=0x42` (no key filter). `fdroid` has those plus `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`,
and `0x62`. `bundlePlayRelease` builds a 12.8 MB AAB.

**Floating mic disclosure** (both flavors): `FloatingMicConsentActivity`. Play requires an in-app
disclosure plus an explicit accept before the user turns on an accessibility service that isn't an
accessibility tool, and `android:description` doesn't count. Every button that opens Accessibility
settings for the mic calls `FloatingMicConsentActivity.openSettings`. The disclosure shows until it is
accepted (pref `a11y_consent`), and No thanks just closes it. The key-press paragraph (`consent_keys`)
has a play override. Don't set `isAccessibilityTool`: Hebrish's main audience isn't disabled users,
and claiming it invites a misrepresentation rejection.

**targetSdk 36** (Play has required it for new apps and updates since 2026-08-31). Changes made:
the side menu's Back. Targeting 36, Android 13+ no longer calls `onBackPressed` (predictive back),
so `Page` registers an `OnBackInvokedCallback` while the menu is open. Not changed: edge-to-edge was
already enforced at 35 and no screen opts out. The IME's `KEYCODE_BACK` handling relies on
`InputMethodService` turning predictive back into key events (I: AOSP has this compat path since
13, not verified on a device).

## Build provenance and /verify (unreleased, 2026-10-21)

`android.yml` and `desktop.yml` run `actions/attest-build-provenance@v2` on the APK, the Play AAB
and the Windows zip. That's a Sigstore-signed statement that the file was built by this workflow
from that commit, stored on GitHub (free for public repos). Anyone can check a file with
`gh attestation verify <file> -R Hebrish-ASR/Hebrish-App`. The .deb is built locally, so it has none.
The model files come from ASR-Training, not this repo's CI, and have none either.
hebrish.app/verify lists every downloadable file with its SHA-256 and VirusTotal result (website repo
`scripts/virustotal.py` → `data/verify.json`). About links to it and to /privacy. Not yet run: the first
attested build is the next tag.

## ALL CAPS, and the 0.7.5 polish pass (2026-10-22)

**ALL CAPS** (Daniel, 2026-10-22, R-2026-10-22-40, B-34: "just for fun"): `core`
`OutputStyle` (pref `all_caps` in the shared `prefs` file), a switch on the Dictation screen.
`TakeDecoder` reads it once per take and upper-cases every segment and the tail it hands over,
so the keyboard, the floating mic and Try it all get it without changes of their own; the stored
last transcript ("Insert last") is in capitals too. `uppercase()` is locale-independent (no
Turkish dotted İ). Desktop has the same setting (`desktop/docs/maintaining.md`, "ALL CAPS").

**Polish pass** (R-2026-10-22-41), from a read-only review; nothing here was tried on a device:
- Try it: a microphone error (busy mic, a call) shows the error instead of crashing the screen.
- Every Grant button (Setup, the keyboard page, the floating mic guide) uses `Setup.askMic`,
  which opens App info once the permission was refused for good; before, only Setup did.
- Floating mic: with type as you go and no field focused, the "held" toast shows once per take,
  not once per segment.
- Strings: Setup recommends Sabich (was Jachnun); the keyboard's Restart is Retake like
  everywhere else; the mic chip says Phone (was Internal); terms summary matches the terms page;
  the controls consent names the real screen; smaller wording fixes.
- TalkBack no longer reads "Hebrish" twice in the keyboard bar; Try's example padding is in dp;
  the Models green comes from `R.color.hebrish_green`.
- Left for later: Setup's keyboard step stays unticked for floating-mic-only users; the two near
  identical version lines on the home screen; Hebrew words in Try's example sentences (need the
  canonical romanizations); dead code (`ModelDownload.start`, `Data.versionFile`); comments that
  say "0.8.0" for things that shipped in 0.7.3.

## Floating mic keeps line breaks before the insert (0.7.6, 2026-10-23)

Daniel, 2026-10-23: a blank line typed before a take was gone when the transcript arrived, as if
a backspace had been sent. Cause (I, from the code; no device on the laptop): `insertInto`
rewrites the whole field with `ACTION_SET_TEXT`, built from the text the app *reports*. Some apps
report the text without its trailing line breaks while the cursor index still counts them; the
cursor was then clamped to the end of the shorter text and the rewrite dropped the breaks (and
added a space). Rule now: **a cursor past the end of the reported text means the reported text is
incomplete, so the overlay pastes at the field's own cursor instead of rewriting** (clipboard is
overwritten, as in the existing paste fallback). If the paste is refused it rewrites with the
missing characters restored as line breaks. Not covered: an app that trims the text *and* reports
no cursor (-1); that still appends at the end with a space. Investigation:
`docs/debug-log/2026-10-23-overlay-eats-line-break.md`.

## Screens in the Hebrish brand (0.10.0, 2026-10-23)

Daniel, 2026-10-23: "a lot of UI polish ... not for the recording itself, but for the menu ...
make it look a little bit more professional and slick, and the Hebrish logo from the website also
doesn't come through". What changed, all in the app's own screens (the keyboard and the floating
mic keep their colours):

- **Logo (V, emulator):** `res/drawable/ic_hebrish.xml` had `pathData=` without the `android:`
  prefix on the H, so the mark drew as a plain green square in the side menu, About and the
  keyboard header since 0.6.0. The launcher icon (`ic_launcher_fg`) was always right.
- **Theme:** `AppTheme` is `Theme.Material.Light` / `Theme.Material` (values-night) with the brand
  tokens in `values/brand_colors.xml` and `values-night/brand_colors.xml`, copied from
  `Hebrish-Mgmt/brand/tokens.json` (change the standard there first). Paper background, flat bar
  in the page colour, green accent. Up to 0.9.x it was `Theme.DeviceDefault.DayNight` with the
  blue `@color/accent`; that colour stays because it is the floating mic's first colour choice
  (`Prefs.BUBBLE_COLORS`).
- **Buttons:** the theme's `AppButton` (soft green pill, no capitals) for every `Button` in the
  screens; `Page.primary()` makes the filled one (Try it on home).
- **Type:** headings and the name in Fraunces (`Page.display()`, `assets/fonts/Fraunces.ttf`:
  the brand's variable font subset to Latin with fonttools `pyftsubset`, 182 KB, OFL). Body text
  stays the system sans.
- **Home:** `Page.brandHeader()` (mark, name, the brand tagline) instead of a bar title; the rows
  are grouped in cards (`Page.group()`, `nav(..., parent)`) with a chevron. The side menu has the
  same header on the brand band. About uses the header too.
- Wording: About no longer says "not-for-profit" (brand rule, 2026-10-22); the Setup
  "(optional)" label kept its space (`\u0020`: aapt trims leading spaces).

Checked on an API 34 emulator in light and dark (screenshots of home, menu, Setup, Models,
Dictation, About; no crash) (V). Not on a phone (I). How to run the emulator: the
`review-android-app` skill, section "Emulator".

## Floating mic pastes instead of rewriting (0.9.1, 2026-10-23)

Daniel, 2026-10-23, on 0.9.0: the field "jumps around" when the text goes in, and the line break
before it is still deleted. Both came from `ACTION_SET_TEXT` (I, from the code): a whole-field
rewrite resets the editor's scroll, and it is built from the text the app reports, which can lack
a trailing break even when the cursor doesn't show it (the 0.7.6 rule only caught a cursor past
the text). **Rule now: the overlay inserts with clipboard + `ACTION_PASTE` at the field's own
cursor; `ACTION_SET_TEXT` is the fallback when paste is refused, and goes first only to replace a
placeholder.** Cost: the transcript is left on the clipboard after every take. Investigation:
`docs/debug-log/2026-10-23-overlay-paste-jumps.md`.

## Floating mic: double-tap to minimise (0.8.0, 2026-10-23)

Daniel, 2026-10-23: the overlay should stay on all the time, but sometimes it is in the way of an
email being written; dragging it off-screen loses it, and a snooze/timer means it is gone when
wanted. Asked for a gesture that makes it "simmer down" into an unobtrusive state and a gesture to
bring it back.

- **Double-tap the idle mic** → it shrinks to a dot, `bubbleSize / Prefs.MINI_DIVISOR` (3), at
  least `Prefs.MINI_MIN` (16 dp), at the same spot, idle opacity, haptic tick. **Tap the dot**
  (single or double) → full size again. Taps for one double-tap timeout after restoring are
  ignored, so the second tap of a double-tap doesn't queue a take. Long-press and drag work on the
  dot as on the mic.
- Double-tap rather than long-press: long-press on the idle mic already re-inserts the last
  transcript (0.3.0), and a × was rejected in 0.7.4 because it was hit when grabbing the mic.
- State: `Prefs.bubbleMinimised` (`bubble_minimised`, kept across restarts; the `bubble_` prefix
  makes the service re-place itself). Not a setting on any screen. `mini()` is minimised **and**
  idle **and** no held transcript: a take from a remote/key, or a held transcript, shows the full
  mic and bar, then the dot comes back. `render()` calls `place()` when `mini()` changes
  (`placedMini`); `place()`/`savePosition()` use `micSize()`, the dot's diameter when minimised.
- **Trade-off (accepted by asking for a tap pattern):** a single tap on the idle, full-size mic now
  waits `ViewConfiguration.getDoubleTapTimeout()` (300 ms default) before it starts a take, to tell
  it from a double-tap (`onMicTap`, `singleTap`). Stop during a take, Insert, and remote/key
  actions are immediate. If the start delay is noticed, the alternative is to minimise on a
  different gesture (e.g. a swipe towards the edge).
- Compiled, not run on a device (I). To verify: double-tap speed on a phone, the dot's position on
  each edge and with "free", y drift between dot and full size (the saved height is a fraction of
  `screen − size`, so it shifts by up to ~two thirds of the size), dragging the dot.

## Transcription history and CSV export (0.8.1, 2026-10-23)

Daniel, 2026-10-23: "Can we also have the ability to export transcription history on Android so
that I can Export a CSV to Google Drive, and we can then also see how the Android inference is
doing as well."

Up to 0.8.0 Android kept no history: only `Prefs.lastTranscript` (one string, for Insert last).
0.8.1 adds the storage half of backlog B-19 plus the export; the History screen (list, search,
word counts, correct, delete one) is still to do. **Rows start with 0.8.1**: earlier takes were
never stored and cannot be exported.

- **Store:** `History.kt`, framework SQLite (`SQLiteOpenHelper`, no androidx), app-private
  `databases/history.db`, table `dictations` with the desktop's column names (`desktop/hebrish/history.py`,
  schema 2): `uid`, `at` (unix s), `text`, `words`, `seconds`, `model` (`<catalogue id> <version label>`,
  e.g. `sabich v2.0`), `source` (`keyboard` | `floating` | `try`), `original`, `model_rev`
  (manifest revision of the installed weights), `decode` (JSON). `original` is always NULL:
  Android types into other apps and never sees the user's edits. `allowBackup` is off, so the
  database is not copied to a cloud backup. Unlimited, like desktop (D-2026-10-22-13); retention
  is B-28.
- **Recorded:** after a take with text, in `VoiceImeService.stopAndTranscribe`,
  `FloatingMicService.stopAndTranscribe` and `TryActivity.stopAndTranscribe`, from
  `TakeDecoder.text` (the whole take, including parts already typed with Type as you go) and
  `TakeDecoder.stats()`. Insert on a background thread. A take that failed to decode, was
  discarded or produced no text is not stored.
- **Setting:** *Keep transcription history* on the Dictation screen (`Prefs.keepHistory`,
  `keep_history`, default on, as on desktop). Off stops new rows; *Clear history* deletes all rows
  (confirm dialog).
- **Diagnostics (`TakeDecoder.Stats`, core):** `decode_s` = sum of wall-clock time in every
  `Transcriber.transcribe` call of the take (trim + pad + sherpa-onnx decode), with the model load
  timed apart as `load_s` (non-zero only when the take found the model unloaded); `wait_s` = Stop
  to text, what the user waited; `segments` = pieces decoded (pause cuts + tail);
  `seconds` = raw audio length (segments + tail, before trimming). The export adds
  `rtf` = `decode_s / seconds`. Context in `decode`: `app`, `engine`
  (`sherpa-onnx nemo_transducer int8 greedy_search, sherpa-onnx <BuildConfig.SHERPA_VERSION>`),
  `threads` (`Transcriber.threads`, cores clamped to 2-4), `cores`, `device`
  (manufacturer + model), `soc` (`Build.SOC_MODEL` on Android 12+, else `Build.HARDWARE`),
  `android`, `type_as_you_go`, `all_caps`. **Not recorded:** CPU time vs wall time (decodes on
  the single worker can wait behind each other, so with long takes `decode_s` is busy time, not
  latency), RAM, thermal state, the microphone, the trimmed length, per-segment times, and
  whether a part went into the field.
- **Export:** Dictation screen → *Transcription history* → **Export CSV**. `ACTION_CREATE_DOCUMENT`
  (`text/csv`, suggested `hebrish-history-YYYY-MM-DD.csv`), so the system picker offers Google
  Drive; no permission is needed and none was added. Written on a background thread to the
  picked URI (`"wt"`). RFC 4180 (`History.csv`: quote fields with `,` `"` CR LF, double quotes;
  CRLF row ends), UTF-8 with a BOM, oldest first. Columns (`History.CSV_COLUMNS`):
  `at, text, words, seconds, model, source, model_rev, decode_s, rtf, wait_s, load_s, segments,
  context_s, type_as_you_go, all_caps, engine, threads, cores, device, soc, android, app, uid`
  (`context_s` added in 0.8.2: audio decoded again as seam context; empty on 0.8.1 rows). `at` is local
  ISO 8601 with offset. The desktop export calls its time column `timestamp` (as of 0.7.5); the
  Android name follows the table column. No share-sheet route: sharing a file needs a
  `FileProvider` (androidx) or a hand-written provider, and the picker already reaches Drive.
- Compiled, not run on a device (I).

## Context at the seams (0.8.2, 2026-10-23)

Daniel, 2026-10-23: "I'm also getting the mid-sentence capitals on Android. I don't know if
there's anything that we can do on that platform to prevent it from happening." Port of the
desktop 0.7.6 fix (`desktop/hebrish/engine.py`: `CONTEXT_S`, `Engine.transcribe_after`,
`hold_stop`, `after_held_stop`; `desktop/docs/maintaining.md`, "Context at the seams"). Debug
log: `docs/debug-log/2026-10-23-android-mid-sentence-capitals.md`.

**Cause (I, same as desktop):** a take longer than 8 s is cut into segments at pauses
(`Recorder.Segmenting`: the first pause of 0.6 s or more after at least 8 s, or a hard cut at
28 s), and each segment was decoded on its own. Parakeet treats a segment as a whole utterance:
it capitalises the first word and closes the last with a full stop. Up to 0.8.1 `TakeDecoder`
joined segment texts with a space, with no seam handling, so a pause mid-sentence gave
"word. Capital" or "word Capital". Takes under 8 s are one segment and were never affected.

**Fix (core, `TakeDecoder.piece`, `Transcriber.transcribeAfter`):**

1. Each segment after the first, and the tail after Stop, is decoded after the last
   `TakeDecoder.CONTEXT_SECONDS` (3 s) of the previous segment's raw audio. Context and segment
   are trimmed apart (`Transcriber.trim`), joined as [context, segment, 0.8 s pad] and decoded
   once. Only the tokens whose timestamp is at or after the trimmed context's length are kept
   (sherpa-onnx 1.13.8 `OfflineRecognizerResult.tokens` / `.timestamps`, checked with `javap` on
   the AAR, 2026-10-23); they carry their own leading spaces, so they are joined and trimmed.
2. `stop` = whether the text of the tokens before the boundary ends in `.` `?` `!`: the model's
   own decision at the seam, made while hearing what followed. No usable context → `stop` null
   and a plain decode: first segment; previous segment not cut in a pause (its trailing quiet,
   `Transcriber.trailingQuietSeconds`, under `PAUSE_CUT_SECONDS` 0.4 s, i.e. a hard cut that may
   split a word); context under 0.3 s; or context without clear speech
   (`Transcriber.hasSpeech`, the same frame test `trim` uses; the counterpart of desktop
   `has_speech`). Unlike desktop, Android cannot ask the `Recorder` whether a cut was in a pause
   without changing the `onSegment` signature (which Hebrish Keyboard compiles against), so it
   reads it from the audio.
3. Held full stop (`holdStop`, `afterHeldStop`, ports of desktop `hold_stop` /
   `after_held_stop`): a non-final piece ending in a single `.` is handed over without it. The
   next piece with text gets `". "` and a capital when `stop` is true, a plain space and the
   model's case when false, and the desktop `CONTINUES` rule when null (lower-case first word or
   a function word in `TakeDecoder.CONTINUES` continues; anything else is a new sentence). At
   Stop with nothing more, the `.` is handed over alone. Applies to Type as you go (`onText`), the
   whole-take path (`held`) and the history text (`keep`) alike.
4. ALL CAPS (`OutputStyle`) is applied after the seam logic, which needs the real case.

**Caller contract change:** text handed over can now start with `". "` (the held stop). The
keyboard (`commit`, `commitPart`), floating mic (`setText`, `insertInto`, `deliverPart`, `hold`)
and Try it (`insert`) all space pieces with `TakeDecoder.join`: a space after a word, none
before text starting with `. , ; : ? !`. The floating mic's paste-at-cursor path (0.7.6, cursor
past the reported text) pastes text as is, with no separator, as before.

**Measured on desktop (V, desktop measurements, not Android):** `desktop/scripts/seam_bench.py`,
108 benchmark clips each given one 0.7-2.0 s pause inside a sentence, 5 s interval:
mid-sentence capitals 73 → 30, false full stops 27 → 10, WER 6.38 % → 6.07 %, about 21 % more
decode time. Android: compiled, not run on a device (I).

**Cost on Android (I, worked out from the cut rules, not measured):** every segment after the
first and the tail decode up to 3 s more audio. After trimming the context keeps up to about
2.75 s (the cut's ≥ 0.6 s of quiet is trimmed to the 0.35 s margin). Android segments are 8-28 s
(not cut at every pause: the first cut needs 8 s of audio), so per segment that is roughly
+35 % audio at 8 s and +10 % at 28 s, against desktop's 5 s pieces. The tail is where it shows:
a 2 s tail after the last cut becomes about 4.75 s of audio, so the **wait after Stop** on a long
take can grow by the decode time of ~2.75 s of audio. Encoder cost grows with length, so the
time overhead tracks these ratios roughly (I). The history export records it: `context_s` (audio
decoded again as context, before trimming) beside `decode_s`, `wait_s` and `rtf`, so
Android's real overhead can be read from Daniel's takes.

## Clipped words at the seams (1.005, 2026-10-27)

The first word of a segment decoded with context lost its first pieces ("ividual", "chnically":
9 of 10 such fragments in Daniel's first history export were in segmented takes). Token times are
80 ms frames, so the word's first pieces could be timed just before the context's end and were
dropped with it. `Transcriber.seamSplit` now steps the split back to the start of that word.
Evidence, reproduction and the desktop twin (`engine.seam_split`): `desktop/docs/maintaining.md`,
"Clipped words at the seams".

## Voice keyboard control row (1.007, B-53, 2026-10-27)

Daniel, 2026-10-27, with a screenshot of the keyboard over WhatsApp: Pause, Retake and Discard
"need to be easier to find and easier to click, like color-coded icons and just a consistent
row"; the blue mic "looks a bit amateur"; "you shouldn't have to scroll down if you need to do a
retake or pause or discard". Up to 1.006 (`res/layout/ime_view.xml`) the mic was an 88 dp flat
blue (`accent` #24527A) circle, and Pause / Retake / Discard were grey text keys in a row
(`take_controls`) shown under it only while a take was open, with *Insert last transcript* a
further full-width row when idle. Opening a take made the keyboard taller, which pushed the key
row under the navigation bar on his phone (seen in the screenshot: the keys sit behind the
gesture bar).

Now one control row, always the same five round buttons with a short label under each:
**Discard** (`bubble_discard`, ✕), **Retake** (`bubble_retake`, ↺), the **mic** in the middle
(72 dp; `ime_mic_idle` brand green #0F6B5C with the mic icon when no take is open,
`bubble_recording` red with a rounded stop square `ic_stop_round` while one is, label Record /
Stop), **Pause** (`ime_pause` slate; `ime_paused` gold with ▶ and "Resume" while paused) and
**Insert last** (`ime_insert`, clipboard icon). `VoiceImeService.renderTake` sets icons, tints,
labels and which buttons are enabled; buttons that don't apply are disabled at 30 % alpha, never
hidden, so the keyboard has one height in every state. The buttons are `ime_round` (white oval,
tinted per button) with the `ime_round_press` ripple as foreground. The retake flash still tints
the mic amber for a second; `renderTake` leaves the mic tint alone while `flashing` and restores
it when the flash ends. The status line lost its "tap ■ to insert" hints (the mic's label says
Stop now): `ime_status_listening` / `ime_status_paused` replace `ime_listening`,
`ime_listening_time` and `ime_paused`. The order puts Discard furthest from the mic, so a
mis-tap next to Stop pauses rather than throws a take away. Floating mic and Transcription Mode
are unchanged.
Compiled (`compileFdroidDebugKotlin`, `processFdroidDebugResources`, V, 2026-10-27, JDK 21; the
local `assembleDebug` failed in cmake on locally modified `third_party` submodules, not this
change); not run on an emulator or phone (I).

## One-tap mic source in the keyboard and the floating mic (1.008, 2026-10-30)

Daniel, 2026-10-30: "Needs to be a one touch operation on Android to toggle between internal mic
and BT audio source (if available)", in both the voice keyboard and the floating mic.

- **Voice keyboard:** a source chip in the header, left of the settings gear (`R.id.source` in
  `res/layout/ime_view.xml`, `VoiceImeService.showSource` / `switchMic`). It is always shown and
  names the mic the next take will use (idle) or the take is using (`Mic.shortLabel`: "Phone",
  "BT <name>", "Wired", "USB <name>"). One tap switches: idle, it only saves the choice; mid-take
  it pauses, re-routes (`Mic.release` + `Mic.prepare`) and resumes into the same take, as the
  floating mic has done since 0.7.2; paused, it applies on Resume. No headset: the status line
  says "No Bluetooth or headset mic is connected." An `AudioDeviceCallback` (registered in
  `onCreate`) refreshes the idle chip when a headset connects or drops. The status line no longer
  appends the mic's long name ("Listening 0:12 · Bluetooth: X"); the chip carries it.
- **`Mic.toggle` (both surfaces):** decides the direction from the mic the take *asked* for
  (`Recorder.preferredDevice`, or `Mic.preferred` when idle), no longer from
  `Recorder.routedDevice`. While a Bluetooth link is still opening, the route can still report the
  phone's mic, so up to 1.007 a tap on "Phone" could switch to Automatic (Bluetooth) again and look
  like it did nothing (I: from the code; not reproduced, no device on the laptop). Phone → `Mic.AUTO`
  (Bluetooth first, then wired/USB); anything else → the built-in mic's key. It returns the mic
  switched to, or null when there is nothing to switch to.
- **Floating mic:** the chip now names the chosen mic (`preferredDevice`) at the start and after a
  switch instead of the routed one, and a tap gives a haptic tick. Its idle bubble gets no chip
  (decided without asking: the bar only exists during a take, and a chip on the idle bubble would
  be in the way of dragging; a take starts with one tap and the chip switches without losing
  audio). Tap = start, double-tap = minimise and long-press = insert last are unchanged.
- Trade-off: the chips show the mic asked for, so if Android fails to route to the headset the
  chip still says "BT"; up to 1.007 the label could flip to "Phone" in that case.
- Compiled (`compileFdroidDebugKotlin`, V, 2026-10-30, JDK 21; the local `assembleDebug` failed in
  cmake on locally modified `third_party` submodules, as on 2026-10-27, not this change); not run
  on a phone (I).

## Enter guard and Voice Typing (1.006, B-50a/B-51a, 2026-10-27)

Parity with desktop 1.007 (D-2026-10-27-02, -03). **Enter guard:** the voice keyboard's Enter
(`VoiceImeService.onEnter`) tapped while stopped takes are still landing (`finishing` not empty)
is held, status "Enter waits for the last words…", until the last take lands (`land` →
`releaseEnter`), then sent as before (`sendEnter`). After `ENTER_HOLD_MS` (4 s, desktop
`ENTER_HOLD_S`) it is sent anyway and the takes still coming are marked `diverted`: their pieces go
to `Take.late`, not the field, and become the last transcript, so **Insert last** puts them in
(status `ime_late_words`). History keeps the whole take. Leaving the field drops a held Enter.
Unlike desktop this is the default with no setting: the Enter is the keyboard's own key, so
holding it needs no keyboard grab (the reason desktop's `hold` is opt-in). Not covered: the
floating mic, where Enter is the other app's key and Hebrish cannot see it; an Enter during an
open take with type-as-you-go (desktop doesn't cover that either).
**Voice Typing:** the Dictation screen and home row are *Voice Typing*, and the tagline is
"Voice typing that gets the Hebrew words right." (`strings.xml`), as on desktop.
Compiled (`compileFdroidDebugKotlin`, V, 2026-10-27, JDK 21); not run on an emulator or phone (I).

## Personal dictionary (0.9.0, 2026-10-23)

Request R-2026-10-22-32 (I-13). Daniel, 2026-10-23: when you enter a custom word in a keyboard,
"it basically writes to the personal dictionary and you read from it". Rules, the shared test set and
the reasoning (why after decoding, not decoder hotwords) are in `../shared/personal-dictionary.md`;
desktop 0.8.0 implements the same rules.

- `core/PersonalDictionary.kt`: the entries (Hebrish's own list, pref `dict_own`, plus the system
  list `UserDictionary.Words`, word + shortcut as a heard-as phrase, cached in `dict_system`) and
  `compile()`, one combined regex. `TakeDecoder` compiles it lazily on the worker at a take's first
  piece and applies it to each piece after the seam rules, before ALL CAPS. History therefore
  holds the corrected text (same as desktop).
- Access (V, AOSP source read 2026-10-23): `UserDictionaryProvider.canCallerAccessUserDictionary()`
  allows the system, an **enabled** IME or an enabled spell checker (uid and package match);
  anyone else gets an empty cursor, a null insert and 0 deletes, no exception. It is "enabled",
  not "current", so once the voice keyboard is switched on in Settings the floating mic (same uid)
  reads and writes the list too, whatever keyboard is in use. `systemAccess()` checks
  `enabledInputMethodList` for our package, and only then is an empty read trusted.
- Screen `DictionaryActivity` (home, side menu): add (word + optional heard-as, written to the
  system list as `addWord(ctx, word, 250, shortcut, null)` and always to `dict_own`), list (own and
  system merged by word), remove (from both; the confirm says the system removal reaches every
  keyboard), and a button to Android's own screen (`ACTION_USER_DICTIONARY_SETTINGS`).
- The core is compiled by Hebrish Keyboard too (`core/README.md`); there the package is the
  keyboard itself, so it reads the list whenever it is enabled. Its submodule is not bumped in this
  release. API levels used are all ≤ 16, so minSdk 21 holds.
- Testing: no unit-test setup in the app, so `scripts/check_dictionary.sh` compiles
  `PersonalDictionary.kt` with Gradle's cached Kotlin compiler and runs the shared cases on the
  JVM: 21/21 (V, 2026-10-23). Android's regex is ICU, not the JVM's; the patterns use only
  `\p{L}`, `\p{N}`, lookarounds and CASE_INSENSITIVE|UNICODE_CASE, which both support (I).

## Disfluency chop (1.001, 2026-10-24)

Request R-2026-10-24-1, B-38a, decision D-2026-10-24-04: *um, uh, eh, ehm, er, erm, hmm* are
removed from every piece, always, for every model; no setting. Rules and the shared test set:
`../shared/disfluencies.md`, `../shared/disfluency-cases.json`.

- `core/Disfluency.kt`, `chop()`. `TakeDecoder.piece()` applies it to the decoded text before the
  seam rules, the personal dictionary and ALL CAPS, so a filler never reaches History or the seam
  logic. Hebrish Keyboard gets it with its next core submodule bump.
- Testing: `scripts/check_disfluency.sh` (same JVM harness as `check_dictionary.sh`; needs
  `JAVA_HOME` set to a JDK 21 if the default points elsewhere): 33/33 (V, 2026-10-24). The app was
  not built locally (no NDK on the laptop); the CI `apk` job built bd60ad8 (run 40084327871, V).

## Floating mic out of the way: grip, bar along the edge, smaller defaults, icons (1.000, 2026-10-24)

Daniel, 2026-10-24: "I'll start dictating, it'll open, and then suddenly it [is] overlaying some
text I'm working on." Asked for: moving the overlay during a take; left as the default side; a
smaller default; every opacity/size control down to its minimum with − / + buttons "so that you
can really dial in exactly what you're looking for"; a size setting for the expanded bar; a clear
mode ("a transparent background for the expander, so that the buttons are set against a mostly
opaque background"); idle icons with the app logo's H and the Hebrew letter ayin on green. The
objective, in his words: "the expansion happens in the least obtrusive part of the screen".

- **Moving during a take.** Dragging the mic or any part of the bar already worked since 0.3.0
  (`Drag`), but the only obvious handle was the mic, and a tap on it during a take is Stop. 1.000
  adds a grip (`ic_drag`, `grip`) at the bar's outer end, shown whenever the bar is (take or held
  transcript). Drag only, no tap action. (I) that the grip is what was missing; not reproduced.
- **Bar along the edge** (`Prefs.bubbleBarDirection`, `bubble_bar_direction`, default `along`;
  `across` is the 0.4.0–0.10.0 behaviour). Along: the root `LinearLayout` is vertical, children
  hug the mic's side (`r.gravity` LEFT/RIGHT, so a wide chip can't shift the mic), the source
  chip is capped at `SOURCE_ALONG_DP` (72). The column opens **down** from a mic in the top half
  and **up** from one in the bottom half. Up keeps window gravity TOP and moves the window's
  top by the bar's measured height (`r.measure(UNSPECIFIED)` in `place()`), so `Drag` and the
  coordinate system are unchanged; the mic is then the last child (`placedUp`), which
  `savePosition()` uses to recover the mic's top. Because the up-placement depends on whether the
  bar is showing, `render()` sets visibilities first and re-places when `expanded()` changes
  (`placedExpanded`), as it already did for the dot (`placedMini`). Not chosen: Gravity.BOTTOM
  anchoring, whose origin (above or below the navigation bar) differs from `displayMetrics`.
- **Bar size** (`Prefs.bubbleBarScale`, 50–100 %, default 80): bar buttons are `BUTTON_DP` (44)
  × scale square with `BUTTON_PAD_DP` (10) × scale padding, `FIT_CENTER`; the timer, chip and
  Insert text scale too. The mic keeps `bubbleSize`.
- **Clear bar** (`Prefs.bubbleBarClear`, off by default): bar background alpha 0; the plain
  buttons (grip, Pause, the held-transcript ×) get an oval backdrop and the timer and Insert a
  rounded one, in `ime_bg` at `BACKDROP_ALPHA` 230/255 (`styleBackdrops()`, one drawable per
  view). Retake/Discard and the chip already have fills.
- **Icons** (`Prefs.bubbleIcon`: `mic` default, `logo`, `ayin`). `ic_bubble_h` is the mark's H
  path (from `ic_hebrish`) on a 36-unit viewport cropped round it; `ic_bubble_ayin` is U+05E2
  from Noto Sans Hebrew Bold (the brand's Hebrew face), outline extracted with fontTools onto the
  same 64 grid. Both are drawn cream on `hebrish_green`, ignoring the colour swatches; during a
  take the mic is red with Stop as before. Rendered as SVG to check centring (2026-10-24).
- **Defaults and ranges:** side `left` (was right), `bubbleX` 0.1 (was 0.9), size 44 dp (was 56),
  size range 20–96 dp (was 36–96), idle opacity and bar opacity minimum 1 % (were 25 % and 20 %).
  New defaults only apply where no value is saved: an install whose mic was ever dragged keeps
  its side and height.
- **Settings screen:** − / + buttons beside the label of each slider (size, idle opacity, bar
  size, bar opacity) step by 1 (`stepped()`); radio rows via `choice()` (side, icon, bar
  direction); a "While you talk" section for the bar settings.
- Compiled, not run on a device (I). To verify on a phone: dragging by the grip mid-take; the
  upward column's mic not jumping on open/close (measured height before layout); the column on a
  right-edge mic; 50 % bar buttons still hittable; clear bar legibility over light and dark apps.

## "Pasted from your clipboard": a tip, not a fix (1.000, 2026-10-24; superseded 2026-10-25, see below)

Daniel, 2026-10-24: every floating-mic insert makes Android say the app "pasted from your
clipboard"; "definitely going to get on everyone's nerves". Asked to prevent it, or else tell users
to turn it off.

- Cause: since 0.9.1 the floating mic inserts with clipboard + `ACTION_PASTE` (see "Floating mic
  pastes instead of rewriting"). Android 12+ shows a clipboard-access toast whenever an app reads a
  clip that another app set. AOSP `ClipboardService.showAccessNotificationLocked` skips it only
  if the reader is the clip's owner or the default IME, or if the secure setting
  `clipboard_show_access_notifications` is 0 (from AOSP, as remembered; not re-read 2026-10-24) (I).
- Can't be prevented by the app: changing that setting needs `WRITE_SECURE_SETTINGS` (adb only),
  and no clip flag suppresses the toast (`ClipDescription.EXTRA_IS_SENSITIVE` only hides the
  Android 13 copy preview). The only way round it is `ACTION_SET_TEXT`, which was the default up
  to 0.9.0 and was dropped for jumping fields and lost line breaks. Not brought back.
- What ships: on Android 12+ (`SDK_INT >= S`), after the first successful paste, one long toast
  (`bubble_clipboard_tip`, delayed `CLIPBOARD_TIP_DELAY_MS` so it follows Android's own toast;
  `Prefs.clipboardTipShown`); and on the Floating mic screen a note plus **Open privacy settings**
  (`Settings.ACTION_PRIVACY_SETTINGS`, falling back to `ACTION_SETTINGS`). The toggle is *Show
  clipboard access* under Privacy on Pixel / stock Android 12+; the name and place on other
  phones (Samsung, OnePlus) are not checked (I).
- Not compiled locally: since the F-Droid source build (pulled 2026-10-24) the laptop needs NDK
  26.3.11579264 to configure the project; CI compiled it.

## Floating mic types through its own input connection first (2026-10-25)

Daniel, 2026-10-25: the clipboard notice on every insert is "really irritating"; the priority is
that text lands in **any field in any app**, through an ordered fallback chain. This replaces the
"a tip, not a fix" conclusion above: there *is* a way round the notice that keeps 0.9.1's
paste behaviour (cursor insert, no rewrite, line breaks kept).

- **New first method:** API 33's `AccessibilityService.InputMethod` (enabled by
  `flagInputMethodEditor` in `res/xml/floating_mic.xml`; `FloatingMicService.commitDirect`).
  The service gets its own `AccessibilityInputConnection` to the focused editor and calls
  `commitText(insert, 1, null)`. That is a keyboard-style insert at the cursor: no clipboard, so no
  "pasted from your clipboard" toast. Signatures read from `android.jar` (platform 37.0) with
  `javap`, 2026-10-25 (V): `getInputMethod()`, `InputMethod.getCurrentInputStarted()`,
  `getCurrentInputConnection()`, `getCurrentInputEditorInfo()`; the connection has `commitText`,
  `getSurroundingText`, `deleteSurroundingText`, `setSelection`, `sendKeyEvent`, all returning
  void except `getSurroundingText`.
- **Checked, because `commitText` returns void:** used only when an input session is started, its
  `EditorInfo.packageName` is the target node's app, and the node is the focused field (the
  connection always follows focus; the take's field may have lost it). `getSurroundingText(64, 0, 0)`
  must answer first: its text before the cursor is the field's real content, so the separator is
  judged from it (a hidden trailing break and WhatsApp's hint-reported-as-text both stop
  mattering). After the commit, the text before the cursor must end with the insert; otherwise
  `commitDirect` returns false and the chain carries on. Risk: a commit that landed but couldn't be
  confirmed would be pasted again (doubled). Not observed; inferred unlikely because both reads go
  through the same connection right after the commit (I).
- **Chain now** (`insertInto`): input connection (API 33+) → clipboard + `ACTION_PASTE` (placeholder:
  `SET_TEXT` first) → `ACTION_SET_TEXT` (hidden-tail handling unchanged) → hold for **Insert**. Each
  success logs `Inserted by …` under tag `HebrishFloatingMic` (`adb logcat -s HebrishFloatingMic`),
  so a field that falls through can be identified from a log. `clipboardTip()` still runs only on
  the paste path.
- **Field discovery** was already wide (`focusedField`: findFocus, Compose host search, last
  editable from events, all app windows); unchanged.
- **Not verified on a phone** (I): whether Android grants the new flag to an already-enabled service
  without turning it off and on (the README tells users to toggle it once if the notice persists);
  how the real keyboard (Gboard, HeliBoard) behaves while the service commits in parallel; and which
  apps' editors answer `getSurroundingText` (those that don't fall back to paste, as before).
  Android 9-12 are unchanged (paste first). Compiled locally (`./gradlew :app:compilePlayDebugKotlin`,
  JDK 17; the shell's `JAVA_HOME` pointed at a missing JDK and had to be overridden).

## Overlapping takes (1.001, 2026-10-24)

R-2026-10-24-6, B-43a (desktop B-43; story in `docs/debug-log/2026-10-24-record-ignored-while-transcribing.md`).
**Rule: a mic tap is never ignored because the last take is still transcribing.**

- `FloatingMicService` and `VoiceImeService` keep a `Take` per take (its `TakeDecoder`, the text
  it put in, pieces `waiting`, and on the floating mic the target field) instead of one
  `decoder` / `takeText` / `target`. `take` is the open one; `finishing` the stopped ones, oldest
  first. `State.TRANSCRIBING` now means "no take open, earlier ones still landing" (`settled()`).
- Order: each take has its own decoder thread and they share `Transcriber`'s lock, so a later
  take's piece can be decoded first. `deliverPart` holds it in `waiting` while an older take is
  still in `finishing`; `land()` (the oldest take's finish) records it in History, flushes the
  next take's waiting pieces and lands that one too if its decoder already finished.
- Keyboard: the mic stays enabled while transcribing (`show` no longer disables it). Status
  messages and "switch back when done" wait until nothing is in flight.
- Try it is unchanged (one take at a time, mic disabled while busy): it is a demo.
- Compiled locally (both flavors). Not run on a device.

## Transcription Mode (1.001, 2026-10-24)

R-2026-10-24-5, B-41a (parity with desktop B-41), D-2026-10-24-06. Home → **Transcription Mode**
(`TranscriptionActivity`, a `Page`).

- **Recorder:** `core/Tape.kt`. Writes a WAV (16 kHz mono int16) to `filesDir/recordings/` as it
  captures: app storage, so no storage permission (this answers I-10's question about all-files
  access). Header rewritten every 2 s and on pause/stop; `Tape.recover` fixes a lagging one. Cap
  4 h. Digital gain (`Prefs.tmGainDb`, −12…+24 dB) before the meter and the file; the clip lamp
  lights for input clipping and gain clipping.
- **Mic:** `Prefs.tmMic` (Automatic or a `Mic.key`), separate from the keyboard's `micChoice`.
  `Mic.preferred` takes the choice as a parameter now; `Mic.routeFor` opens the Bluetooth link.
  *Change mic* mid-recording reopens AudioRecord on the new device, same file.
- **State is process-wide:** `Recording` (in `TranscriptionService.kt`) holds the `Tape` and the
  held file; the screen redraws from it (`Recording.listener`), so a recording outlives the screen.
- **Background (B-42a, D-2026-10-24-07):** opt-in, `Prefs.tmBackground` (Setup's optional step
  `background`, or the switch on the screen) plus notifications on Android 13+
  (`Recording.background`). Then Record starts `TranscriptionService`, a foreground service of type
  `microphone`, started while the screen is in front as Android 14 requires. Its notification has a
  chronometer and Pause/Resume and Stop (actions back into the service); later redraws go through
  `NotificationManager.notify`, not a second `startForegroundService`, which Android 12+ may refuse
  from the background. Without it: the screen is kept on and `onPause` pauses (mic released, file
  kept). A mic that disappears (read < 0) pauses with a message instead of ending the take.
- **Play:** the microphone foreground service has to be declared in the Play Console (App content →
  Foreground service permissions) before a Play release carrying B-42a.
- **Transcribe:** `Tape.segments` reads the file back in 100 ms chunks and cuts it with the live
  take's rules (`Recorder.Segmenting`, copied as `Tape.Cutter` rather than refactoring the
  keyboard's `Recorder`), feeding `TakeDecoder` (seams, held stops, dictionary, disfluency chop as
  for any take). The reader waits while the decoder is more than two segments behind, so memory
  stays small. A paragraph roughly every 30 s of audio, as on desktop. History source `record`.
  The file is deleted on success; on failure or Cancel it stays and is offered at the top.
- Compiled locally (`compileFdroidDebugKotlin`, JDK 21, after installing NDK 26.3.11579264;
  the native cmake step still fails on the laptop, so the APK comes from CI). Not run on a device.

## Transcription Mode: Paragraphs setting (unreleased, B-44a, 2026-10-24)

D-2026-10-24-09, parity with desktop B-44. Spec: `../shared/paragraphs.md`; test file
`../shared/paragraph-cases.json`. Transcription Mode has a **Paragraphs** line under the progress
bar ("Paragraphs: Time-based" + *Change*), which opens a single-choice dialog: **None** (one block),
**Time-based** (the 30 s split, `PARAGRAPH_S`), **Paragraph model**. Remembered in
`Prefs.tmParagraphs`; unset means Paragraph model if installed, else Time-based (`ParagraphMode.get`).
Dictation (keyboard, floating mic, Try it) is unchanged.

- **Code:** `Paragraphs.kt` (Python-style word split, `windows()`, most-central merge, join, and
  `WordPiece`: BERT uncased as HF `tokenizers` runs it), `ParagraphModel.kt` (ORT Java API from the
  `onnxruntime-android` AAR the app already ships; session created on first use on a worker, kept
  while the screen is open with Paragraph model chosen, closed when the setting changes or the
  screen is destroyed; `Transcriber.threads` intra-op threads). Neither imports `android.*`, so the
  check script compiles them as they are. Not in `core/`: Hebrish Keyboard compiles `core` without
  the ORT Java classes. `libonnxruntime4j_jni.so` was already in the APK (from the same AAR), so no
  new native binary.
- **Download:** `ParagraphStore.kt`. `latest.json` from `cdn.hebrish.app/models/paragraph-breaks/`,
  files into `filesDir/models/paragraph-breaks/<version>/` through `ModelStore.downloadFiles` (the
  speech models' loop, split out of `ModelStore.download`: resumable `.part`, SHA-256, rename when
  verified; an additive core change). The manifest is stored (`Prefs.paragraphModel`) only after
  every file verified, then other version folders are deleted. Threshold: the manifest's, else
  `config.json`'s `paragraph_threshold`. Not a catalogue model, not in the model picker. Progress
  shows in the Paragraphs line and a bar under it.
- **Flow:** `TranscriptionActivity.Take` keeps the take's pieces with their time-based break flags,
  and `shown` is what the app last wrote. Each piece redraws the box in the current setting
  (appended when it only adds text). With Paragraph model the box fills as one block while
  decoding; when transcription finishes the model runs on `paraWorker`, and its text replaces the
  box only if the box still equals `shown`; otherwise the status line says the paragraphs were not
  changed. Changing the setting re-flows the take under the same rule. Model missing (or still
  downloading), failing to load or throwing: Time-based for that take, with a status message; when
  a download finishes, the current unedited take is redone. History gets the take as the app showed
  it (with its paragraphs; the model's text when it ran), recorded once the text is final, also if
  the screen closed meanwhile. A held-back full stop at the start of a time-based paragraph's first
  piece (". Next") now stays at the end of the paragraph before (before B-44a it began the new one).
- **Background (B-42a):** unchanged. Only the recording runs in `TranscriptionService`; transcription
  and the paragraph step run in the screen, as before.
- **Tests:** `scripts/check_paragraphs.sh` (JDK 21, `uv`, network on first run; cached in
  `~/.cache/hebrish-checks`). 2026-10-24 (V): windows and word_pieces of all 11 cases exact; 3000
  fuzz words (Latin with accents, Greek incl. final sigma, Cyrillic, Hebrew with points, CJK, kana,
  Hangul, combining marks, controls, Cf, private use, unassigned, U+FFFD, NUL, symbols, emoji,
  special-token text such as `[SEP]`, words over 100 characters) identical to HF `tokenizers` ids;
  fp32 `model.onnx` (the strict target, from the Hub) vs `probs_fp32`: max |dp| 6.6e-06 (limit
  0.001), all 11 `output_fp32` identical; int8 on ORT Java 1.28.0: output differs from the input
  only in whitespace, break decisions differ from fp32 on 8 of 1,412 words (limit max(2, 2%) per
  case); Kotlin + ORT Java 1.28.0 vs the Hub's `paragraphs.py` + ORT Python 1.28.0 on the int8 model:
  max |dp| 5.6e-08, every output identical. 3099/3099 checks. The fuzz caught one rule the spec draft had wrong:
  unassigned code points (Cn) are kept (HF gives [UNK]), only Cc/Cf/Co/Cs are dropped.
- **int8 drift (V, 2026-10-24):** the int8 model's scores depend on the ORT version and CPU far
  beyond the spec's first 0.02 tolerance (which is why fp32 is now the strict target). Same laptop, same inputs: ORT 1.28.0 and 1.29.0 agree, 1.30.0 and
  1.31.0 agree, and the two pairs differ by up to 0.62 per word (syn-2-0002, word 175); against
  the cases' ORT 1.31 values the app's ORT 1.28 gives 14 word scores off by more than 0.02 and 3
  break decisions different over the 11 cases. int8 vs fp32 differs by up to 0.98 on single words
  on either version. The app ships int8 and ORT 1.28 (tied to sherpa-onnx), so phone results can
  differ from desktop's on borderline breaks; the text never changes, only where blank lines go.
- **Latency:** laptop x86, 1 thread, int8, ORT Java 1.28: 0.20 s for 208 words, 0.83 s for 566
  words (2 windows); about 0.4 s for the first call (session load). Phone: not measured (no device).
- **Size:** the model is downloaded (34 MB). Debug APK +54,016 bytes (fdroid) / +54,020 (play),
  clean builds before and after, all dex and resources.
- Built locally (`assembleFdroidDebug`, `assemblePlayDebug`, JDK 21, NDK 26.3.11579264) in a fresh
  clone with submodules. Not run on a device.

## Clean up: S1-mini on the phone, and Post-processing in Models (unreleased, B-40a, 2026-10-30)

Parity with desktop B-40 (`desktop/hebrish/cleanup.py`). Daniel, 2026-10-30: quantise it for
phones and offer it; then offer **two** models, **stock S1-mini by Superwhisper as the default**
and his fine-tune S1-ASR-Cleanup as **experimental** until it is better validated; no benchmark
for this step. Licence: every place a model is named reads "S1-mini" by "Superwhisper".

- **Catalogue:** `../shared/catalogue.json` `addons`, kind `text_cleanup`, entries `s1-mini`
  (`default: true`) and `s1-asr-cleanup` (`experimental: true`). Android reads only an entry's
  `android` block (file, size, SHA-256, `ram_mb`, optional `revision`). An entry with placeholders
  or no `android` block is skipped (`CleanupStore.parse`). Android builds before this ignore `addons`.
  Files (both Q4_K_M, which keeps the most sensitive tensors at Q6_K):
  - stock: Superwhisper's own `superwhisper/s1-mini-GGUF` `s1-mini-q4_k_m.gguf` (484,219,808 bytes),
    pinned to commit `34add00a48a2e5d24e5a4ee5405a99620a3a240c`; Superwhisper's card calls it the
    build its published accuracy was measured on. Desktop uses the same file. Not re-hosted.
  - fine-tune: `danielrosehill/S1-ASR-Cleanup` `s1-asr-cleanup-v1.0-Q4_K_M.gguf` (396,704,480
    bytes), made 2026-10-30 from the v1.0 safetensors (`convert_hf_to_gguf.py --outtype f16`, then
    `llama-quantize … Q4_K_M`, llama.cpp b11982; transformers 5.x needed: 4.57 crashes on the
    tokenizer config's list-form `extra_special_tokens`). Uploaded after the `v1.0` tag, so pinned by
    commit `33b39785995179277426beac2da5c243970df3b0` (`android.revision`). The stock GGUF is bigger
    because it carries a separate output matrix.
  - Sanity check only (no benchmark, Daniel): each file loaded in llama-server b11982 on the laptop
    and cleaned one test sentence coherently through `cleanup.py`'s own `clean()`. Peak RSS at ctx
    4,096: stock Q4_K_M 1.24 GB, fine-tune Q4_K_M 1.16 GB (desktop context; Android's is smaller).
    Q4_0 was also tried for the fine-tune and dropped words on that one sentence; not used.
- **Runtime:** llama.cpp **b11982** (the build desktop's `llama-server` is pinned to) as the
  submodule `third_party/llama.cpp`, compiled into its own `libhebrish-llama-jni.so`
  (`src/main/cpp/CMakeLists.txt`, bridge `s1_cleanup_jni.cpp`), loaded only when Clean up first runs.
  No llama-server: Android can't run a downloaded executable, and F-Droid needs it built from source.
  Flags: `GGML_CPU_ARM_ARCH=armv8.2-a+dotprod+fp16`, OpenMP off (ggml's thread pool; no libomp to
  ship), KleidiAI off (upstream's Android example turns it on, but it is fetched at configure time
  and the build is offline). A CPU without `asimddp` in `/proc/cpuinfo` (Cortex-A53/A73 era) is not
  offered clean-up (`CleanupModel.supported()`); the library would hit illegal instructions there.
  Library: 54.6 MB unstripped, **6.6 MB stripped, about 2.5 MB compressed** in the APK (NDK
  26.3.11579264, built alone on the laptop 2026-10-30, all four `Java_..._CleanupModel_native*`
  symbols exported). The full app native build was not run locally (it comes from CI).
- **Code:** `Cleanup.kt` is `cleanup.py`'s logic line for line (prompt, `[Layers: 1,2]`, chunks at
  sentence ends, 1.3 x input + 32 output cap, the guard: empty, cut off or a dropped dictionary word
  keeps that chunk raw); no `android.*`. One deliberate difference: chunks of at most **600** tokens
  and a **1,536**-token context (desktop 900 / 4,096), so the f16 KV cache is about 170 MB instead
  of about 470 MB. Timeout per chunk 45 s + 0.2 s per output token. `CleanupModel.kt` is the JNI
  wrapper (UTF-8 byte arrays, not jstring: JNI's modified UTF-8 breaks on non-BMP characters; greedy
  sampler; stop at end-of-generation; a deadline through llama.cpp's abort callback).
  `CleanupStore.kt` downloads from Hugging Face at the entry's tag through `ModelStore.downloadFiles`
  into `filesDir/models/<id>/<version>/`; the user's pick is `Prefs.cleanupChoice`, else the default.
- **Transcription Mode:** a **Clean up** switch (`Prefs.tmCleanup`, off by default) with the chosen
  model's line and *Change* (pick a model; *Delete unused*). Turning it on with the model missing
  asks before downloading (size and memory). When a take finishes, the flat text (after the
  disfluency chop and the dictionary) is cleaned on `paraWorker`; the model stays loaded until the
  switch goes off, the model changes or the screen closes. Its paragraphs replace the Paragraphs
  setting (that line is dimmed and says so); if nothing was cleaned, the Paragraphs setting runs
  as before. Same edited-box rule as paragraphs: the text replaces the box only while it still
  holds what the app wrote. History records the cleaned text.
- **Models screen:** a **Post-processing** section (desktop: Models, Utilities) lists the paragraph
  model (B-44a; until now only reachable from Transcription Mode's Paragraphs dialog) and each
  clean-up model, with Download / Cancel / Delete and *Use for Clean up*. `ParagraphStore.remove`
  added for its Delete.
- **Add-on models, easier to find (2026-10-31).** Daniel: the section sat below the long list of
  speech models, so "you have to really dig through to find it". The heading is now **Add-on
  models** (string `models_post`; desktop: Models › Utilities; catalogue: `addons`), its intro
  starts "Paragraphs and clean-up", and a button under Download all (`models_addons_jump`,
  "Add-on models: paragraphs and clean-up ↓") smooth-scrolls the screen's `ScrollView` (Page's
  `column.parent`) to that heading. Checked: `./gradlew --offline compileFdroidDebugKotlin`
  (JDK 21, V); not run on a phone.
- **Checked (2026-10-30):** `./gradlew --offline :app:compileFdroidDebugKotlin` (JDK 21); the JNI
  library built alone with the pinned NDK (above). Not run on a phone: speed and memory on a real
  device are unknown, and long takes may take a while to clean.

## Transcripts folder and titles (unreleased, B-74a/B-75a, 2026-10-31)

Daniel, 2026-10-31 (R-2026-10-31-7): "bring the title model to Android, and keep at least some of
the transcription features available there". Parity with desktop B-74/B-75/B-78
(`desktop/hebrish/transcripts.py`, `titles.py`; desktop maintaining.md, "Transcript in one go,
Next recording, titles, versions"). B-77a (transcript in one go, Next recording) is not done.

- **Save (B-74a).** Transcription Mode's text box has **Save** (primary, before Copy / Share /
  Clear) and, under it, a line saying where Save writes plus **Folder…**. The folder is picked
  with the system picker (`ACTION_OPEN_DOCUMENT_TREE`) and kept with a persisted read/write grant
  (`TranscriptFolder.accept`, pref `transcripts_tree`; the old grant is released on a change).
  Storage Access Framework only: no all-files permission (Google Play refuses it for this kind of
  app), and the picker also offers SD cards and cloud providers' folders. No folder yet (or the
  grant was revoked): Save opens the picker, then saves.
- **Layout and names** as desktop: `<folder>/YYYY/MM/DD/<stem>.md`, stem `HH-MM-SS` or
  `<snake_case_title>_HH-MM-SS` (`Transcripts.slug`, ASCII, at most 60 characters at a word end),
  `-2`, `-3`, … while the day folder already has `<stem>.md` or `<stem>.json`. Day folders are
  created with `DocumentsContract.createDocument`; files are created as
  `application/octet-stream` because a provider may append `.txt` to a name given a `text/*` type
  it doesn't map to `.md` (AOSP `FileUtils.splitFileName`; octet-stream keeps the name as given).
- **File format (B-78), copied from desktop.** YAML front matter (`title`, `date` ISO with offset,
  `version`, `generator`, `model`, `audio_seconds`, `source`, `cleanup_model`, `versions`; empty
  ones left out; strings JSON-quoted), `# <title>` or `# Transcript`, `## <Weekday> <d Month yyyy>,
  HH:MM` (English names, ASCII digits whatever the phone's language), the credit line
  `*Transcribed by Hebrish Android 1.0xx with Sabich v2.3 on 31 October 2026.*`, the text.
  Android values: `generator` "Hebrish Android <versionName>" (the version numbers of the two apps
  differ, so the platform is named), `model` the catalogue name plus the installed version label,
  `source` "recording", `cleanup_model` "<name> <version>" when Clean up changed a part.
- **Versions.** `<stem>.md` (the box, edits included), `<stem>.raw.md` (each take's text as
  decoded, before clean-up and edits; written only when its words differ), `<stem>.json`
  (schema 1, desktop's manifest: shared fields, one entry per version). No *Save cleaned copy* on
  Android. Save on an unchanged box says "Already saved: <path>".
- **The document behind the box** (`TranscriptionActivity.Doc`, desktop `_doc`): the first take's
  time, raw text per take, models, audio seconds, clean-up models, what was last saved. A take that
  starts in an empty box starts a new one; Clear drops it. Typing into an empty box and saving
  works (saved with the current model and now).
- **Titles (B-75a).** Catalogue `title-gemma-270m` now has an `android` block: the desktop Q8_0
  file as is (`openwebui-title-generator-270m.q8_0.gguf`, 291,546,016 bytes, SHA-256
  `94eb69ae…`, revision `66dd1caf…`), `ram_mb` 450 (an estimate, not measured), and `android` /
  `phone` in `platforms` / `devices` (desktop's `offered()` checks only its own OS and `runtime`,
  so it is unaffected; desktop tests pass). `CleanupStore.entries(ctx, kind)` reads either kind,
  deciding cached-vs-bundled catalogue per kind (a cached catalogue with clean-up models but no
  Android title entry still finds the bundled one; the desktop debug log
  `docs/debug-log/2026-10-31-title-model-download.md` is the same trap). `CleanupStore.title` /
  `titleFile`; one download at a time across both kinds; `Status.Failed` now carries the id so
  Transcription Mode says which model failed.
  - Models › Add-on models has a card for it (Download / Cancel / Delete). Transcription Mode has
    the switch **Give saved transcripts a title** (pref `titles`, on by default as on desktop;
    turning it on without the model offers the download) and a status line. Hidden on phones
    without ARMv8.2 dot product (`CleanupModel.supported`). No *Longest title* setting yet:
    pref `title_max_chars` (default 60, 16–120) is read but has no UI.
  - `Titles.kt` is `titles.py` line for line: Open WebUI's title prompt in Gemma's template,
    first 1,200 words, greedy, 40 tokens, `clean()` / `fit()` of the JSON reply. Android
    difference: the model runs with a 2,048-token context (`Titles.CTX`; `CleanupModel` now takes
    `nCtx`), and a prompt that would not fit with the 40 output tokens is cut by a quarter of its
    words at a time (romanized Hebrew can pass 2,000 tokens in 1,200 words). Stops at
    `<end_of_turn>` through llama.cpp's end-of-generation check in the JNI.
  - Save runs the title on `paraWorker` (which owns the models): the clean-up model is closed
    first to keep memory down, the title model loaded, run and closed. Any failure, or nothing left
    after cleaning, saves by the time alone. Status: "Writing a title…", then "Saved: <path>".
- **Tests:** `app/src/test/…/TitlesTest.kt` (every case of `desktop/tests/test_titles.py`, plus
  the context cut) and `TranscriptsTest.kt` (names, slug, no overwrite, the front matter / H1 / H2
  / credit line byte for byte as `test_transcripts.py` checks, raw version and manifest). The
  app's first JVM unit tests: `testImplementation` junit 4.13.2 and org.json 20240303 (android.jar's
  org.json is a stub off-device). Run `./gradlew testFdroidDebugUnitTest`.
- **Checked (2026-10-31):** the 12 JVM tests pass; `assembleFdroidDebug` builds (JDK 21, a clean
  worktree with every submodule at its pinned commit, 19.4 MB debug APK with
  `libhebrish-llama-jni.so` and the new catalogue); desktop tests pass apart from the known
  `test_numbers_and_rules_match_the_website`. **Not run on a phone:** the folder picker, writing
  through a real provider, the title model's speed and memory, and whether 2,048 tokens of context
  load comfortably on a mid-range phone are all unverified (B-75a's phone check is still open).

## Robustness pass: dead ends, leaks, main-thread work (unreleased, 2026-10-30)

A whole-app review (`android/app/src/main`, `android/core/src/main`) and its fixes. No measured
rule changed: trailing pad, segment cuts, deferred reload and the update protocol are untouched.
**Rules that came out of it:**

- **System screens open through `Setup.openSystem(ctx, intent, fallback…)`** (`MainActivity.kt`,
  object `Setup`). It tries each intent in turn and, when the phone has none of them, shows
  `no_settings_screen`. Up to 1.008 most setup buttons called `startActivity` on a settings action
  directly, so a ROM without that screen (`ActivityNotFoundException`) crashed the app. The
  battery button (Setup and the floating mic guide) is one helper, `Setup.askBattery`; App info is
  `Setup.appInfo` / `Setup.appInfoIntent`. Web links go through `Page.open` (ModelsActivity's line
  links swallowed the failure before).
- **Copy and Share are `TextOut`** (Try it, Transcription Mode, Install): an empty box says
  "Nothing to copy/share yet" instead of a false "Copied" or no reaction.
- **No dead ends on Try it:** with no model it shows **Open Models** and loads the model when the
  user comes back with one; a failed load shows **Try again**. "Set it up for every app" opens the
  Setup checklist (it only closed the screen, which from home went nowhere).
- **Long work off the main thread:** "Use this model" unloads and preloads on a worker thread
  (`Transcriber.unload` waits for a decode in progress, since it holds the lock, and froze the
  Models screen meanwhile); Delete removes the model files on a worker thread.
  `Transcriber.preload` runs one load at a time (an `AtomicBoolean`); before, each field focus
  started a thread that queued on the lock.
- **Transcription Mode:** a write error on the capture thread (storage full) ends the take as the
  length limit does, keeps the file and shows `tm_write_failed` (`Tape.writeError`); before, the
  uncaught `IOException` killed the app. The screen stops its 80 ms redraw loop in `onDestroy`,
  because with background recording the take outlives the screen and the loop kept the destroyed
  Activity alive. Seconds shown for a held or leftover file come from its size (`Tape.seconds`);
  `Tape.recover`, which rewrites the WAV header, ran on every redraw. A failed Resume now shows
  its error (it was cleared on the next line).
- **Takes:** a type-as-you-go piece already posted to the main thread when Discard or Retake ran
  is dropped (`TakeDecoder.isCancelled`); it used to be typed in after the discard. Both services
  clear their main-thread callbacks in `onDestroy`, and the keyboard also drops an open take and
  the takes still landing there (normally `onFinishInputView` has already done it).
- **Floating mic, accessibility events:** once a focused field is known, click and text events
  from views that aren't editable no longer run the full probe (windows list, `findFocus`, up to
  `MAX_NODES` per window); focus and window events still do (`PROBE_EVENTS`). The rising edge
  (preload, show the bar) is decided exactly as before.
- **Downloads:** each file's `HttpURLConnection` is disconnected in a `finally` (a cancel or read
  error skipped it), and progress is published every 2 MB but at most 5 times a second, because
  each update rebuilds every card on the Models screen.
- Lint: the app has product flavours, so the task is `:app:lintFdroidDebug` (plain `lintDebug` is
  ambiguous). Before this pass it reported 1 error (a literal byte-order mark in `History.kt`,
  now `"\uFEFF"`) and 54 warnings; after, 0 errors and 51 warnings, none new.
- Compiled both flavours and linted locally. Not run on a device or an emulator (the native build
  needs the `third_party` submodules checked out).

## Model memory and the drag crash guard (1.010 hotfix, 2026-10-31)

Reported 2026-10-31 by the session managing Hannah's phone (Pixel 11 "cubs", Android 17 / SDK 37,
12 GB RAM; installed from F-Droid). Released as a stability hotfix on Daniel's word ("push out this
as a new stability release (android only)"), from branch `hotfix/android-1.010` off
`android-v1.009`, so none of the unreleased sprint work on `main` ships with it.

**Memory (V on her phone, numbers from `dumpsys meminfo`):** on 1.009, 94 s after the process
started (20:51:50 to 20:53:24), Native Heap PSS was 717,368 KB (TOTAL PSS 751,895 KB, RSS 871 MB),
with no dictation yet. On 0.6.0 the same ~700 MB sat in swap and lmkd killed background apps
("low watermark is breached"). Cause (I, from the code): not a leak. `Transcriber` holds one
recognizer, and sherpa-onnx reads the 650 MB int8 encoder into native heap (not mmap). Up to 1.009
`FloatingMicService.onServiceConnected` preloaded it at boot, and nothing freed it while the
always-on accessibility service kept the process alive. Fix:
- no preload in `FloatingMicService.onServiceConnected`; it still preloads on a field's focus
  (rising edge) and on Start, and the IME as before;
- `Transcriber.touch()` on every load and decode arms a timer; `unloadIfIdle(IDLE_UNLOAD_MS)`
  (5 min) frees the model, waiting for a decode in progress (it holds `lock`);
- `Transcriber.onTrimMemory(level, takeOpen)` from both services' `onTrimMemory`: levels 10-15
  (pre-Android 14) and 40+ free it if no take is open in that service and it was not used in the
  last 30 s. Level 20 (UI_HIDDEN) is ignored: the IME gets it each time the keyboard hides.
Trade-off: a take after 5 min idle (or a Transcription Mode pause over 5 min) waits for a reload
(a few seconds) before its first decode. Not changed: the model's size; a smaller model is the
user's choice (Sabich-Parakeet-110M).

**Drag crash (0.6.0 only so far):** 14 `data_app_crash` entries, 2026-10-29 14:52 to 2026-10-31
19:48, all `IllegalStateException: The specified child already has a parent` at
`FloatingMicService.place` (0.6.0 line 346, `r.addView(c, ...)` in the children loop) via
`savePosition` from `Drag.onTouch`. 0.6.0 and 1.009 both call `r.removeAllViews()` first and no
child is listed twice, so why a child kept a parent is not established. 1.010 detaches each child
from whatever parent it has before `addView`. Not reproduced; no 1.009 crash reported yet.

Verified: compiles (`compileFdroidDebugKotlin`, `compilePlayDebugKotlin`). Not run on a phone.

## Model freed while the phone sleeps (1.011 hotfix, 2026-10-31)

Follow-up to "Model memory and the drag crash guard" (1.010). Measured on Hannah's Pixel 11 with
1.010 (the session managing her phone, `dumpsys meminfo`): just after install, Native Heap PSS
4.8 MB, TOTAL PSS 23.7 MB (no boot preload: works). About 8 minutes later, the same process
(started 21:05:56) had Native Heap PSS 697,612 KB while dozing, screen off, no field focused and
no take. So the model had loaded (most likely a field's focus, which preloads) and was not freed.

Cause (I, from the code): the 1.010 idle timer is a `ScheduledExecutorService`, whose delays run
on `System.nanoTime` (CLOCK_MONOTONIC), which stops while the CPU is suspended. On a dozing phone
its 5 minutes count only awake time. `onTrimMemory` comes only under memory pressure, which a
12 GB phone with free RAM doesn't send. Released from `hotfix/android-1.011` off `android-v1.010`
(Daniel's stability release, same scope); `main` takes the same commit.

Fix:
- `Transcriber.onScreenOff(takeOpen)`, from an `ACTION_SCREEN_OFF` receiver in both
  `FloatingMicService` (registered in `onServiceConnected`) and `VoiceImeService` (`onCreate`):
  frees the model at once unless that service has a take open; a decode in progress finishes
  first (the free waits for `lock`).
- `Transcriber.checkIdle()` at the top of `FloatingMicService.onAccessibilityEvent` (no take
  open): frees the model if `IDLE_UNLOAD_MS` has passed on `elapsedRealtime` (counts sleep). The
  timer stays as a third path.
- All frees go through `freeInBackground` (one thread at a time). Loads and frees are logged:
  `adb logcat -s HebrishModel` shows `model loaded (<dir>, <ms> ms)` and
  `model freed (<why>, unused <s> s)`.

Verified: compiles (`compileFdroidDebugKotlin`, `compilePlayDebugKotlin`). Not run on a phone.

## Not yet verified (as of 2026-10-20)

- Robustness pass (2026-10-30) on a device: Try it with no model (Open Models, then back) and
  after a failed load (Try again); the settings buttons on a phone missing a screen; storage full
  during a Transcription Mode take; Use this model while a take is still decoding.
- Overlapping takes (B-43a) on a device: floating mic and keyboard, tap during "transcribing",
  texts in order, type-as-you-go on and off, switching back after the last take lands.
- Paragraphs setting (B-44a) on a device: the download and its progress, the model's latency and
  memory on a phone, ORT Java sharing `libonnxruntime.so` with sherpa-onnx in one process (two ORT
  environments' worth of callers; expected to work, (I)), re-flow after switching, the edited-text
  rule, the fallback when offline.
- Transcription Mode (B-41a, B-42a) on a device: a long take with the screen off and in another app
  (background on), the notification's Pause/Stop and chronometer, a long take with the screen on, Bluetooth mic switch
  mid-recording, pause on leaving the screen, the leftover after force-stopping the app, the
  transcription of a 30+ minute file (memory, time), the meter's zones on a real mic.

- 0.9.0 on a device: reading and adding to the system personal dictionary with the voice
  keyboard enabled but another keyboard in use (floating mic); a word added in HeliBoard or Gboard
  showing up in Hebrish; dictionary corrections in a take from the keyboard, floating mic and Try it.

- 0.8.2 on a device: seams in a long take with mid-sentence pauses (keyboard, floating mic, Type
  as you go on and off), the held "." at Stop, no double or missing spaces around a held stop in
  WhatsApp and Gmail, the wait after Stop with context (`wait_s`, `context_s` in the export).

- 0.8.1 on a device: a row per take from the keyboard, floating mic and Try it; the export to
  Google Drive through the picker; the CSV opening in Sheets with commas, quotes and line breaks
  intact; `load_s` on the first take after a restart.

- Channels / targetSdk 36 on a device: the disclosure (decline leaves settings closed, accept
  opens them and isn't shown again), Back closing the side menu on Android 13+, the IME's Back
  ("switch keyboard") on Android 16, the play build's battery list; an install with a shared model
  folder updating to 0.8.0 (copied back, or re-downloaded?); the keyboard in a password field
  (message shown, no auto-start, mic does nothing).


- 1.008 on a device: the keyboard's source chip (idle switch, mid-take switch with a Bluetooth
  headset, headset connecting while the keyboard is up), and whether the floating mic's chip now
  switches on the first tap while a Bluetooth link is opening.

- 0.7.2 on a device: the bar order on both edges, the chip's width with a long headset name,
  switching Bluetooth ↔ internal mid-take (does the SCO link come up fast enough that the first
  second after the switch isn't lost?).

- 0.7.0 on a device: Sabich-Parakeet-110M download and speed on a phone, the line/variant list, greyed variants, the tiers rendering, a pre-0.7.0
  install keeping its selected model after the switch to catalogue v2.

- 0.4.0 on a device: the floating mic in ChatGPT and other Compose apps, segment cuts and joins, the trim on quiet speakers, the Stop-to-text time,
  the download queue, the new screens, Insert after a missed field, `fdroidrepos://` opening
  F-Droid.

- 0.6.0 on a device: beeps, Bluetooth mic routing and the mic label, learned keys and broadcasts,
  the retake flash and spin, placeholder replacement in WhatsApp, the setup checklist (does
  `ACTION_AUTO_REVOKE_PERMISSIONS` open the right page on OxygenOS?), the side menu, the model cards,
  the new keyboard layout (height on a small phone), an upgrade from 0.5.0 keeping its model.

- The floating mic (0.3.0) on any device: recording from the service, insertion in Gmail,
  WhatsApp, Chrome and a Compose app, the paste fallback, drag and snap, rotation.

- The update flow and the model picker on a device; the remote catalogue fetch.
- Back with gesture navigation; `switchInputMethod(id)` on OxygenOS; pause/resume on device.
- No on-device run has been recorded yet: model load time, RAM, and transcription speed
  on the Nord 3.
- The HeliBoard mic key landing on this IME.

## Display name: Hebrish (0.1.2, 2026-10-19)

User-facing name is **Hebrish** so app search finds it; everything that identifies the install keeps `parlance`. Android: `app_name`, `ime_name` and every other user-visible string in `strings.xml` (not `url_source`); the package `com.danielrosehill.parlance` and the IME component were left unchanged so an enabled keyboard stayed enabled. Superseded by the next section.

## Identifiers: Hebrish (0.2.0, decided 2026-10-19)

Reverses the decision above: every identifier is now Hebrish, for clarity, done the day 0.1.2
shipped while installs were near zero.

- `applicationId` and `namespace`: `app.hebrish.dictation` (was `com.danielrosehill.parlance`);
  sources moved to `app/src/main/java/app/hebrish/dictation/`. `rootProject.name = "Hebrish"`.
- **Not an upgrade:** Android treats it as a new app; install it and enable the keyboard. The
  0.1.x install (`com.danielrosehill.parlance`) is now Parlance, a separate general-purpose app
  re-created 2026-10-19 in `danielrosehill/Parlance-Dictation` that keeps the old identifiers;
  Parlance 0.2.0 updates it in place, and both apps can be installed together. App-private data (prefs, a model kept in app storage) does
  not carry over; a model in a user-chosen shared folder does, because the folder is named after
  the model repo (`ModelStore.sharedFolder`), not the app.
- Same signing key as 0.1.x (nothing depends on it, since the package changed).
- `VoiceImeService` return-to-keyboard fallback now prefers Hebrish Keyboard
  (`app.hebrish.keyboard`, the HeliBoard fork in `Hebrish-ASR/Hebrish-Keyboard`) before HeliBoard.
- Release APK: `Hebrish-<ver>.apk` (already so since the 0.1.2 workflow).

## Repo name: Hebrish-App (renamed 2026-10-20; Hebrish-Dictation 2026-10-19)

On 2026-10-19 the GitHub repo `Hebrish-ASR/Parlance-Dictation` was renamed to
`Hebrish-ASR/Hebrish-Dictation` (local clone moved from
`~/repos/github/audio-dictation/Parlance-Dictation` to `.../Hebrish-Dictation`). GitHub
redirects the old URLs; checked the same day that `raw.githubusercontent.com/.../main/shared/models.json`
and the release-asset download URLs still return 200 under the old name. Source links,
`catalogue_url` (both copies of `models.json`), the desktop `USER_AGENT`, About link, `.deb`
`Homepage` and Android `url_source` now use the new name. Code identifiers followed the same
day; see "Identifiers: Hebrish (0.2.0)".

**Never create a new repo named `Hebrish-ASR/Parlance-Dictation`.** Installed builds up to and
including 0.1.2 (desktop and Android) fetch the catalogue from the old-name `catalogue_url`;
a repo taking the old name kills GitHub's redirect and those installs stop seeing catalogue
updates (they fall back to the bundled copy). Old download links on other sites rely on the
same redirect.

On 2026-10-20 it was renamed again, `Hebrish-ASR/Hebrish-Dictation` → `Hebrish-ASR/Hebrish-App`, so the
repo name says what it is: the source of every Hebrish app (Android, Linux, Windows). The website, which
had been `danielrosehill/Hebrish-App`, became `danielrosehill/Hebrish-Website` (private, kept on the personal
account: Vercel Hobby cannot deploy a private org-owned repo). Local clones moved to
`.../Hebrish-App` and `.../Hebrish-Website`. Checked the same day: the old raw `shared/models.json` URL and
the old release-asset URL still return 200, so apps already installed keep their `catalogue_url`. All
references in the Hebrish repos were updated; the Hebrish-Keyboard submodule URL points at the new name.

## Model version labels: no commits in the UI (0.7.4, 2026-10-22)

Daniel: showing the commit number (and the training-run name) next to the model is "too much
information"; the UI shows only the version, e.g. "Sabich v2.0". `ModelStore.Manifest.label`
(Android, `android/core`) and `Manifest.label` (desktop, `desktop/hebrish/model_store.py`) take
the manifest's `version`, drop a leading model name (the CDN manifest for Sabich says
`"version": "Sabich v2.0"`) and show nothing for the `rev abc1234` fallback. `revision` and `run`
are still stored and used for directory names and same-weights checks; the desktop keeps them in
`Manifest.debug_label` for logs and the CLI. Compiled (`assembleDebug`) and desktop tests pass (V);
not run on a device (I).

## Plain model descriptions and What's new (unreleased, 2026-10-25)

**Plain model descriptions (unreleased, 2026-10-25).** Daniel: the Models page should be "as
friendly as possible for regular people", e.g. "base model Parakeet 0.6B v2 by NVIDIA", not
`Qwen/Qwen3-ASR-1.7B` with BF16/PyTorch/GGUF detail. Each catalogue variant now has `base_label`
("Parakeet 0.6B v2 by NVIDIA", "Nemotron Speech Streaming 0.6B by NVIDIA", "Qwen3-ASR 1.7B by
Alibaba", "Canary-Qwen 2.5B by NVIDIA", "Parakeet 110M by NVIDIA", "asr4all M/S by FUTO"), shown as
"Base model: …" under the name. `hardware`, `recommendation` and `runs_on` were rewritten in plain
words ("graphics card", "memory", "other speech software … See the model page"). The engineering
text that was there moved to a new `technical` field, shown with `base_model` (repo id) and `repo`
only under a collapsed **Technical details** link on each card. `base_model`, `repo`, `engine` and
the rest are unchanged, so downloads are unaffected. `tests/test_shared.py`
(`test_what_users_see_is_plain_language`) fails if a repo id, format or runtime name gets back into
a displayed field. The published catalogue is re-fetched by installed apps, so older builds show the
plainer `hardware`/`runs_on` text as soon as `main` has it; only builds with this change show
`base_label` and Technical details.

**What's new, baked at build time (unreleased, 2026-10-25).** Daniel: "integrate the update feed,
the changelog, into the app itself … bake in the short updates according to the build time."
`scripts/bake_updates.py` reads hebrish.app's changelog (`changelog.html` in the website checkout
next to this repo, else `https://hebrish.app/changelog`), keeps the entries dated on or before the
build date, newest first, the last 20, each as date, tag, title and the first one or two sentences
of its first bullet (at most 280 characters), and writes `shared/updates.json` plus its
byte-identical copy `desktop/hebrish/data/updates.json`. Source choice: the changelog is the only
feed with short dated entries for app releases; the site's `data/releases.json` has just the two
numbered model releases and `data/updates/` is the voice-note podcast. It is plain HTML, so the
script depends on its markup (`<article class="log">`, `<time datetime>`, `<span class="tag">`,
`<h3>`, first `<li>`); `test_bake_reads_the_changelog_markup` pins that, and the script exits with
an error if it finds no entries. `scripts/release-tag.sh` runs it before every tag and commits both
copies with the version bump (`SKIP_UPDATES_BAKE=1` to skip, e.g. offline). Write the release's own
changelog entry on the site before tagging, or the build lists only the entries before it
(release-tag.sh prints a note when the newest entry doesn't name the version).

Android: `Catalogue.Model.baseLabel` and `.technical`; `ModelsActivity.card()` shows "Base model:
…" and `technical()` adds the Technical details toggle (open cards are remembered across the
frequent `render()`s during downloads). What's new is `UpdatesActivity`, reading
`assets/updates.json` (copied from `shared/updates.json` by the gradle `copyCatalogue` task),
reached from home (More), the side menu and a button on About; a link at the bottom opens the
full changelog. Checked: `./gradlew --offline :app:compileFdroidDebugKotlin
:app:mergeFdroidDebugAssets` passes and the merged assets contain `updates.json` (V); a full
`assembleDebug` could not run on 2026-10-25 because the native (sherpa-onnx) configure step failed
on this checkout's submodule state, unrelated to this change; not run on a device (I).

**One list per platform (2026-10-31).** Daniel: "the updates should only be related to Android on
Android ... categorized according to what platform they're relevant to, that way we can build them
accordingly". Every entry on hebrish.app's changelog now carries `data-platforms` (`android`,
`desktop`, `models`, `site`; site README, `changelog.html` row; the page filters on it). A model
update the apps offer through their model update (Sabich releases) is filed under `android` and
`desktop` too, so Sabich v2.3 shows in both apps; other model news (TTS, variants not in the apps)
is `models` only and shows in neither. `bake_updates.py` now writes `shared/updates-android.json`
(`android` entries; copied into the APK as `assets/updates.json`, renamed by the gradle
`copyCatalogue` task) and `desktop/hebrish/data/updates.json` (`desktop` and `site` entries:
major site changes are shown on desktop), each with `"platform"` and per-entry `platforms`.
`shared/updates.json` is retired. An entry without the attribute falls back to its tag
(`platforms_from_tag`). Tests: `test_updates_are_well_formed[android|desktop]`,
`test_bake_keeps_each_apps_own_entries`.

**Button bindings: on/off, Clear all, saved sets (unreleased, 2026-10-25).** Daniel: the floating
mic grabbing bound keys all the time is inconvenient when the same Bluetooth remote is wanted for
something else; asked for a way to switch the bindings off without losing them, a clear button,
and saving/restoring them (named profiles acceptable if that is the simplest). Settings → Sound,
microphone and buttons → Buttons now has (F-Droid build only; the Play build has no hardware keys):

- **Use bound buttons** (`Prefs.keysOn`, key `key_bindings_on`, on by default). Off:
  `FloatingMicService.onKeyEvent` returns false for every key, so the remote reaches other apps;
  the bindings stay stored. Learn still works while off (the key is learned, then not taken).
- **Clear all** (`Remote.clearAll`): unbinds every action and ends learning; saved sets are kept.
- **Saved sets** (`Remote.saveProfile`/`useProfile`/`deleteProfile`): type a name, Save stores the
  current bindings; each set is listed with its keys and **Use** (replaces the current bindings;
  actions the set doesn't bind are cleared) and **Delete**. Same name overwrites. One prefs key,
  `key_profiles`, JSON `{name: {ACTION: keyCode}}`, on the phone only, so a later settings backup
  or cloud sync only has to carry that key and `key_<ACTION>`.

Both new keys start with `key_`, so `ControlsActivity`'s preference listener re-renders on them.
Checked: `./gradlew :app:compileFdroidDebugKotlin :app:compilePlayDebugKotlin` passes (V, JDK 21);
not run on a device (I).
