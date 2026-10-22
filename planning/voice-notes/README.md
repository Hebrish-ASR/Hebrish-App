# Voice notes

Daniel's spoken ideas and updates for the Hebrish apps, kept in the repo as the original record
of each request. Started 2026-10-22. They are public, like the rest of `planning/`.

Each note is turned into requests and sprint items with the `queue-sprint` skill (plugin
`hebrish-maintainers`), and every request it produces links back to its note.

## Adding a note

Put the audio file in `inbox/`. Any name and any common format (mp3, m4a, ogg/opus, wav).
Compressed formats keep the repo small: opus or mp3 at speech bitrates is about 0.5 MB a minute.

## Processing a note (agents)

1. Transcribe it. The transcript is the source, so keep Daniel's wording, with only obvious
   ASR errors fixed (Hebrish model names, Hebrew words in the canonical romanization).
2. Move the audio from `inbox/` to `YYYY-MM/<YYYY-MM-DD>-<slug>.<ext>` (the date it was
   recorded, else the date it was added) with `git mv`. Write the transcript next to it as
   `<same name>.md`:

   ```markdown
   # <YYYY-MM-DD>: <one-line gist>

   - Audio: [<file>](<file>)
   - Processed: <YYYY-MM-DD>, requests R-…, R-…; decisions D-… (or "none")

   ## Transcript

   <the transcript>
   ```

3. Queue the asks with `queue-sprint`. In `planning/requests.md`, "From" is
   `Daniel ([voice note](voice-notes/YYYY-MM/<name>.md))`.
4. Add a row to `index.json`, then commit the audio, the transcript and the `planning/` edits
   together: `planning: voice note <date> <slug> -> R-…`.

`inbox/` empty means every note has been processed.

## Files

| Path | What |
| --- | --- |
| `inbox/` | New notes waiting to be processed |
| `YYYY-MM/` | Processed notes: the audio and its transcript (`.md`) |
| `index.json` | One entry per processed note: `file`, `transcript`, `recorded`, `processed`, `requests`, `decisions` |
