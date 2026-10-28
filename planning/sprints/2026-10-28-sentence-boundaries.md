---
sprint: sentence-boundaries
title: Sentence boundaries at pauses and stop/restart
created: 2026-10-28
platforms: [desktop, android]     # desktop = Ubuntu + Windows (shared desktop/)
status: planned                   # planned | in progress | done | released <versions>
release: per the release gate in ../backlog.md (Daniel decides whether this sprint joins or follows the open one)
requests: [R-2026-10-28-1]
---

# Sprint: sentence boundaries at pauses and stop/restart

## Goal

Dictating with insert as you go (desktop paste at the cursor; Android keyboard and floating mic),
pausing to think and stopping and restarting takes, gives text with **no capitals or full stops
in the middle of a sentence**, and **keeps the real sentence ends**. Ubuntu is the main
platform in daily use (Daniel, 2026-10-28); both apps get the same behaviour (parity,
D-2026-10-22-05).

## Why (evidence)

- Diagnosis: [debug log 2026-10-28](../../docs/debug-log/2026-10-28-false-sentence-breaks-remain.md).
  Desktop History, Sabich: 0.28 mid-sentence capitals per minute of audio on 1.005-1.007, down from
  0.72 before the seam fix of 0.7.6; none in takes under 8 s.
- Measurement: [research/desktop-base-model](../../research/desktop-base-model/README.md)
  (2026-10-28, `results.json`):
  - Same model (Sabich v2.2), same audio: **1** false sentence break when the take is decoded in
    one pass, **14** through the app's path (`Engine.transcribe(vad=True)`: ~10 s pieces cut at
    pauses, `stretch_pauses`, `shorten_silences`, `normalize`). The app's audio handling is the main
    cause, not the model.
  - Stop/restart: second half decoded alone, 7-10 of 14 start with a wrong capital; decoded after
    the last 3 s of the first half's audio (`transcribe_after`), **0 of 14**.
  - No stock base model (Whisper large-v3-turbo, Canary-1b-v2, Qwen3-ASR-0.6B) breaks fewer
    sentences than Sabich decoded in one pass, and all are slower on CPU. The base stays.

## Targets

Each target names how it is measured. The baseline is the 2026-10-28 measurement; targets are
goals, not results.

| # | Target | Measured by | Baseline (2026-10-28) |
| --- | --- | --- | --- |
| T1 | False sentence breaks on the pause takes through the app path: **≤ 3 per 27 takes** (≤ 0.12 per 100 words) | `research/desktop-base-model` scripts, `app` variant (B-54) | 14 (0.54 per 100 words); one-pass decode 1 |
| T2 | Stop/restart within the context window: **≤ 1 of 14** wrong capital at the restart, **≤ 1 of 14** full stop left before it | same scripts, stop/restart test, both apps' join logic (B-57, B-61) | 7-10 of 14 |
| T3 | Lost sentence ends (two sentences run together) **not worse** than baseline | `lost_stops` in the same runs and `desktop/scripts/seam_bench.py` | per `results.json` |
| T4 | WER on the pause takes **not worse** than baseline (± 0.3 points) | same runs | 11.6 % app path |
| T5 | Desktop History after a week of use: mid-sentence capitals **≤ 0.10 per minute** | the History query in the debug log (re-run, Sabich takes after the release) | 0.28 / min |
| T6 | No added wait after Stop beyond **0.3 s** on a 30 s take (desktop CPU) | decode timing in History `decode` / logs | per release 1.007 |
| T7 | Shared join rules (seam, cross-take) pass the same cases on both apps | `shared/seam-cases.json` in desktop pytest and Android unit tests (B-55) | no shared cases yet |

## Task lists

Status words as in [../README.md](../README.md). Ids continue the backlog's `B-<n>`. Each item
says how it is checked.

### Shared and measurement

| Id | Item | Check | Status |
| --- | --- | --- | --- |
| B-54 | **Find which step of the app path adds the breaks.** Run the pause takes and the disfluent set through the desktop path with one change at a time: `stretch_pauses` off; `shorten_silences` with `VAD_KEEP_S` 0.8 / 0.5 / 0.3 s and `VAD_LONG_S` 1.5 / 1.0 s; `normalize` off; piece length `PIECE_S` 10 / 20 / 30 s; the whole take decoded once at Stop. Report false breaks, lost stops, mid caps, WER and decode time per variant in `research/desktop-base-model/` (new section, `results.json` key `app_path_ablation`). Repeat the decisive variants through Android's path (`Transcriber.trim` edge trim, `Recorder.Segmenting` 8-28 s segments; no inner-pause padding, to be confirmed). Laptop CPU only. | table committed; T1-T4 numbers for the chosen variant | planned |
| B-55 | **Seam rules specified once, with shared cases.** `shared/seams.md`: how a piece joins the one before (held full stop, model's mark at the seam, `CONTINUES` fallback) and how a take joins the previous take (B-57, B-61). `shared/seam-cases.json`, run by desktop pytest and Android unit tests, as `shared/disfluency-cases.json` is. | T7 | planned |
| B-56 | **Measure in use.** Record per take in History `decode` (desktop) and the Android history export: number of seams, how each was joined (model mark / rule / cross-take), and whether a cross-take full stop was removed. The debug-log History query reads them (T5). No audio kept. | fields present; query updated in the debug log | planned |

### Desktop (Ubuntu + Windows)

| Id | Item | Check | Status |
| --- | --- | --- | --- |
| B-58 | **Apply the B-54 result** to the desktop audio path (`engine.py`: whichever of `stretch_pauses`, `shorten_silences`, `PIECE_S`, `normalize` it points to). Keep the B-46 voice-detection gate and the clipped-word fix (`seam_split`) intact. Record the change and numbers in `desktop/docs/maintaining.md`. | T1, T3, T4; `seam_bench.py` rerun | planned |
| B-57 | **Context across takes.** Keep the last `CONTEXT_S` (3 s) of each take's audio. A take that starts within a window (default 20 s, setting) of the previous one, with the same paste target (same focused window, when the inserter can tell), is decoded with `transcribe_after` on that audio. If the model continues the sentence (`stop` false): the new take's first word keeps the model's case, and the full stop the app pasted at the end of the previous take is removed with one Backspace before the paste, only when nothing else was pasted since (Wayland cannot read the field). If `stop` true: as now. Setting *Join takes into one sentence* (default on), in Settings, Output. Off when output is clipboard only. | T2; tests with a fake inserter | planned |
| B-59 | **Hold the take's final full stop (option to evaluate).** Alternative to the Backspace in B-57 if it misfires: paste the final `.` only when the next take starts a sentence, or after the window expires (paste it then, or leave it). Decide after B-57 is tried; log the choice with `log-decision`. | decision logged | idea |
| B-60 | **Live pieces: longer seams where it is cheap.** If B-54 shows longer pieces help, raise the insert-as-you-go presets' piece length or cut only at pauses ≥ 1.0 s, within the presets of B-48 (Fast 4 / Normal 6 / Relaxed 10 s). Wait to first paste must stay within the preset. | T1, T6 | planned |

### Android

| Id | Item | Check | Status |
| --- | --- | --- | --- |
| B-62 | **Apply the B-54 result** to Android (`core`: `Transcriber.trim`, `Recorder.Segmenting`, `TakeDecoder`), in parity with B-58. Record in `android/docs/maintaining.md`. | T1, T3 on the Android path (desktop harness with Android's cut rules, or on device) | planned |
| B-61 | **Context across takes, keyboard.** Keep the last 3 s of the previous take's audio and the time it ended. A take started within the window in the same field (`EditorInfo` field id and package) is decoded with `Transcriber.transcribeAfter`. If the sentence continues: read `getTextBeforeCursor(2, 0)`; only if it is still the full stop (and space) the app committed, delete it with `deleteSurroundingText` and commit the new text in the model's case. Floating mic: the same when it pastes into a field it can read; otherwise the B-55 rule. Parity setting with B-57. | T2; unit tests on `TakeDecoder` + a fake `InputConnection` | planned |
| B-63 | **Keep the piece end editable (keyboard).** While a take runs, commit each piece except its last word and mark (or the held full stop) as composing text (`setComposingText`); when the next piece arrives, fix that end by the seam decision and `finishComposingText`. Removes the commit-before-hearing-what-follows problem on Android, which the desktop paste cannot. Watch apps that mishandle composing text (check in a browser field, a chat app, a terminal). | T1 on device; manual check in three apps | planned |
| B-64 | **Android history export for T5.** Daniel exports the Android history after a week; run the debug-log query on it (Android was not measured on 2026-10-28). | rate per minute recorded in the debug log | planned |

## Out of this sprint, related

- **Training data with pauses** (next Sabich round, `ASR-Training`): an atomic dataset of
  sentences with mid-sentence pauses and fillers whose transcript has no break, and clips that start
  or end mid-sentence (lowercase start, no final mark). Fixes the model's own habit; queued there,
  not here.
- **Base model for desktop**: answered, keep Sabich ([research](../../research/desktop-base-model/README.md)).

## Done when

T1-T4 and T7 met and recorded; B-57/B-61 shipped on both platforms; T5 checked after a week of use
(it can close the sprint after the release). Then the release gate decides the version.
