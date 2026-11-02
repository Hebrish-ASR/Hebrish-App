---
date: 2026-11-02
platform: desktop-linux
environment: KDE Plasma 6.6.6 (KWin 6.6.6, Klipper in plasmashell) Wayland, Ubuntu 26.04.1, xclip 0.13
component: desktop/hebrish/inserter_linux.py (LinuxInserter.insert, ClipboardKeeper, read_clipboard, write_clipboard)
affected: "all desktop versions on Linux (the clipboard was never restored); on KDE since 0.7.4 (xclip paste + Klipper)"
fixed_in: "next desktop release after 1.016 (unreleased)"
status: fixed (unit-tested and checked against the live KDE clipboard; the real paste into an app not yet tried by Daniel)
---

# The transcript is pasted twice when something was on the clipboard

## Symptom

Daniel, 2026-11-02 (Ubuntu, KDE Plasma Wayland): "if I have something on the clipboard and then
I paste something, for some reason the transcript will be pasted twice". With something copied,
he dictated (Hebrish pasted the transcript at the cursor), then pressed Ctrl+V for his own
copied text and got the transcript again. It "gets in the way of how you might want to use the
clipboard in conjunction with the text injection".

## Cause

The paste path borrows the clipboard: `copy_for_paste()` serves the transcript with
`xclip -selection clipboard -quiet` (KWin: xclip, see 2026-10-22-paste-flicker-kde.md), presses
Ctrl+V, and `release_later()` ends xclip 1.5 s later. Nothing ever put the user's previous
clipboard back. (V) On KDE, ending xclip doesn't empty the clipboard: Klipper keeps the
transcript as the current clipboard (it is the newest history item; Klipper refills an emptied
clipboard from its history), so the user's next Ctrl+V pastes the transcript a second time.
Hebrish inserted it once; the second copy is the user's own paste of a clobbered clipboard.

A second, deliberate source on Daniel's machine: his config has both *Output → At the cursor*
and *Output → Clipboard* on (`out_cursor`, `out_clipboard`). The Clipboard output copies the
whole take 600 ms after the paste on purpose, so with it on the transcript stays on the
clipboard by design and the fix leaves that alone.

## How it was found

- Read the insert path: `Controller._insert` → `LinuxInserter.insert(text, "paste", chord)`;
  `_done` → `_copy_take` when `out_clipboard`. Only one paste chord per piece; no retry, no
  typing path, no second insert (V, by reading `ui/app.py` and the existing tests).
- Live, on the KDE Wayland session (2026-11-02), without a key press: set the clipboard to
  `USERCLIP` through Klipper (`qdbus6 org.kde.klipper /klipper setClipboardContents`), served
  `TRANSCRIPT` with `xclip -quiet` as `copy_for_paste` does, then killed it after 1.5 s:

  | moment | `wl-paste` (Wayland) | `xclip -o` (X11) | `wl-paste -p` (PRIMARY) |
  | --- | --- | --- | --- |
  | before | USERCLIP | an older dictated take | |
  | during the paste | TRANSCRIPT | TRANSCRIPT | USERCLIP |
  | after xclip ended | **TRANSCRIPT** | no owner | USERCLIP |

  Klipper history after: 0 = TRANSCRIPT, 1 = USERCLIP. So the Wayland clipboard keeps the
  transcript (V), and PRIMARY is not touched by the paste (V).
- The "before" X11 value was an older take held by a background `xclip` (the Clipboard output's
  `copy_to_clipboard`, still running): KWin's X11 side lags the Wayland clipboard (V, seen
  again; the issue of 2026-10-24-xclip-holds-clipboard.md). That is why the restore must not
  read with `xclip -o` on KDE.

## Ruled out

- **A double insert by the app** (two pastes, paste plus typing, a retry): there is one chord per
  piece; the transcript appears twice only because the user's Ctrl+V pastes it again (V by code
  reading and the live clipboard check; the app's own key events were not traced).
- **PRIMARY selection:** the paste sets only CLIPBOARD; PRIMARY kept the user's value (V).
- **The restore racing the paste:** the restore runs after `release_later` (1.7 s vs 1.5 s), so
  the target app has had the same time to read the paste as before.

## Fix

`inserter_linux.ClipboardKeeper` (module singleton `KEEPER`):

- `LinuxInserter.insert(..., "paste", ...)` calls `KEEPER.before_paste()` (saves the clipboard's
  text) and, after the chord, `KEEPER.after_paste(text)`, which restores it `RESTORE_AFTER_S`
  (1.7 s) later.
- Pastes within that window (insert as you go) keep the first save and push the restore back.
- `copy_to_clipboard()` (Clipboard output, Copy buttons, `insert(..., "clipboard")`) cancels a
  pending restore: a deliberate copy stays. Internal writes use `_copy()`.
- The restore is skipped when the clipboard by then holds something other than the pasted text
  (the user copied meanwhile), and when nothing was saved (an image, an empty clipboard).
- Reading/writing without taking focus: `read_clipboard()` / `write_clipboard()`. KDE: Klipper
  over D-Bus (`gdbus call` for `getClipboardContents`, reply parsed with `ast.literal_eval`;
  `dbus-send ... string:<text>` for `setClipboardContents`). KDE Wayland without Klipper: no
  restore. wlroots/Hyprland: `wl-paste`. X11 or GNOME: `xclip -o`, then the usual tool.

First attempt (wrong turn): reading Klipper with `dbus-send --print-reply=literal`. Its output is
three spaces plus the text, with no reliable end marker, and the leading spaces came back into
the restored text (V). `gdbus` prints GVariant text that round-trips exactly (checked with
quotes, a tab, a newline, a backslash and Hebrew).

Klipper's `setClipboardContents` also sets PRIMARY to the restored text (I, from Klipper's
behaviour; not checked separately).

## Verified / not verified

- (V) Unit tests, `desktop/tests/test_inserter_linux.py`: restore after a paste; restore when the
  clipboard is empty after release; a burst restores the first save once; the Clipboard output's
  copy and `insert(..., "clipboard")` cancel the restore; a newer user copy is not overwritten;
  nothing is restored when nothing was saved; gdbus reply parsing; Klipper missing; KDE Wayland
  without Klipper never reads X11; X11 reads with xclip. Full suite: 526 passed, 3 failures
  unrelated to this change (catalogue labels and shared prompt data, other work in progress).
- (V) Live on the KDE Wayland session with the real `ClipboardKeeper`, `copy_for_paste` and
  `release_later` (no key press): the user's multi-line text with quotes and Hebrew was saved via
  Klipper and was the Wayland clipboard again after a two-piece burst; a copy made by the user
  during the restore window was kept.
- (I) Not tried: a real dictation pasted into an app on Daniel's desktop with the new code,
  then Ctrl+V. In particular that 1.7 s is late enough for slow apps; if the restored text ever
  gets pasted instead of the transcript, raise `PASTE_HOLD_S` (the restore follows it).
- (I) GNOME/Mutter and wlroots paths are by code only.
- Daniel's config has *Output → Clipboard* on; with it on the take still stays on the clipboard
  (that output's purpose). To keep his own clipboard, switch that output off.

## Related

- 2026-10-24-xclip-holds-clipboard.md (the paste's xclip released after 1.5 s)
- 2026-10-22-paste-flicker-kde.md (why xclip, not wl-copy, on KWin)
- `desktop/docs/maintaining.md`, "The user's clipboard is put back after a paste"
