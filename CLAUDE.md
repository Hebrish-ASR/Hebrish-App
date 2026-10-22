# CLAUDE.md

Hebrish apps: Android voice keyboard (`android/`) and the Ubuntu + Windows desktop app
(`desktop/`). Start with `README.md` (layout and releases), then `desktop/docs/maintaining.md` or
`android/docs/maintaining.md` for the engineering record.

## This repository is public, including this workspace

Hebrish-ASR/Hebrish-App is public. The agent workspace is exposed **deliberately**: this file,
`.claude/skills/` and `planning/` are meant to be read and used by contributors and their
agents. So:

- Write everything as if a stranger reads it: no personal details beyond Daniel's public role,
  no machine/host names, account ids, internal URLs, private repo contents, or credentials
  (reference a secret by its name, never its value).
- Skills that need private accounts or personal machines (the CDN upload, Daniel's installs)
  stay in Daniel's private plugin. Skills a contributor could run go here, in `.claude/skills/`.

## Where the shared work lives

These folders are where Daniel and agents work together. Read the relevant one before asking
something it would answer, and write to the one that fits.

| Folder | What goes there |
| --- | --- |
| `planning/` | Requests, the backlog (sprints and ideas) and the decision log. See below |
| `research/` | Agent-led investigations that end in a recommendation: one folder per topic, indexed in `research/README.md`, which also sets the format |
| `desktop/docs/maintaining.md`, `android/docs/maintaining.md` | The engineering record: how each app works, what was tried, what was measured |
| `docs/` | Shared reference: `feature-parity.json`, screenshots |
| `shared/` | Data and protocols both apps read (`catalogue.json`, `update-protocol.md`) |
| `.claude/skills/` | Skills a contributor's agent can run here |

A research answer becomes a decision (`planning/decisions.md`) and a backlog item, both linking
back to the research folder. Shipped behaviour is described in `maintaining.md`, not in
`research/`.

## Planning

`planning/` holds feature requests (`requests.md`), the working backlog (`backlog.md`, including
*Ideas for future versions*) and the decision log (`decisions.md`). When a decision is made, log
it with the `log-decision` skill. When requests come in (often in batches), queue them with the
`queue-sprint` skill: one sprint per platform in `backlog.md`.

Feature parity across Android, Ubuntu and Windows is the standing aim (D-2026-10-22-05).
`desktop/` is shared by Ubuntu and Windows, and `docs/feature-parity.json` is the matrix.

## Working here

- Other sessions commit in this repo concurrently: stage only your own files, and stage and commit in
  one command.
- Desktop tests: `cd desktop && .venv/bin/python -m pytest -q`.
