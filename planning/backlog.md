# Backlog

Last updated 2026-10-22. Status words: `idea`, `planned`, `in progress`, `done (unreleased)`,
`released <version>`. Each item lists the platforms it still has to reach (parity is the aim:
decision D-2026-10-22-05).

## Now

| Id | Item | Platforms | Status |
| --- | --- | --- | --- |
| B-1 | **Insert-as-you-go presets.** Fast ~5 s, Normal ~7 s (new default, was ~10 s), Relaxed ~10 s, Off, Custom (3–60 s). Existing installs at the old 10 s move to 7 once. From R-2026-10-22-1; decisions D-2026-10-22-02, -03 | Ubuntu, Windows: done (unreleased, desktop 0.7.0). Android: see B-3 | done (unreleased) |
| B-2 | **Stop and send.** An optional action key: stop, wait for the last words to be pasted, then press the send key (Enter by default; configurable, e.g. Ctrl+Enter). From R-2026-10-22-2; decision D-2026-10-22-04 | Ubuntu, Windows: done (unreleased, desktop 0.7.0; Windows tested in CI only). Android: see B-4 | done (unreleased) |

## Next

| Id | Item | Platforms | Status |
| --- | --- | --- | --- |
| B-3 | **Android: interval presets.** Android's *Type as you go* is on/off with a fixed interval; give it the same Fast / Normal / Relaxed / Custom choice | Android | planned |
| B-4 | **Android: Stop and send.** The voice keyboard could offer a stop-and-send button that stops, inserts the last text, then submits the field (IME action or Enter). Needs a UI decision: a long-press on the mic, or its own button | Android | planned |
| B-5 | **Release desktop 0.7.0** with B-1 and B-2 | Ubuntu, Windows | planned |

## Ideas for future versions

Worth doing, not scheduled. Ordered roughly by value.

| Id | Idea | Notes | Status |
| --- | --- | --- | --- |
| I-1 | **"Still transcribing" indicator during a take.** After you stop, the tray and overlay already show *Transcribing…*. While you are still talking with insert-as-you-go on, though, nothing shows that a piece is still being decoded. Add a pending mark to the tray icon and the overlay whenever the decode queue isn't empty. From R-2026-10-22-3 | All platforms | idea |
| I-2 | **Guard a plain Enter.** Catch an ordinary Enter pressed while text is still pending. Options: (a) beep and flash the overlay, a warning only, because the Enter has already reached the app; (b) hold the keyboard only while text is pending (usually under 2 s), keep the Enter, paste, then replay it. (b) is the only option that saves a reflex Enter, but a hang would leave the keyboard held, so it needs a hard timeout and would be opt-in. On Linux, (b) needs exclusive access to the keyboard device (EVIOCGRAB); on Windows, a low-level keyboard hook. From R-2026-10-22-2 | Ubuntu, Windows; Android differs (the IME owns its Enter) | idea |
| I-3 | **Mid-sentence continuation.** When the last text the app inserted didn't end in `.`, `?` or `!`, and the new take starts within ~2 minutes, lowercase the new take's first letter (keeping "I", "I'm" and all-caps acronyms). Within one insert-as-you-go take this is reliable, because the pieces are known to be continuous; across takes the cursor may have moved to another window, hence the time limit and an off switch. The app can't read the text field (not possible on Wayland), so it goes by its own last output. From R-2026-10-22-4 | All platforms | idea |
