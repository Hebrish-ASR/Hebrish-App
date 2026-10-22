# Decision log

Newest first. Append-only: a decision that is later reversed stays here, and the new one says
which decision it supersedes. Ids are `D-<date>-<nn>`. Agents add entries with the
`log-decision` skill (plugin `hebrish-maintainers`, marketplace Hebrish-ASR/Hebrish-Claude-Plugins).

Each entry: **Decision**, **Why**, **Alternatives** (what was considered and not chosen),
**By** (who decided), and links to the request, backlog item or commit where they exist.

---

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
