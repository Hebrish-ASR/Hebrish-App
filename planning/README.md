# Planning

Public project tracking for the Hebrish apps (Android, Ubuntu, Windows). Started 2026-10-22.

Hebrish is a one-person project, built by Daniel Rosehill with AI coding agents. This folder is
where the plans live, in the open, so anyone (or any agent) can see what has been asked for,
what is being worked on next, and why things were decided the way they were.

| File | What |
| --- | --- |
| [requests.md](requests.md) | Feature requests received, from users and from Daniel, with where each one went |
| [backlog.md](backlog.md) | The working list: one sprint per platform (desktop, Android), and ideas for future versions |
| [sprints/](sprints/README.md) | Cross-platform sprints with targets, one file each |
| [decisions.md](decisions.md) | The decision log, newest first |
| [voice-notes/](voice-notes/README.md) | Daniel's spoken ideas and updates (audio and transcript), the source of many requests. New ones go in `voice-notes/inbox/` |

## How to use it

- **A request comes in** → add a row to `requests.md` (date, where it came from, the ask in
  one line). When it is triaged, link the backlog item it became, or say why not.
- **Work is chosen** → it goes into a sprint in `backlog.md` (one per platform: desktop, Android; agents use the `queue-sprint` skill). Things worth doing but not
  scheduled go under *Ideas for future versions*. Not everything can be built at once; that
  section is the honest answer to "will you add X?".
- **A decision is made** (a default, a trade-off, a scope call, "not this way") → append it to
  `decisions.md`. Agents: use the `log-decision` skill (plugin `hebrish-maintainers` in the [hebrish marketplace](https://github.com/Hebrish-ASR/Hebrish-Claude-Plugins)).
- **Something ships** → mark the backlog item done with the commit or tag. The engineering
  record (how it works, what was tried) stays in `desktop/docs/maintaining.md` and
  `android/docs/maintaining.md`, not here.

Status words: `idea`, `planned`, `in progress`, `done (unreleased)`, `released <version>`.
Platform parity is the standing aim (decision D-2026-10-22-05): an item names every platform it
still has to reach, and `docs/feature-parity.json` is the per-feature matrix.

## Suggesting something

Open an issue on [Hebrish-ASR/Hebrish-App](https://github.com/Hebrish-ASR/Hebrish-App/issues),
or use the contact options on <https://hebrish.app/contact>. Requests are logged here with no
names unless you ask to be credited.

Store accounts and submissions (Google Play and the like) are tracked privately, because they
involve account details.
