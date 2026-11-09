# Voice notes

Daniel's spoken ideas and updates for the Hebrish apps, turned into requests and sprint items.
Started 2026-10-22.

Raw transcripts and audio are not kept in this public repository (Daniel, 2026-11-05: they were
removed, and new ones are not added). Each note is published as a written-up podcast episode at
<https://hebrish.app/updates/podcast>, and that page is what requests link to. The originals stay
in the project Drive.

## Processing a note (agents)

1. Publish it with the `voice-update` skill. Its page is `https://hebrish.app/updates/<date>`.
2. Queue the asks with `queue-sprint` (maintainer's private plugin). In `planning/requests.md`,
   "From" is `Daniel ([voice note](https://hebrish.app/updates/<date>))`.
3. Add an entry to `index.json` and commit the `planning/` edits together:
   `planning: voice note <date> <slug> -> R-…`.

## Files

| Path | What |
| --- | --- |
| `index.json` | One entry per processed note: `page`, `recorded`, `processed`, `requests`, `decisions` |
