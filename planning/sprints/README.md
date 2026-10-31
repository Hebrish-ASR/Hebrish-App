# Sprints

Cross-platform sprints with targets. Started 2026-10-28 (Daniel: one sprint definition for a
problem that spans Android and Ubuntu, worked through in its own session).

`../backlog.md` still holds the per-platform sprints and ideas; a sprint here is used when one
goal spans platforms and needs measurable targets. Its items take the backlog's `B-<n>` ids, and
the backlog's *Cross-platform sprints* table links each sprint file.

## Format

One file per sprint, `YYYY-MM-DD-<slug>.md` (the date it was defined): front matter (`sprint`,
`title`, `created`, `platforms`, `status`, `release`, `requests`), then **Goal**, **Why
(evidence)**, **Targets** (each with how it is measured and its baseline; targets are goals,
never shown as results), **Task lists** (one per platform or area: id, item, check, status),
**Out of this sprint, related**, **Done when**. Status words as in `../README.md`.

Agents: the flow-control plugin's `plan-sprint` (define a sprint, or add a task list to one) and
`capture` (file new asks mid-task); `setup` creates a planning layout in a repo that has none.
Contributors without them: copy the newest file and follow the format above.

## Index

| Sprint | Platforms | Status | Defined |
| --- | --- | --- | --- |
| [Sentence boundaries at pauses and stop/restart](2026-10-28-sentence-boundaries.md) | desktop, Android | planned | 2026-10-28 |
| [History backend, statistics and viewer](2026-10-29-history-backend.md) | desktop, Android | in progress | 2026-10-29 |
