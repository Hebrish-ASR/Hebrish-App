---
sprint: history-backend
title: History backend, statistics and viewer
created: 2026-10-29
platforms: [desktop, android]     # desktop = Ubuntu + Windows (shared desktop/); desktop first
status: in progress               # planned | in progress | done | released <versions>
release: desktop 1.009 ships the first part (B-66, B-69, B-70); the rest per the release gate in ../backlog.md
requests: [R-2026-10-28-4, R-2026-10-28-5, R-2026-10-28-6, R-2026-10-28-7, R-2026-10-29-1]
---

# Sprint: history backend, statistics and viewer

## Goal

The dictation history (`history.db`, SQLite + FTS5 since 0.7.0) stays small and fast as it grows
by millions of characters, says how big it is, shows the volume transcribed at a glance, and
becomes a viewer of its own with fuzzy and (optionally) semantic search. Desktop first (Daniel,
2026-10-29), then Android for parity (D-2026-10-22-05).

## Why (evidence)

- Daniel, 2026-10-28/29 (R-2026-10-28-4 to -7, R-2026-10-29-1): sqlite-vec, periodic indexing and
  storage optimisation so the file doesn't bloat; its size shown in the app; Diagnostics to show
  total volumes rounded (K, then fifths of a million in M), no exact word counts; an optional
  7-day graph; History as a page that can be broken out, with fuzzy search.
- Scale check, 2026-10-28 (`desktop/docs/maintaining.md`, "Dictation history"): 200,000 synthetic
  rows, 170 MB: search 219 ms, stats 126 ms, insert 0.2 ms. Kept on SQLite (D-2026-10-28-01).
- Before 1.009 nothing ever gave space back: deleted rows left free pages in the file, the FTS5
  index grew as one small segment per insert, and `history.db-wal` was never truncated.

## Targets

Goals, not results. Measured on the 200,000-row synthetic database unless stated.

| Id | Target | How measured | Baseline |
| --- | --- | --- | --- |
| T1 | After upkeep, no free pages left in `history.db` and `history.db-wal` at 0 bytes | `History.storage()["free_bytes"]`, file size; `tests/test_history.py::test_maintain_compacts_and_converts_an_older_file_once` | free pages kept forever; WAL unbounded between checkpoints |
| T2 | Fuzzy search finds a word with one typo ("shakshoka" → "shakshuka") in under 300 ms | timing script on the synthetic database | no typo tolerance; prefix search 219 ms |
| T3 | Semantic search returns in under 500 ms on CPU, embeddings built in the background without delaying a take | timing script; a take while embeddings build | none |

## Task lists

### Desktop (Ubuntu + Windows)

| Id | Item | Check | Status |
| --- | --- | --- | --- |
| B-66 | History counts in K; WAL journaling | `tests/test_history_counts.py` | done (unreleased) |
| B-69 | Storage upkeep: incremental auto-vacuum, FTS5 optimize, `PRAGMA optimize`, WAL checkpoint and size limit; about daily while idle, and Diagnostics → Tidy now | T1 | done (unreleased) |
| B-70 | Diagnostics → History card: words and dictations all told (K, fifths of a million in M), audio hours, days active, database size, last tidied; *Show last 7 days* bar chart | off-screen render | done (unreleased) |
| B-68 | History viewer in its own window (tray entry), fuzzy keyword search, filters (date presets, source, model) | T2 | planned (next) |
| B-16 | Semantic search with sqlite-vec and a downloadable embedding model | T3 | planned |
| B-67 | Export to Parquet | an exported file read back with pyarrow | planned |

### Android

| Id | Item | Check | Status |
| --- | --- | --- | --- |
| B-69a | The same upkeep on the app's `history.db` (WorkManager, idle and charging) | free pages 0 after a run | planned |
| B-70a | Volume totals (K/M) and the 7-day chart in the app's statistics | screenshot | planned |
| B-68a | Fuzzy search and date presets in History | T2 on device | planned |
| B-16a | Semantic search (sqlite-vec via `BundledSQLiteDriver.addExtension`) | T3 on device | planned |

## Out of this sprint, related

- B-17 / B-20 Drive backup of the history; I-7 sync across devices (needs accounts).

## Done when

Daniel says so (release gate). Each desktop item above is released, and the Android items are
released or explicitly moved to a later sprint.
