# Decision log

Newest first. Append-only: a decision that is later reversed stays here, and the new one says
which decision it supersedes. Ids are `D-<date>-<nn>`. Agents add entries with the
`log-decision` skill (plugin `hebrish-maintainers`, marketplace Hebrish-ASR/Hebrish-Claude-Plugins).

Each entry: **Decision**, **Why**, **Alternatives** (what was considered and not chosen),
**By** (who decided), and links to the request, backlog item or commit where they exist.

---

### D-2026-10-31-01: Press Enter after silence is opt-in, 8 s, once per pause, only while recording

- **Decision:** Desktop gets *Press Enter after silence* (B-72), off by default, delay 8 s (2-60 s).
  It presses the configured Send key (`send_chord`, Enter by default) through the paste inserter,
  at most once per silence and only when text was typed since the last Enter; new speech resets
  it; never while paused or after Stop; silence is voice detection's (Silero, else the energy rule).
- **Why:** Daniel, 2026-10-31: dictating into Claude he forgets to hit Enter, but it must not fire
  on a thinking pause. Off by default because an Enter nobody expected in another app (a terminal,
  a mail client) can run or send something; the Send key rather than a fixed Enter so apps where
  Enter makes a new line work as with Stop and send.
- **Alternatives:** on by default (rejected: the cost of a stray Enter); firing after Stop as well
  (Stop and send covers that); a fixed Enter regardless of the Send key.
- **By:** Daniel (the feature, 8 s, the once-per-batch rules); agent (off by default, Send key).
- **Links:** R-2026-10-31-1; backlog B-72, B-72a; `desktop/docs/maintaining.md`, "Press Enter after silence".

### D-2026-10-30-01: Two clean-up models, stock S1-mini by Superwhisper the default; Q4_K_M with llama.cpp built in on Android

- **Decision:** The clean-up add-on offers two models in both apps: stock **S1-mini by
  Superwhisper** (default; Superwhisper's own `s1-mini-q4_k_m.gguf`, pinned by commit) and Daniel's
  fine-tune **S1-ASR-Cleanup** (marked experimental). Android gets clean-up (B-40a) with Q4_K_M
  files and llama.cpp b11982 compiled into the APK from a submodule, offered only on CPUs with the
  ARMv8.2 dot-product instructions. The Android Models screen gains a Post-processing section
  (paragraph model and clean-up models), as desktop's Models > Utilities.
- **Why:** Daniel, 2026-10-30: "use the stock s1 for now until my fine tune is better validated",
  offer both, on desktop too, and quantise for phones; no benchmark for this step. The only
  comparison so far (proof-of-concept LoRA, 9 held-out items: 0.898 vs stock 0.891) is too small to
  rank them, and v1.0 is unbenchmarked. Android can't run a downloaded executable and F-Droid needs
  native code built from source, so desktop's downloaded `llama-server` doesn't carry over.
- **Alternatives:** fine-tune only (as desktop 1.013); stock only; re-hosting a stock Q8_0
  (Superwhisper publishes only F16 and Q4_K_M; their card measures accuracy on Q4_K_M); Q4_0 for
  phones (dropped words on the one sanity sentence); llama.cpp's CPU-variant dynamic backends
  (needs shared libraries, clashes with the static sherpa-onnx build).
- **By:** Daniel (both models, stock default, Android and desktop, no scoring); agent (files,
  runtime, dot-product gate, Android context size).
- **Links:** backlog B-40a; `android/docs/maintaining.md` "Clean up: S1-mini on the phone";
  `desktop/docs/maintaining.md` "Clean-up model".

### D-2026-10-29-03: The clean-up model (S1-mini by Superwhisper fine-tune) runs on a downloaded llama-server, in Transcription Mode, and replaces Paragraphs while on

- **Decision:** S1-ASR-Cleanup (a fine-tune of S1-mini by Superwhisper) is an optional desktop
  add-on in Models > Utilities, off by default. It runs on a pinned llama.cpp CPU build of
  `llama-server` that is downloaded with the model and started as a local child process. It
  cleans each finished Transcription Mode transcript; while it is on, its own paragraphs replace
  the Paragraphs setting (greyed out), which applies again only when clean-up fails. Any failure
  keeps the text as transcribed.
- **Why:** Daniel asked for it as a downloadable accessory model, desktop only (2026-10-29). The
  .deb (`uv pip install --target`) and the Windows PyInstaller zip would have to compile
  llama-cpp-python into every build (no PyPI wheels) for a feature most users never download; the
  stock llama.cpp release binaries are about 23 MB, checked by SHA-256, and add nothing to an
  install that doesn't use them. The model inserts paragraph breaks itself and the paragraph model
  re-flows all whitespace, so running both would undo one or the other.
- **Alternatives:** llama-cpp-python bundled or optional (build cost, size); running the paragraph
  model after clean-up (undoes the model's breaks); applying clean-up to Voice Typing takes
  inserted in one go and Paste last as the research plan lists (left for Daniel: seconds of delay
  before every paste).
- **By:** Daniel (add-on, desktop only, mobile later: B-40a); agent (runtime, order, Transcription
  Mode only, open to Daniel's review). B-40; [research](../research/post-processing/README.md);
  `desktop/docs/maintaining.md`, "Clean-up model".

---

### D-2026-10-29-02: Silero VAD is bundled and on by default; TEN VAD not offered

- **Decision:** Silero VAD ships inside the app (0.6 MB) and is used whenever Voice detection is
  on, which is the default; "Use it for voice detection" on Models > Add-ons turns it off. TEN VAD
  is not offered.
- **Why:** Daniel: "VAD should be enabled by default ... I can pause as long as I want." It costs
  about 9 ms per second of audio on the desktop CPU, small next to decoding, and long pauses and
  silent takes are then reliably not decoded even in a noisy room. TEN VAD measured about the same
  speed, cleaner on silence but much worse with background noise (docs/maintaining.md, "Silero
  VAD"), and its licence adds a no-competing-with-Agora condition, a risk for a speech-to-text
  app that may be licensed commercially.
- **Alternatives:** Silero as a download (D-2026-10-29-01, same day: an extra step for a 0.6 MB
  file); both VADs as a choice (TEN's licence and the noise result).
- **By:** Daniel (on by default); agent (TEN not offered, open to Daniel's review). R-2026-10-29-2.

### D-2026-10-29-01: Silero VAD is an optional add-on for voice detection (supersedes the 2026-10-21 "not added")

- **Decision:** Silero VAD (sherpa-onnx's `silero_vad.onnx`, 643,854 bytes, MIT) is offered as a
  download on a new Models > Add-ons tab, next to the paragraph model. Downloaded and with "Use it
  for voice detection" on (`vad_silero`, default on), it decides which frames are speech for
  Voice detection: skipping silent takes and shortening long silences. Live cut points stay on the
  energy rule. Android gets the same model through the same sherpa-onnx API (B-71a).
- **Why:** Daniel: "Can't hurt to have it as an option that users can use." The energy rule
  treats steady noise (fans, cafés) as speech; Silero does not (measured 2026-10-29: 5 s of
  noise at -34 dBFS, 0 speech frames with Silero, 145 with energy). About 10 ms per second of
  audio on the CPU.
- **Alternatives:** Keep energy only (the 2026-10-21 call: one more download, cut points already
  at 1% WER; answered by making it optional and leaving the cut points alone). TEN VAD (also in
  sherpa-onnx; not chosen: Silero is the one Daniel asked for, and its MIT licence is plain).
- **By:** Daniel. Request R-2026-10-29-2, backlog B-71, B-71a.

### D-2026-10-28-01: History stays on SQLite; semantic search adds sqlite-vec to the same file

- **Decision:** `history.db` stays SQLite (FTS5 keyword search, WAL journaling from 1.009, B-66) on
  desktop and Android. Semantic search (B-16, B-16a) stores its vectors in the same database through
  the sqlite-vec extension, with embeddings computed on the device by a downloadable model. Parquet
  is an export format (B-67), not storage.
- **Why:** Daniel asked (2026-10-28) whether a document database such as MongoDB, or another
  document-native store with semantic search, would be more robust. The history is one user's
  rows with a fixed schema on one device; SQLite is transactional, needs no server, already holds
  the FTS index, stores JSON columns (`decode`), and is what Android uses, so parity holds. Scale
  check (2026-10-28, synthetic 200,000 rows, 46 M characters, 170 MB): search 219 ms, stats 126 ms,
  insert 0.2 ms.
- **Alternatives:** MongoDB (needs a server); PoloDB, TinyDB, UnQLite (document stores, no vector
  search); LanceDB and Milvus Lite (embedded vector stores, not document stores, no Android, pyarrow
  weight for LanceDB; Milvus Lite allows one process per data directory); DuckDB with its vector
  extension (experimental; better as an export and analysis tool); Couchbase Lite (document store
  with vector search, but no official Python SDK for the desktop app; vector search edition terms
  unverified). Comparison done 2026-10-28 from web sources; sqlite-vec's current release status
  was not confirmed and is to be checked when B-16 starts.
- **By:** Daniel, on the agent's recommendation. Links: R-2026-10-28-5, R-2026-10-28-6, B-16, B-16a,
  B-66, B-67.

### D-2026-10-27-03: The dictation mode is Voice Typing; the desktop UI takes the hebrish.app brand

- **Decision:** The desktop's Dictate tab and mode are **Voice Typing** in the UI (config keys and
  internal names unchanged). The window uses the brand standard (`Hebrish-Mgmt/brand/`): accent
  green, paper header with the mark and Fraunces, one gold mark, line icons drawn for the app;
  record red and busy amber stay. Tagline: "Voice typing that gets the Hebrew words right."
  Diagnostics and About move from the tab bar to the header.
- **Why:** Daniel, 2026-10-27: "dictation" carries the old boss-and-transcriptionist picture, and
  the other pole, Silicon Valley hype ("ten times as fast", vibe coding by voice), is just as
  wrong; the app should look slick and easy, in the website's voice. The tab bar also overflowed.
- **Alternatives:** Keeping "Dictate"; a hype-led tagline. Bundling Inter (about 2.4 MB): not done,
  the system sans stays.
- **By:** Daniel (name and direction); the look by the agent, from the brand standard.
- R-2026-10-27-2, B-51.

### D-2026-10-27-02: Enter guard: late words are kept for Paste by default; holding the Enter is opt-in

- **Decision:** When the user's send key (`send_chord`, Enter by default) is pressed after Stop
  and before the take's last words are pasted, those words are not pasted into whatever comes
  next: they go on the clipboard and the overlay shows "Late words · Paste" (setting
  `enter_guard` = `late`, default). `hold` (opt-in) also holds that Enter until the words are in,
  then replays it, for at most 4 s (`ENTER_HOLD_S`); on Linux by grabbing the keyboards with an
  Enter key and forwarding every other key through a passthrough uinput device, on Windows by
  suppressing the hook event. `off` is the behaviour before 1.007.
- **Why:** Daniel, 2026-10-27 (and R-2026-10-22-2): in Claude Code a reflex Enter submits without
  the last words, and they then land in the next prompt where they don't belong. Keeping them
  out needs no keyboard grab, so it can be the default; saving the reflex Enter needs one, which
  Daniel called "maybe risky", so it is opt-in and capped.
- **Alternatives:** A warning only (I-2 option a): the words still land in the wrong place.
  Hold as the default: a hung grab would take the keyboard.
- **By:** Daniel (asked for both); default and cap by the agent.
- R-2026-10-27-1, B-50 (replaces I-2).

### D-2026-10-27-01: Repeated words and ellipses are cut in the disfluency chop (both apps)

- **Decision:** The chop (`shared/disfluencies.md`) now also cuts a word repeated straight away
  ("wanted, wanted" → "wanted"; runs of three or more too), a two- or three-word phrase said
  again ("it was, it was" → "it was"), a repeat across an insert-as-you-go seam, and turns the
  ellipsis the models write for a trailing-off thought into a space or a full stop. Words said
  twice on purpose ("really, really", "had had", "yalla yalla") are kept twice, never more;
  numbers are never cut. Always on, no setting, like the filler rules.
- **Why:** Daniel, 2026-10-27: stutters and false starts come through ("could we change, change,
  change? change the dataset") and repetition is more often unintended than deliberate. The
  models write what was said; the text layer works with them. Part of D-2026-10-24-04 left
  repeated words to the models; this supersedes that part.
- **Alternatives:** A repetition penalty at decoding: sherpa-onnx's transducer greedy/beam search
  has none, and the repeats are faithful to the audio, so the decoder would need to know intent.
  The lasting fix is training data whose transcripts drop false starts (the disfluency dataset).
- **By:** Daniel (ask); rules by the agent.
- R-2026-10-27-3, B-52.

### D-2026-10-24-09: Transcription Mode offers Paragraphs: None, Time-based or Paragraph model

- **Decision:** Transcription Mode (desktop and Android) gets a Paragraphs setting: *None* (one
  block), *Time-based* (the existing ~30 s split) or *Paragraph model* (the MiniLM-L12 break
  classifier, downloaded on demand from the CDN, run once on the finished transcript). Spec:
  `shared/paragraphs.md`. Dictation is unchanged. B-44, B-44a.
- **Why:** Daniel, 2026-10-24: "I don't like the line split … didn't we train up a small paragraph
  classifier? … we could have options for to use the classifier model, or to use Time Based, or None
  so the user has the option".
- **Default:** Paragraph model when installed, else Time-based (agent's choice; Daniel named none).
- **Supersedes:** the app part of D-2026-10-24-08 for Transcription Mode only. Still in force: no
  paragraph passages in Hebrish ASR training (ASR-Training `ISOLATED_TAGS`); the dataset stays
  `danielrosehill/Paragraph-Dictation-Passages`.
- **Note:** the classifier is text-only and trained on synthetic memos (break F1 0.85 on 26 held-out
  memos); an audio-aware model is the separate project's next step and could replace it later.
- **By:** Daniel.

### D-2026-10-24-08: Paragraph inference is not part of Hebrish

- **Decision:** No paragraph step in the apps. B-40 keeps only S1-mini by Superwhisper (desktop);
  B-40a (paragraphs on Android) is dropped, and the shared spec and CDN copy made for it the same day
  were removed. Paragraph inference continues as its own project (ASR-Paragraph-Breaks), with its own
  dictated-passage dataset `danielrosehill/Paragraph-Dictation-Passages`, which no Hebrish model trains on
  (ASR-Training `cs_lib.ISOLATED_TAGS`).
- **Why:** Daniel: it "requires a different architecture", and the passages should not "corrupt the
  training data with something that can't actually work". He wants to train a dedicated model on that
  data extensively.
- **Alternatives:** Shipping the text-only r5b break classifier (break F1 0.85 on synthetic memos) as
  an opt-in step on all platforms; started, then stopped before anything was released.
- **Not needed:** a Sabich retrain. The ASR never saw breaks: the 3 passage takes (44 s, 2026-10-21)
  have one-line transcripts, and at most r9 (Release v2) included them among about 714 minutes.
- **By:** Daniel. Supersedes the paragraph part of R-2026-10-24-3 / -4 and B-40.

### D-2026-10-24-07: Android records Transcription Mode in the background, opt-in from Setup

- **Decision:** Android gets a `microphone` foreground service for Transcription Mode (B-42a), with
  the permissions it needs (`FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_MICROPHONE`,
  `POST_NOTIFICATIONS`). It is optional: an optional Setup step and a switch on the screen turn it
  on; off, Transcription Mode records only while its screen is open (D-2026-10-24-06).
- **Why:** Daniel, 2026-10-24: "we should add into the setup on Android the background recording
  … it can be optional: if you want to use it for this mode, then this permission is needed."
- **Alternatives:** foreground-only recording (D-2026-10-24-06's first answer); background on for
  everyone (asks every user for notifications they may never need).
- **By:** Daniel. Supersedes the Android part of D-2026-10-24-06.

### D-2026-10-24-06: Transcription Mode keeps its recording on disk until it is transcribed

- **Decision:** Transcription Mode (B-41, B-41a) writes each recording to a WAV in the app's own
  data folder as it records, and deletes it once its transcript is in History. A recording that
  was not transcribed (the app closed or crashed, the transcription failed or was cancelled) stays
  and is offered again until it is transcribed or deleted. This is a bounded exception to
  D-2026-10-22-20 (no audio kept), like D-2026-10-22-17's retry buffer: audio exists only until
  its text does. On Android it records only while its screen is open (I-15 for the background).
- **Why:** Long-form recording is the case where "the audio is the valuable part and must not be
  lost" (project-context, long-form dictation): an hour in memory dies with the process. Daniel,
  2026-10-24, asked for "long-form recording" with a seamless flow to transcription.
  Android: a background recorder needs a foreground service, new permissions and a Play
  declaration, which is Daniel's call.
- **Alternatives:** recording into memory as dictation does (loses everything on a crash, and
  ~350 MB per 90 minutes); keeping the audio after transcription (against D-2026-10-22-20); a
  foreground service on Android now (I-15).
- **By:** agent, from Daniel's request R-2026-10-24-5; open to Daniel's review.

### D-2026-10-24-05: S1-mini by Superwhisper on desktop only; on hold on Android

- **Decision:** S1-mini by Superwhisper may be offered as a finishing step on desktop (B-40), if it
  runs well on a laptop CPU and keeps romanised Hebrew words. On Android it is on hold.
- **Why:** Daniel, 2026-10-24, after the research note: 462 MB, a few seconds per take on a recent
  phone at best, English-only. "For mobile though, on hold."
- **Alternatives:** an ONNX build for Android (none exists; not worth making while it is on hold).
- **By:** Daniel. Research: [`research/post-processing`](../research/post-processing/README.md).

### D-2026-10-24-04: Disfluencies are always removed, in every app and with every model

- **Decision:** Hesitation sounds (*um, uh, eh, erm, hmm*) and stutters are removed after decoding
  on every platform, for every model, with no setting to keep them (B-38). Meaning-dependent
  fillers (*like*, *you know*) and false starts are left to the models.
- **Why:** Daniel, 2026-10-24: the fine-tunes are trained to drop disfluencies, and a
  deterministic fallback gets the result sooner; "I can't think there's any reason why people would
  want those disfluencies."
- **Alternatives:** a setting (no use case for keeping them); relying on the fine-tunes alone
  (stock and older models still emit them).
- **By:** Daniel. Research: [`research/post-processing`](../research/post-processing/README.md).

### D-2026-10-24-03: Paste last transcription; the "No text field" prompt is opt-in

- **Decision:** Desktop keeps the last transcription and pastes it again on an action key, a tray
  item or the overlay's Paste. The "No text field" prompt (AT-SPI focus check, overlay with Paste)
  ships off by default, as an experimental setting.
- **Why:** Daniel, 2026-10-24: text pasted into the wrong window was unrecoverable; he asked for
  both. Opt-in because the check needs the desktop accessibility switch on for every app (off by
  default on KDE) and gave a false "no field" for Konsole on the first try (2026-10-24), so on by
  default it would interrupt the main use, dictating into a terminal.
- **Alternatives:** a modal dialog (takes the focus, so Paste would go into the dialog); a desktop
  notification (no button that pastes into the field). Drift detection: backlog I-14.
- **By:** Daniel (features), agent (opt-in default, overlay as the prompt).

### D-2026-10-24-02: Desktop outputs are switches; paste at the cursor only by default

- **Decision:** The desktop's Output is three independent switches (at the cursor, clipboard,
  this window), at least one on. Default and migration: at the cursor only, so takes no longer
  show in the Dictate tab's text box unless *This window* is on. Takes in the box collect with a
  blank line between them (`clear_each_take` off). Text box font 16 px. Desktop 1.000.
- **Why:** Daniel, 2026-10-24: paste "writes to the window as well in the app, which I definitely
  don't want"; "buttons that can be toggled on and off ... so you could choose to have what we
  currently have, but by default the paste mode should only be going into ... the cursor position";
  "a blank line inserted between transcriptions" for "natural segments".
- **Alternatives:** a fourth radio entry "paste + window" (no: he asked for combinable toggles);
  all switches off allowed (no: a take would look lost; History still has it).
- **By:** Daniel (switches, default, blank line, size), agent (whole-take clipboard copy, at least
  one on, migrating paste users to cursor-only).

### D-2026-10-24-01: Versions are M.NNN from a unified 1.000; earlier GitHub releases deleted

- **Decision:** Android and desktop both release as **1.000** (2026-10-24), then 1.001, 1.002, ...
  (three digits after the point; each app still releases on its own). All 45 earlier GitHub
  releases (Android 0.1.0-0.10.0, desktop 0.1.0-0.8.0) are deleted; their git tags stay.
  The floating-mic round tagged 0.11.0 / 0.11.1 that day was cancelled before publishing and
  ships as 1.000.
- **Why:** Daniel, 2026-10-24: "There's no point in pushing out this only to quickly succeed it",
  "I really don't want to clog it up with a huge amount of releases", "we'll use three decimal
  places of version releases, so v1.000 is this".
- **Alternatives:** 2.0.0 (Daniel's first suggestion; dropped for 1.0 because "Release v2" on
  hebrish.app names the 2026-10-22 model batch); X.Y.Z continued; deleting the tags too (not
  asked; kept so old builds stay traceable).
- **Checked:** desktop `app_update.parse_version` orders 1.000 > 0.10.0 and 1.010 > 1.009
  (tests added); Debian and F-Droid accept the format; the Android app compares no versions.
  `scripts/release-tag.sh` now refuses anything but M.NNN.
- **By:** Daniel (scheme, deletion, 1.0), agent (keeping tags, the version checks).

### D-2026-10-23-01: Personal dictionary corrects the text after decoding, shared with Android's

- **Decision:** Both apps get a personal dictionary applied to the model's text after decoding
  (before ALL CAPS), with one set of matching rules (`shared/personal-dictionary.md`, test set
  `shared/dictionary-cases.json`). Android reads and writes the system personal dictionary
  (`UserDictionary`), which works once the voice keyboard is enabled; desktop keeps its own
  `dictionary.json`. Android 0.9.0, desktop 0.8.0.
- **Why:** It cannot slow a take or make the model's own output worse, and works on every model.
  Daniel, 2026-10-23: words entered in a keyboard write to the personal dictionary and Hebrish
  reads from it; on desktop, Hebrish's own list.
- **Alternatives:** sherpa-onnx decoder hotwords (needs beam search instead of greedy, slower;
  unverified for NeMo transducers; over-boosting inserts words not said): left for a later
  measured trial. Training data stays the fix for words many users need.
- **By:** Daniel (scope and the Android integration), agent (the post-decoding approach and rules).
- Links: R-2026-10-22-32, I-13.

### D-2026-10-22-20: The app keeps no audio; History is text only

- **Decision:** The desktop setting `keep_audio` is removed, and audio that 0.7.0-0.7.2 kept in
  `history-audio/` is deleted on the first start of 0.7.3 (the text stays). History keeps text,
  the model version and the exact weights (`model_rev`). Supersedes the opt-in part of
  D-2026-10-22-17 and D-2026-10-22-13; D-2026-10-22-17's small retry buffer for *failed* takes
  (the last three, B-26) is unchanged.
- **Why:** Daniel, 2026-10-22: he doesn't want audio kept, and "the app should not be retaining
  audio, deliberately. It'll quickly eat up a lot of disk space." Mistranscriptions are tracked
  from the text (his corrections and near-miss terms per model version) instead.
- **Alternatives:** keep the opt-in setting off by default (rejected: deliberately not offered).
- **By:** Daniel, 2026-10-22. Request R-2026-10-22-44; backlog B-26, B-37.

### D-2026-10-22-19: Insert as you go follows pauses, and is quicker by default

- **Decision:** On desktop, a pause of 1 s or more inserts what was said at once, whatever the
  interval; the presets become Fast 3, Normal 5 (default), Relaxed 8 s, and existing installs
  move to the new value of their preset once. A Sabich piece cut at a short pause keeps its
  sentence open (the held full stop). Shakshuka pastes a phrase at a time by default: a few
  words every 2-3 s, a sentence end at once.
- **Why:** Daniel, 2026-10-22: text came too late and the breaks were jagged; word by word is
  jarring and long waits make you wonder whether it's working. Measured with
  `desktop/scripts/pace_sim.py`: same accuracy at 3-7 s on the test clips.
- **Alternatives:** keep the 7 s Normal and only fix the seams; re-decode across the seam with
  token timestamps (more accurate joins, but a second decode per piece; not needed yet).
- **By:** Daniel (request), 2026-10-22. Request R-2026-10-22-39; backlog B-33.

### D-2026-10-22-18: Parakeet (Sabich) is the desktop dictation default again

- **Decision:** Supersedes the default in D-2026-10-22-12. On Linux and Windows the default model
  is Sabich again. Installs that 0.7.0 moved to Shakshuka are moved back once. Shakshuka stays
  in the catalogue as a choice and is still first in line for streaming work; it comes back as
  the default once its live insertion works well.
- **Why:** After using 0.7.0's Shakshuka dictation the same day, Daniel found it distracting:
  words appeared two or three at a time, the screen flickered on each paste, and text held back
  waiting for the next word did not come out during a pause. Parakeet "gave better performance
  for the dictation use case".
- **Alternatives:** Keep Shakshuka as the default and fix the release logic first (the
  phrase-at-a-time release in B-32 is that fix, but it hasn't been tried in real dictation).
  A model per mode (I-5): wanted, parked.
- **By:** Daniel, 2026-10-22. Request R-2026-10-22-37; backlog B-32.

### D-2026-10-22-17: Recordings are not kept, except failed takes for retry

- **Decision:** Audio is deleted once its transcription succeeds. A take whose transcription
  failed keeps its audio for retry (the last three). Keeping all audio stays opt-in
  (`keep_audio`, off, D-2026-10-22-13). History gets truncation settings; the default stays
  unlimited.
- **Why:** Daniel's strong preference: voice recordings sitting around take space and make him
  uncomfortable; the only reason to keep one is not to lose words.
- **Alternatives:** Keep audio by default (rejected in D-2026-10-22-13 too).
- **By:** Daniel, voice note 2026-10-22 (59:26). Request R-2026-10-22-30; backlog B-26, B-28.

### D-2026-10-22-16: Every shortcut is remappable; Android starts with one button, tap-tap

- **Decision:** Desktop shortcuts come in two levels: a basic laptop preset (Enter / Escape
  style) and advanced binding where every action, the escape action included, can be bound to any
  key (F13 and up too). On Android the first button support is a single headset button that
  starts and stops (tap-tap).
- **Why:** A system-wide dictation tool collides with global shortcuts unless every key is
  movable; a macro pad or a USB HID button sending F13 avoids conflicts altogether. Daniel uses
  about six actions (start/stop, push-to-talk, cancel, retake, eject, escape), more than a foot
  pedal has. Holding a button on an earphone is awkward, so tap-tap.
- **Alternatives:** Fixed keys with a few options (rejected: conflicts). Push-to-talk on the
  headset (rejected: holding the button).
- **By:** Daniel, voice note 2026-10-22 (41:04, 43:34); remapping the escape action was Claude's
  suggestion, accepted. Requests R-2026-10-22-23, -33; backlog B-22, B-27.

### D-2026-10-22-15: All three output modes stay; the toggle moves to the tray and a shortcut

- **Decision:** Desktop keeps three output modes: clipboard + type (default), clipboard only,
  type only. The mode can be changed from the tray menu and with bindable shortcuts.
- **Why:** In the voice note Daniel first called "always use the clipboard" and then retracted
  it: with History as a fallback, a clipboard-free mode is useful when the transcription would
  overwrite something just copied. His typed correction the same day: the toggle exists but is
  hard to reach, so put it in the tray and on a shortcut.
- **Alternatives:** Clipboard always as a backup, no modes (retracted in the same note).
- **By:** Daniel, voice note 2026-10-22 (56:00) and typed correction. Request R-2026-10-22-24;
  backlog B-23.

### D-2026-10-22-14: Accounts are invite-only, starting with the maintainer; cross-device sync waits

- **Decision:** Hebrish gets accounts as a construct now (B-18), optional and invite-only: an
  allow-list of addresses, which at first holds only Daniel, so account features can be tested
  on real installs without affecting anyone else. Nothing in the app requires an account.
  Syncing history across devices (I-7) is deferred until accounts exist.
- **Why:** Cross-device sync needs accounts and server storage. Building the account layer first,
  closed, makes the later features testable without a public sign-up.
- **Alternatives:** Open sign-up (rejected for now: nothing to offer yet, and more to run).
  Sync without accounts, through each user's own Drive (that is the backup, B-17, not sync).
- **By:** Daniel. Requests R-2026-10-22-19, -20; backlog B-18, I-7.

### D-2026-10-22-13: History is on by default, kept in full and searchable; the text box clears per take

- **Decision:** Every transcript is kept on the device by default (`keep_history` on, no limit),
  in SQLite with a full-text index (`desktop/hebrish/history.py`), with search and word counts in
  the History tab. The Dictate tab's text box clears when a take starts (`clear_each_take`, on).
  Installs from before 0.7.0 get history switched on once (their `false` was the 0.5.0 forced
  default). Keeping audio is opt-in (`keep_audio`, off): about 2 MB a minute.
- **Why:** The text box became one huge blob after many takes. Daniel: err on the side of
  keeping things; with everything kept, it has to be searchable to be useful. Reverses the 0.5.0
  default (history off, last 50), which predates this log.
- **Alternatives:** Keep the 50-item JSON list (doesn't scale, no search). Audio on by default
  (rejected: disk use, and most people won't correct transcripts).
- **By:** Daniel (defaults, keeping everything); agent, implementing (SQLite/FTS5, the one-time
  switch, audio opt-in). Requests R-2026-10-22-13, -14; backlog B-14, B-15; commit 8ab496a.

### D-2026-10-22-12: Shakshuka is the desktop default; Sabich for phones and recordings

- **Decision:** On Linux and Windows the recommended (default) model is Shakshuka, the
  streaming line, with words inserted as you speak. Sabich stays the default on Android and is
  the pick for transcribing recordings on a computer. Shakshuka is first in line for retraining.
  Later, the catalogue should be narrowed to a few models the project can stand behind (for
  example, not both a Parakeet and a Qwen Sabich); not decided which.
- **Why:** Streaming text is what dictating into a terminal or chat box needs. Parakeet in
  5–10 s pieces is the workaround, and chunked Parakeet is unusable below about 2 s
  (`research/streaming-revision/`). Shakshuka runs on the same runtime at RTF ~0.2 on a CPU.
- **Alternatives:** Keep Sabich as the desktop default and offer Shakshuka as an option. Build
  live corrections (two-pass) now: deferred to idea I-4, to keep the first version simple.
- **By:** Daniel. Request R-2026-10-22-12; backlog B-12, B-13, I-5, I-6.

### D-2026-10-22-11: Outreach skills are for the maintainer and authorised representatives only

- **Decision:** `outreach-email`, `community-fyi` and `newsletter` ask first whether the user is
  the maintainer or someone Daniel has authorised to represent the project, and stop for anyone
  else. Others can suggest a contact in an issue titled "Outreach: <who>".
- **Why:** Outreach speaks for the project. A public skill that let anyone draft or send it, even
  as a "personal recommendation", invites messages the project never approved.
- **Alternatives:** A personal-recommendation mode for anyone (first draft; removed).
- **By:** Daniel.

### D-2026-10-22-10: One public plugin, `hebrish-maintainers`, in the `hebrish` marketplace

- **Decision:** All project skills ship in one plugin, `hebrish-maintainers`, in the public
  marketplace Hebrish-ASR/Hebrish-Claude-Plugins: app reviews and releases, parity, planning,
  training data, website, outreach and Hugging Face. Each skill states its access tier. The
  user-facing install skills stay a separate entry, `hebrish-setup`, pointing at
  Hebrish-Agent-Skills. Maintainer-only specifics live in the private Hebrish-Mgmt repo
  (`docs/maintainer-agent-notes.md`). The skills were moved out of Daniel's private plugins and
  this repo's `.claude/skills/`. The marketplace is linked from hebrish.app/docs and llms.txt,
  and Daniel's plugin catalogue indexes it.
- **Why:** Contributors need one install, and the project's skills should not sit in a personal
  account. The name follows Daniel's wording; many skills inside are open to anyone.
- **Alternatives:** Four plugins (dev, data, website, outreach; first layout, merged the same
  day: more to explain, no gain).
- **By:** Daniel (public marketplace, one plugin); agent (layout, access tiers, notes file).

### D-2026-10-22-09: Backlog work is queued in one sprint per platform

- **Decision:** `backlog.md` has a sprint per platform (desktop = Ubuntu + Windows; Android),
  each ending in a release, plus *Ideas for future versions*. Batches of requests are split
  across them with the `queue-sprint` skill. Parity follow-ups go into the other sprint.
- **Why:** Requests arrive in batches, often mid-work, for different platforms. One flat list
  mixed them up and hid what each release would contain.
- **By:** Daniel. Request R-2026-10-22-10.

### D-2026-10-22-08: The mic ignores its own prompts

- **Decision:** While a beep or spoken prompt plays with the mic open (start, retake, resume),
  the recorder drops input for the prompt's length plus 150 ms (`CUE_MARGIN_S`).
- **Why:** Spoken prompts were being transcribed into the user's text. Dropping is simpler
  and safer than echo cancellation, and the prompts are at most about 1.5 s long.
- **Alternatives:** Playing the prompt before opening the mic (rejected: it delays the start
  of every take by the prompt's length, even for people who start talking before it ends).
- **By:** Daniel asked for an offset; the mechanism is the agent's, implementing it. R-2026-10-22-6.

### D-2026-10-22-07: Voice feedback uses Herman, Corn and Hilbert; the stock voice goes

- **Decision:** Voice feedback offers three voices: Herman (default), Corn and Hilbert, the My
  Weird Prompts podcast characters (Daniel's own voice clones). They replace the Microsoft
  edge-tts voice used since 0.5.0, so existing Voice users hear Herman after updating.
  Hilbert has slightly longer lines for three prompts ("Dictation paused.", "Take discarded.",
  "Copied to the clipboard."), because the voice model garbles those single words in his voice.
- **Why:** Character voices are more fun, Daniel asked for exactly three options, and the clips
  are generated once from voices he owns, which avoids redistributing a third-party TTS voice.
- **Alternatives:** Keeping the stock voice as a fourth option (not done: three was the ask).
  Smaller formats such as Opus (not done: all three packs are 764 KB as WAV, and the player
  reads WAV with no extra dependency).
- **By:** Daniel (voices, three options); agent (replacing the stock voice, Hilbert's lines,
  WAV). R-2026-10-22-5.

### D-2026-10-22-06: Pending indicator, Enter guard and mid-sentence lowercase are ideas, not scheduled

- **Decision:** Backlog items I-1, I-2 and I-3 go under *Ideas for future versions*. The work now
  is B-1 (presets) and B-2 (Stop and send), which are smaller and fix the lost-text problem for
  anyone who uses the key.
- **Why:** Not everything can be built at once, and the two chosen items are the most direct
  fixes. I-2 option (b) holds the keyboard, which carries real risk and needs care.
- **By:** Daniel. Requests R-2026-10-22-2, -3, -4.

### D-2026-10-22-05: Feature parity across Android, Ubuntu and Windows is the standing aim

- **Decision:** A feature is not finished until it is on every platform where it makes sense.
  Desktop features land on Ubuntu and Windows together, since they share `desktop/`. Android
  follow-ups get their own backlog item rather than being forgotten.
- **Why:** One app, three platforms. Users shouldn't have to pick a platform by its feature list.
- **Alternatives:** Per-platform roadmaps (rejected: they drift, as the parity matrix shows).
- **By:** Daniel. Matrix: `docs/feature-parity.json`.

### D-2026-10-22-04: Stop and send is an optional key, with a configurable send key

- **Decision:** A new action key, *Stop and send* (`key_send`, not set by default). It stops,
  waits for the last text to be pasted, then presses the *Send key* (`send_chord`, default
  `enter`; users whose app needs `ctrl+enter` or `shift+enter` change it). Paste output only.
- **Why:** Hitting Enter while the last piece is still being transcribed submits without it. A
  key that sends only after the text is in fixes that with no keyboard tricks. It is an advanced
  setup (it needs a spare key or pedal), so it is off by default.
- **Alternatives:** Guarding a plain Enter (I-2), deferred. Holding Enter down to send (rejected:
  any key the app watches also reaches the focused window, so an Enter-based trigger would submit at once).
- **By:** Daniel. Request R-2026-10-22-2, backlog B-2.

### D-2026-10-22-03: Existing installs at the old 10 s default move to 7 s once

- **Decision:** On upgrade, a stored `live_insert_s` of 10 becomes 7, once, for configs saved
  before 0.7.0 (they lack `send_chord`). Any other value, and a 10 chosen later, is kept.
- **Why:** Every config file stores every setting, so a 10 written before 0.7.0 was almost
  always the old default, not a choice. Without this the faster default would reach new installs only.
- **Alternatives:** New installs only (rejected: most users would never see it).
- **By:** agent, implementing D-2026-10-22-02. Request R-2026-10-22-1.

### D-2026-10-22-02: Insert-as-you-go presets: Fast 5 s, Normal 7 s (default), Relaxed 10 s, Custom

- **Decision:** Replace the 10/15/20/30 s list with named presets. Normal is the old ~10 s cut by
  a third (~7 s), Fast is half (~5 s), and Relaxed keeps ~10 s. Custom takes 3–60 s.
- **Why:** At ~10 s, text arrived too slowly in use. Named presets are easier to choose than
  bare numbers, and Custom covers everyone else.
- **Alternatives:** Labels "normal / slow / slowest" (first suggestion). Not used, because the
  aim was a faster default, and the names should say which way each option goes.
- **Not yet measured:** how much accuracy Fast costs (shorter pieces give the model less
  context).
- **By:** Daniel. Request R-2026-10-22-1, backlog B-1.

### D-2026-10-22-01: Planning is public, in this repo, including the agent workspace

- **Decision:** Requests, the backlog and the decision log live in `planning/` in this public
  repository. The agent setup (`CLAUDE.md`, `.claude/skills/`) is public too, deliberately, so
  contributors and their agents work the same way.
- **Why:** Open development. Anyone can see what's planned and why, and reuse the skills.
- **Alternatives:** Keeping all planning in a private repo (still used for store accounts and
  submissions, which involve account details).
- **By:** Daniel.
