# Backlog

Last updated 2026-10-22. Status words: `idea`, `planned`, `in progress`, `done (unreleased)`,
`released <version>`. Work is queued in **one sprint per platform** (desktop = Ubuntu + Windows,
which share `desktop/`; Android). A sprint ends with a release. Parity is the aim (decision
D-2026-10-22-05): an item done on one platform gets a matching item in the other sprint, unless
it makes no sense there. Agents add to sprints with the `queue-sprint` skill.

## Sprint: desktop (Ubuntu + Windows), toward 0.7.0

| Id | Item | Status |
| --- | --- | --- |
| B-1 | **Insert-as-you-go presets.** Fast ~5 s, Normal ~7 s (new default, was ~10 s), Relaxed ~10 s, Off, Custom (3–60 s). Existing installs at the old 10 s move to 7 once. R-2026-10-22-1; D-2026-10-22-02, -03 | done (unreleased) |
| B-2 | **Stop and send.** An optional action key: stop, wait for the last words to be pasted, then press the send key (Enter by default, configurable). R-2026-10-22-2; D-2026-10-22-04. Windows tested in CI only | done (unreleased) |
| B-6 | **Character voices.** Voice feedback in Herman's, Corn's or Hilbert's voice (Settings → Sounds → Voice), replacing the stock TTS voice. R-2026-10-22-5; D-2026-10-22-07 | done (unreleased) |
| B-7 | **Prompts no longer end up in the transcript.** The mic ignores input while a beep or spoken prompt plays (start, retake, resume), plus 150 ms. R-2026-10-22-6; D-2026-10-22-08 | done (unreleased) |
| B-8 | **Tray menu icons.** Icons beside the tray menu entries (Start dictation, Show overlay, Show window, …) so the menu reads at a glance. R-2026-10-22-8 | planned |
| B-12 | **Shakshuka streaming.** The streaming engine (sherpa-onnx `OnlineRecognizer`): with Shakshuka, words are inserted as you speak (about a second behind), append-only. Shakshuka is the recommended model on desktop (`recommended_by_platform`). At release: change the chooser's "not in the apps yet" note here and on hebrish.app together. R-2026-10-22-12; D-2026-10-22-12 | done (unreleased) |
| B-14 | **Text box clears for each take.** The Dictate tab's box starts empty when a take starts (Settings: "Start the text box empty for each take", on by default); earlier takes are in History. R-2026-10-22-13; D-2026-10-22-13 | done (unreleased) |
| B-15 | **Dictation history.** Every transcript kept on this computer (`history.db`, SQLite), on by default and unlimited, including File-tab transcripts. History tab: keyword search (prefixes, best match first), word counts for today / last 7 days / all time, where it is stored (path, size, Open folder), Export (JSON Lines), Correct (keeps the model's original text) and Delete. Optional: keep each take's audio. Installs from before 0.7.0 get history switched on once. R-2026-10-22-14, -16, -17, -21; D-2026-10-22-13 | done (unreleased) |
| B-16 | **Semantic search.** Find dictations by meaning, not only by words. Design: a small multilingual text-embedding model, downloaded on demand like the speech models (catalogue + CDN); vectors stored in `history.db`, computed in the background; results ranked by a mix of meaning and keyword match. Needs onnxruntime (Python) and a tokenizer in the .deb and the Windows zip. R-2026-10-22-15 | planned |
| B-17 | **Back up history to Google Drive.** Opt-in: sign in with Google (desktop OAuth, `drive.file` scope, so the app sees only its own files), then upload a consistent snapshot of `history.db` (SQLite backup API) and the kept audio to a Hebrish folder, on a schedule and on demand, with restore. Needs a Google Cloud OAuth client for Hebrish. R-2026-10-22-18 | planned |
| B-18 | **Accounts, invite-only.** An optional Hebrish account (sign-in via hebrish.app), allowed only for invited addresses; at first the list holds only Daniel. Without an account nothing changes. The account is the anchor for later cross-device sync (I-7). All platforms; needs a small server side on hebrish.app. R-2026-10-22-20; D-2026-10-22-14 | planned |
| B-22 | **Shortcut settings, basic and advanced.** Basic: a laptop-friendly preset (Enter / Escape style). Advanced: every action (start/stop tap-tap, push-to-talk, cancel, retake, eject, escape) can be bound to any key, F13 and up included, so a macro pad or a USB HID button can drive it. No action hard-wired to Escape. R-2026-10-22-23; D-2026-10-22-16 | planned |
| B-23 | **Output mode from the tray and a shortcut.** The output-mode setting (clipboard + type, clipboard only, type only) gets a tray-menu entry and bindable shortcuts to switch or cycle it, with a notification of the new mode. R-2026-10-22-24; D-2026-10-22-15 | planned |
| B-24 | **"Download models" setup.** First run and the model screen offer models to download rather than one to choose: a streaming model (Shakshuka) for dictation and a non-streaming one (Sabich) for recordings, with recommendations for the computer's hardware (see I-5). R-2026-10-22-26 | planned |
| B-25 | **Long-form mode.** A text-editor-like module for long dictation: record up to ~90 minutes (chunked, each chunk saved to disk as it is captured, VAD and downsampling during capture) or pick a file; transcribe with the non-streaming model; autosave at once; then tidy and save. Builds on the Transcribe tab and History. R-2026-10-22-27 | planned |
| B-26 | **Retention.** Audio of a take whose transcription failed is kept for retry (the last three); otherwise audio is kept only with `keep_audio` on. Settings to truncate the history (by age or count; default stays unlimited, D-2026-10-22-13). R-2026-10-22-30; D-2026-10-22-17 | planned |
| B-5 | **Release desktop 0.7.0** with the items above (B-16 to B-18 can move to the next release if 0.7.0 is otherwise ready) | planned |

## Sprint: Android

| Id | Item | Status |
| --- | --- | --- |
| B-9 | **Floating mic: horizontal offset.** Today the floating mic can be moved up and down the screen edge. Add a horizontal offset: by default the mic sits a little in from the screen edge (hard to reach right at the edge), and the user adjusts from there: negative puts it flush with the edge, positive moves it further in. Applies on whichever side it is snapped to. R-2026-10-22-9 | planned |
| B-10 | **Design pass.** The app is taking shape, and splitting settings over many pages works well, but the screens need visual design: consistent cards, spacing, headers and icons, using the brand standard (Hebrish-Mgmt `brand/`). R-2026-10-22-7 | planned |
| B-3 | **Interval presets.** Android's *Type as you go* is on/off with a fixed interval; give it the same Fast / Normal / Relaxed / Custom choice (parity with B-1) | planned |
| B-4 | **Stop and send.** The voice keyboard could offer a stop-and-send control that stops, inserts the last text, then submits the field (IME action or Enter). Needs a UI decision: a long-press on the mic, or its own button (parity with B-2) | planned |
| B-13 | **Shakshuka streaming on Android** (parity with B-12): `sherpa_online_transducer` in `Catalogue.SUPPORTED_ENGINES`, an `OnlineRecognizer` feeding the composing text, whole words only. Then drop the exception in `desktop/tests/test_shared.py` | planned |
| B-11 | **Character voices and cue muting.** Android has beeps but no spoken prompts: ship the same Herman / Corn / Hilbert WAVs (`desktop/hebrish/data/voice/`), and check whether Android beeps also bleed into the recording (parity with B-6, B-7) | planned |
| B-19 | **Dictation history on Android** (parity with B-14, B-15): keep every transcript (Room/SQLite with FTS), a History screen with search and word counts (today / 7 days / all time), Correct and Delete, export, and where it is stored. Check whether the Try screen's text box should also clear per take. R-2026-10-22-14, -16 | planned |
| B-20 | **Google Drive backup on Android** (parity with B-17) | planned |
| B-21 | **Accounts on Android** (parity with B-18): sign in to an invited account | planned |
| B-27 | **One headset button.** Bind a single Bluetooth headset button (media button) to start and stop dictation, tap-tap. Test with a Yealink headset. R-2026-10-22-33; D-2026-10-22-16 | planned |
| B-28 | **Retention on Android** (parity with B-26): keep only failed takes' audio for retry; history truncation settings, with B-19. R-2026-10-22-30 | planned |

## Ideas for future versions

Worth doing, not scheduled. Ordered roughly by value.

| Id | Idea | Notes | Status |
| --- | --- | --- | --- |
| I-1 | **"Still transcribing" indicator during a take.** After you stop, the tray and overlay already show *Transcribing…*. While you are still talking with insert-as-you-go on, though, nothing shows that a piece is still being decoded. Add a pending mark to the tray icon and the overlay whenever the decode queue isn't empty. R-2026-10-22-3 | All platforms | idea |
| I-2 | **Guard a plain Enter.** Catch an ordinary Enter pressed while text is still pending. Options: (a) beep and flash the overlay, a warning only, because the Enter has already reached the app; (b) hold the keyboard only while text is pending (usually under 2 s), keep the Enter, paste, then replay it. (b) is the only option that saves a reflex Enter, but a hang would leave the keyboard held, so it needs a hard timeout and would be opt-in. On Linux, (b) needs exclusive access to the keyboard device (EVIOCGRAB); on Windows, a low-level keyboard hook. R-2026-10-22-2 | Ubuntu, Windows; Android differs (the IME owns its Enter) | idea |
| I-3 | **Mid-sentence continuation.** When the last text the app inserted didn't end in `.`, `?` or `!`, and the new take starts within ~2 minutes, lowercase the new take's first letter (keeping "I", "I'm" and all-caps acronyms). Within one insert-as-you-go take this is reliable, because the pieces are known to be continuous; across takes the cursor may have moved to another window, hence the time limit and an off switch. The app can't read the text field (not possible on Wayland), so it goes by its own last output. R-2026-10-22-4 | All platforms | idea |
| I-4 | **Live streaming with corrections.** Words appear as you speak (Shakshuka, Nemotron streaming, about 560 ms) and each finished phrase is decoded again by the offline model, which corrects the tail where the two differ, as Deepgram does. Modes: revise, append-only, pieces (today). Shakshuka's streaming accuracy is not measured yet. [Research](../research/streaming-revision/README.md). R-2026-10-22-11 | All platforms | idea |
| I-5 | **A model per mode.** Dictation uses Shakshuka (streaming) while the Transcribe tab uses Sabich for recordings, each chosen separately, so neither mode needs a switch. Costs a second loaded model (~1.5 GB RAM) or a reload when changing tab. R-2026-10-22-12 | Desktop | idea |
| I-6 | **Fewer models.** Narrow the catalogue to a few models the project stands behind, e.g. not both a Parakeet and a Qwen version of Sabich. Needs results on one test-set revision first. R-2026-10-22-12; D-2026-10-22-12 | All, and hebrish.app | idea |
| I-7 | **Sync history across devices.** Your history follows your account across Android, Ubuntu and Windows (merging by each row's `uid`). Deferred until accounts (B-18) exist: it needs server storage and account creation. R-2026-10-22-19; D-2026-10-22-14 | All platforms | idea |
| I-8 | **Clipboard race guard.** If the clipboard changed while a take was being transcribed, don't overwrite it: keep the text in History and notify ("transcription held back"). R-2026-10-22-25 | Desktop | idea |
| I-9 | **Long form to Google Docs.** Name a long-form transcription and create a Google Doc from it. R-2026-10-22-28 | Desktop | idea |
| I-10 | **Long form on Android** (parity with B-25). First check that chunked local storage works without the all-files permission (a Google Play blocker). R-2026-10-22-27, -35 | Android | idea |
| I-11 | **VAD toggle.** Whether voice activity detection should be a user toggle on desktop, and whether Android can have it; speed of inference comes first. R-2026-10-22-29 | All platforms | idea |
| I-12 | **Report a word.** Send a misrecognized word (and a note) from the app; reports become a corrections dataset that feeds the training recordings. Needs a small server side on hebrish.app. R-2026-10-22-31 | All platforms | idea |
| I-13 | **Personal dictionary.** Use Android's personal dictionary in inference (if the engine can take hints), offer one on desktop, and sync it with accounts (B-18, I-7). R-2026-10-22-32 | All platforms | idea |
