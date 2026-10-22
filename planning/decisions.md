# Decision log

Newest first. Append-only: a decision that is later reversed stays here, and the new one says
which decision it supersedes. Ids are `D-<date>-<nn>`. Agents add entries with the
`log-decision` skill (`.claude/skills/log-decision/`).

Each entry: **Decision**, **Why**, **Alternatives** (what was considered and not chosen),
**By** (who decided), and links to the request, backlog item or commit where they exist.

---

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
