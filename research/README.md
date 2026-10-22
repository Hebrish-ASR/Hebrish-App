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
