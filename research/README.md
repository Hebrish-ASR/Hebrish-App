# Research

Agent-led investigations for the Hebrish apps. Started 2026-10-22.

A question goes here when answering it needs reading outside this repo (papers, vendor docs,
other runtimes) or a prototype before anything can be planned. The output is a recommendation
that `planning/` can act on, not shipped code.

One folder per topic, named for the question (`research/<topic>/`). Each has a `README.md`
with, in this order:

1. **Question**: what is being asked, and the request it came from (`R-…` in
   `planning/requests.md`).
2. **Status**: `open`, `answered`, or `superseded by <topic>`, with the date.
3. **Findings**: each with its source URL, the date it was read, and whether it was confirmed
   from the source or inferred.
4. **Recommendation** and the next step, linked to the backlog item it became.

Add notes, prototype scripts and measurements to the same folder as the work produces them.
When a topic is answered, its decision goes in `planning/decisions.md` and the backlog item
links back here.

| Topic | Question | Status |
| --- | --- | --- |
| [streaming-revision](streaming-revision/README.md) | Live word-by-word dictation that corrects earlier words when later speech changes their meaning (Deepgram-style). How is it built, and which base model fits it? | answered (2026-10-22) |
| [post-processing](post-processing/README.md) | Disfluency chop, numbers to digits and S1-mini by Superwhisper after the speech model: what can be regex, what runs locally on a phone, and how the chain is offered | open (2026-10-24) |
| [desktop-base-model](desktop-base-model/README.md) | A desktop base model that does not break sentences at pauses or stop/restart (Parakeet stays on phones): Qwen3-ASR-0.6B, Whisper turbo, Canary-1b-v2 vs Sabich | answered (2026-10-28): keep Sabich; the breaks come from the app path and stop/restart |
