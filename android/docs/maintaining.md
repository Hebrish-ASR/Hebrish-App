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
  whole field, so it builds `before + [space] + text + after` from `text` and
  `textSelectionStart/End` (an empty field's hint is excluded via `isShowingHintText`), then
  `ACTION_SET_SELECTION` to the end of the insert. When the cursor lies past the reported text
  (0.7.6), PASTE goes first so nothing the app doesn't report is deleted. Fallback: clipboard + `ACTION_PASTE`; the
  old clip is not restored because a background service can't read the clipboard on Android
  10+. Password nodes are skipped.
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

Text joins: segment texts are joined with a space. A cut lands in a pause, which is usually a
sentence or clause boundary, so the model's per-segment casing and full stop mostly fit; a
mid-sentence pause can produce an extra full stop and capital. *Type as you go*
(`Prefs.typeAsYouGo`) inserts each segment when decoded (keyboard: `commitText`; floating mic:
`deliver` into the take's field), and Discard then drops only what isn't in yet.

Considered and not done: NNAPI (`provider = "nnapi"`; the AAR's ONNX Runtime has the NNAPI EP)
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

## Version and tag (2026-10-21)

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
- Tap the chip → `switchMic()` → `Mic.toggle`: from the phone mic to `Mic.AUTO` (Bluetooth first;
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

## Not yet verified (as of 2026-10-20)

- Channels / targetSdk 36 on a device: the disclosure (decline leaves settings closed, accept
  opens them and isn't shown again), Back closing the side menu on Android 13+, the IME's Back
  ("switch keyboard") on Android 16, the play build's battery list; an install with a shared model
  folder updating to 0.8.0 (copied back, or re-downloaded?); the keyboard in a password field
  (message shown, no auto-start, mic does nothing).


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
