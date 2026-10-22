# Backlog

Last updated 2026-10-22. Status words: `idea`, `planned`, `in progress`, `done (unreleased)`,
`released <version>`. Work is queued in **one sprint per platform** (desktop = Ubuntu + Windows,
which share `desktop/`; Android). A sprint ends with a release. Parity is the aim (decision
D-2026-10-22-05): an item done on one platform gets a matching item in the other sprint, unless
it makes no sense there. Agents add to sprints with the `queue-sprint` skill.

## Sprint: desktop (Ubuntu + Windows), toward 0.7.0

| Id | Item | Status |
| --- | --- | --- |
| B-1 | **Insert-as-you-go presets.** Fast ~5 s, Normal ~7 s (new default, was ~10 s), Relaxed ~10 s, Off, Custom (3–60 s). Existing installs at the old 10 s move to 7 once. R-2026-10-22-1; D-2026-10-22-02, -03 | done (unreleased) |
| B-2 | **Stop and send.** An optional action key: stop, wait for the last words to be pasted, then press the send key (Enter by default, configurable). R-2026-10-22-2; D-2026-10-22-04. Windows tested in CI only | done (unreleased) |
| B-6 | **Character voices.** Voice feedback in Herman's, Corn's or Hilbert's voice (Settings → Sounds → Voice), replacing the stock TTS voice. R-2026-10-22-5; D-2026-10-22-07 | done (unreleased) |
| B-7 | **Prompts no longer end up in the transcript.** The mic ignores input while a beep or spoken prompt plays (start, retake, resume), plus 150 ms. R-2026-10-22-6; D-2026-10-22-08 | done (unreleased) |
| B-8 | **Tray menu icons.** Icons beside the tray menu entries (Start dictation, Show overlay, Show window, …) so the menu reads at a glance. R-2026-10-22-8 | planned |
| B-5 | **Release desktop 0.7.0** with the items above | planned |

## Sprint: Android

| Id | Item | Status |
| --- | --- | --- |
| B-9 | **Floating mic: horizontal offset.** Today the floating mic can be moved up and down the screen edge. Add a horizontal offset: by default the mic sits a little in from the screen edge (hard to reach right at the edge), and the user adjusts from there: negative puts it flush with the edge, positive moves it further in. Applies on whichever side it is snapped to. R-2026-10-22-9 | planned |
| B-10 | **Design pass.** The app is taking shape, and splitting settings over many pages works well, but the screens need visual design: consistent cards, spacing, headers and icons, using the brand standard (Hebrish-Mgmt `brand/`). R-2026-10-22-7 | planned |
| B-3 | **Interval presets.** Android's *Type as you go* is on/off with a fixed interval; give it the same Fast / Normal / Relaxed / Custom choice (parity with B-1) | planned |
| B-4 | **Stop and send.** The voice keyboard could offer a stop-and-send control that stops, inserts the last text, then submits the field (IME action or Enter). Needs a UI decision: a long-press on the mic, or its own button (parity with B-2) | planned |
| B-11 | **Character voices and cue muting.** Android has beeps but no spoken prompts: ship the same Herman / Corn / Hilbert WAVs (`desktop/hebrish/data/voice/`), and check whether Android beeps also bleed into the recording (parity with B-6, B-7) | planned |

## Ideas for future versions

Worth doing, not scheduled. Ordered roughly by value.

| Id | Idea | Notes | Status |
| --- | --- | --- | --- |
| I-1 | **"Still transcribing" indicator during a take.** After you stop, the tray and overlay already show *Transcribing…*. While you are still talking with insert-as-you-go on, though, nothing shows that a piece is still being decoded. Add a pending mark to the tray icon and the overlay whenever the decode queue isn't empty. R-2026-10-22-3 | All platforms | idea |
| I-2 | **Guard a plain Enter.** Catch an ordinary Enter pressed while text is still pending. Options: (a) beep and flash the overlay, a warning only, because the Enter has already reached the app; (b) hold the keyboard only while text is pending (usually under 2 s), keep the Enter, paste, then replay it. (b) is the only option that saves a reflex Enter, but a hang would leave the keyboard held, so it needs a hard timeout and would be opt-in. On Linux, (b) needs exclusive access to the keyboard device (EVIOCGRAB); on Windows, a low-level keyboard hook. R-2026-10-22-2 | Ubuntu, Windows; Android differs (the IME owns its Enter) | idea |
| I-3 | **Mid-sentence continuation.** When the last text the app inserted didn't end in `.`, `?` or `!`, and the new take starts within ~2 minutes, lowercase the new take's first letter (keeping "I", "I'm" and all-caps acronyms). Within one insert-as-you-go take this is reliable, because the pieces are known to be continuous; across takes the cursor may have moved to another window, hence the time limit and an off switch. The app can't read the text field (not possible on Wayland), so it goes by its own last output. R-2026-10-22-4 | All platforms | idea |
