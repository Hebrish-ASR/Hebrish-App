# Debug log

One file per bug that took diagnosis: the symptom as reported, how the cause was found, the
wrong turns, the fix and how it was checked. Written for the next person (or agent) who hits the
same wall, so they start from what is known instead of re-deriving it.

What goes where:

- **Here:** the investigation. Commands run, what they showed, hypotheses ruled out and how,
  what is still unverified.
- **`desktop/docs/maintaining.md`, `android/docs/maintaining.md`:** the lasting rule the fix
  leaves behind ("wl-copy only where the compositor offers wlr data-control"), with a link to
  the entry here. Not the story.
- **`planning/decisions.md`:** only if fixing it meant choosing a behaviour (a default, a
  trade-off).

Agents: the `debug-log` skill in the `hebrish-maintainers` plugin writes entries in this format.

## Format

File name `YYYY-MM-DD-<short-slug>.md` (the date the bug was diagnosed). Front matter, then the
sections in this order; omit a section only if it would be empty.

```markdown
---
date: 2026-10-22            # diagnosed
platform: desktop-linux     # desktop-linux | desktop-windows | android | website | models | shared
environment: KDE Plasma 6.6.6 Wayland, Ubuntu 26.04.1
component: desktop/hebrish/inserter_linux.py
affected: "<= 0.7.3"        # versions that have the bug
fixed_in: "0.7.4"           # or "unfixed"
status: fixed               # fixed | worked-around | unfixed | not-a-bug
---

# <the symptom, in the reporter's terms>

## Symptom
## Cause
## How it was found
## Ruled out
## Fix
## Verified / not verified
## Related
```

Mark every claim (V) verified or (I) inferred, as `maintaining.md` does. Absolute dates. Public
repo: no personal names beyond "Daniel" (the maintainer), no host names, account ids or
credentials; a user is "a user" unless they asked to be credited.

## Index

Newest first.

| Date | Platform | Symptom | Status | Entry |
| --- | --- | --- | --- | --- |
| 2026-10-25 | desktop-linux, android | `<unk>` appears in dictated text at clause breaks (Sabich v2.0) | fixed (unreleased); training fix for next retrain | [2026-10-25-unk-in-dictation.md](2026-10-25-unk-in-dictation.md) |
| 2026-10-25 | desktop-linux | The last words of a take never arrive after Stop | fixed (gate); paste half mitigated, logged | [2026-10-25-last-words-lost-at-stop.md](2026-10-25-last-words-lost-at-stop.md) |
| 2026-10-24 | desktop-linux | Thinks it's recording when it isn't (record pressed while the last take was transcribing was ignored) | fixed in 1.001 | [2026-10-24-record-ignored-while-transcribing.md](2026-10-24-record-ignored-while-transcribing.md) |
| 2026-10-23 | android | Floating mic: the field jumps on insert and the line break before it is still deleted | fixed in 0.9.1 | [2026-10-23-overlay-paste-jumps.md](2026-10-23-overlay-paste-jumps.md) |
| 2026-10-23 | android | Capitals and full stops in the middle of sentences after a pause | fixed in 0.8.2 | [2026-10-23-android-mid-sentence-capitals.md](2026-10-23-android-mid-sentence-capitals.md) |
| 2026-10-23 | android | Floating mic deletes the line break before the dictated text | fixed in 0.7.6 | [2026-10-23-overlay-eats-line-break.md](2026-10-23-overlay-eats-line-break.md) |
| 2026-10-22 | desktop-linux | Title bar still flickers on every paste after 0.7.4 (Claude Code's wl-paste) | not-a-bug | [2026-10-22-paste-flicker-claude-code.md](2026-10-22-paste-flicker-claude-code.md) |
| 2026-10-22 | desktop-linux | Focused window's title bar flickers on every paste (KDE Wayland) | fixed in 0.7.4 | [2026-10-22-paste-flicker-kde.md](2026-10-22-paste-flicker-kde.md) |
