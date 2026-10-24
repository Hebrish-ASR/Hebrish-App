---
date: 2026-10-24
platform: desktop-linux
environment: KDE Plasma 6.6.6 (KWin 6.6.6) Wayland, Ubuntu 26.04.1, xclip 0.13-4build1
component: desktop/hebrish/inserter_linux.py (LinuxInserter.insert, copy_for_paste, release_later)
affected: "0.7.4 to 1.002 on compositors where the paste uses xclip (KWin, Mutter)"
fixed_in: "next desktop release after 1.002"
status: fixed (unit-tested; not yet checked live on the KDE desktop)
---

# A dictated take stays on the X11 clipboard after the Wayland clipboard moves on

## Symptom

After dictating into an app, copying an image in a Wayland app and pasting it into Claude Code
(a terminal app reading the clipboard over X11) pasted the old dictated text instead of the image.
Claude Code saves a pasted image with `xclip -t image/png -o || wl-paste ...`; xclip returned the
stale text and exited 0, so the `wl-paste` fallback never ran (anthropics/claude-code#104668).
Daniel worked around it with a wrapper, `~/.local/bin/xclip` (2026-10-24), that fails an image read
unless the X11 selection really offers that type.

## Cause

Since 0.7.4 the paste path on KWin and Mutter sets the clipboard with `xclip -selection clipboard`
(see 2026-10-22-paste-flicker-kde.md). xclip forks into the background and owns the X11 CLIPBOARD
until another X client takes it. (I) KWin's XWayland bridge did not take the X11 selection over
when a Wayland app copied an image, so X11 readers kept getting Hebrish's text. Hebrish never needed
the text after the paste: the Clipboard output copies the whole take separately.

## Fix

`LinuxInserter.insert(..., "paste", ...)` uses `copy_for_paste()`: the same tool kept in the
foreground (`xclip -quiet`, `wl-copy --foreground`), and `release_later()` ends it
`PASTE_HOLD_S` (1.5 s) after the paste chord, unless it already exited because another copy took
the selection. `copy_to_clipboard()` (Copy buttons, the Clipboard output, clipboard-only pieces) is
unchanged: there the text is meant to stay.

Hebrish does not save and restore what was on the clipboard before a take; that is unchanged.

## Checked

- (V) On a private Xvfb display: `xclip -quiet` serves the text; after it is terminated
  `xclip -o` fails with "target STRING not available" (no owner); a foreground xclip exits on
  its own when another client sets the selection.
- (V) Unit tests in `desktop/tests/test_inserter_linux.py`: the paste path uses the foreground flag
  for both tools and schedules the release; release ends only a running process; the clipboard
  method still uses `copy_to_clipboard`.
- (I) Not run live on the KDE desktop (no paste tests there): that KWin then keeps the X11 and
  Wayland clipboards in step, and that 1.5 s is enough for slow apps to read the paste. If a paste
  ever comes out empty, raise `PASTE_HOLD_S` first.
- (I) Once confirmed, the `~/.local/bin/xclip` wrapper can go; it is harmless meanwhile (Hebrish
  finds `xclip` on PATH and the wrapper passes everything but image reads straight through).
