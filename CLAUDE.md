# CLAUDE.md

Hebrish apps: Android voice keyboard (`android/`) and the Ubuntu + Windows desktop app
(`desktop/`). Start with `README.md` (layout and releases), then `desktop/docs/maintaining.md` or
`android/docs/maintaining.md` for the engineering record.

## This repository is public, including this workspace

Hebrish-ASR/Hebrish-App is public. The agent workspace is exposed **deliberately**: this file,
`planning/` and the project's skills are meant to be read and used by contributors and their
agents. So:

- Write everything as if a stranger reads it: no personal details beyond Daniel's public role,
  no machine/host names, account ids, internal URLs, private repo contents, or credentials
  (reference a secret by its name, never its value).
- The project's maintenance skills (reviews, parity, planning, `log-decision`, `debug-log`,
  `queue-sprint`, data, website, Hugging Face) are in Daniel's private Claude Code plugin since
  2026-11-09 (D-2026-11-09-01); the public `hebrish-maintainers` plugin was removed. Don't add
  skills here. The public `hebrish` marketplace
  ([Hebrish-ASR/Hebrish-Claude-Plugins](https://github.com/Hebrish-ASR/Hebrish-Claude-Plugins))
  still has `hebrish-setup` for users. Contributors without the skills follow the formats in
  `planning/` and `docs/debug-log/README.md` and open an issue or pull request.
  `.claude/skills/android-release` is the last repo-local copy, kept until it is reconciled with
  the plugin's version (2026-10-22).

## Where the shared work lives

These folders are where Daniel and agents work together. Read the relevant one before asking
something it would answer, and write to the one that fits.

| Folder | What goes there |
| --- | --- |
| `planning/` | Requests, the backlog (sprints and ideas) and the decision log. See below |
| `research/` | Agent-led investigations that end in a recommendation: one folder per topic, indexed in `research/README.md`, which also sets the format |
| `desktop/docs/maintaining.md`, `android/docs/maintaining.md` | The engineering record: how each app works, what was tried, what was measured |
| `docs/` | Shared reference: `feature-parity.json`, screenshots |
| `docs/debug-log/` | One file per bug that took diagnosis: symptom, cause, how it was found, wrong turns, fix, what is verified. Index and format in its `README.md`; lasting rules still go in `maintaining.md`. Skill: `debug-log` |
| `shared/` | Data and protocols both apps read (`catalogue.json`, `update-protocol.md`) |
| Maintainer skills | Private since 2026-11-09 (reviews, parity, planning, data, website, Hugging Face): see above |

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
