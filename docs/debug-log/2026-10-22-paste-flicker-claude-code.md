---
date: 2026-10-22
platform: desktop-linux
environment: KDE Plasma 6.6.6 (KWin 6.6.6) Wayland, Ubuntu 26.04.1, wl-clipboard 2.2.1-2build1, Konsole running Claude Code 2.1.308
component: none in Hebrish (the target app's own clipboard read)
affected: "all versions, only when pasting into a terminal running Claude Code"
fixed_in: "unfixed"
status: not-a-bug
---

# Title bar still flickers on every paste after 0.7.4

## Symptom

Daniel, 2026-10-22, on 0.7.4 (installed from APT, app restarted after install), dictating into
Konsole running Claude Code: the same flicker as before 0.7.4, on every paste.

## Cause

The flicker is still a focus steal by wl-clipboard, but it no longer comes from Hebrish. Claude
Code handles Ctrl+V itself (image paste). It runs `wl-paste -l` to list the clipboard's types and
then a second `wl-paste` to read it. wl-paste 2.2.1 on KWin 6.6 has the same problem as wl-copy
had in [2026-10-22-paste-flicker-kde.md](2026-10-22-paste-flicker-kde.md): it binds only
`zwlr_data_control_manager_v1`, which KWin 6.6 does not offer, so it maps a toplevel and takes
focus. Two focus steals per paste: what Daniel sees.

- (V) Two `wl-paste | wl-clipboard` activations, about 25 ms apart, follow every Hebrish paste.
- (I) The caller is Claude Code. Its binary contains `wl-paste -l 2>/dev/null | grep -E …` and
  `wl-paste --type image/png > …`. Hebrish contains no `wl-paste` call. A process watcher
  (`pgrep -x wl-paste`, 5 ms poll) did not catch the parent, because each wl-paste lives about 3 ms.

## How it was found

1. Ruled out a stale install: `dpkg -l hebrish` showed 0.7.4-1. The running process started at
   22:18:18, 11 s after `/var/lib/dpkg/info/hebrish.list` was written. It runs with
   `PYTHONPATH=/usr/lib/hebrish`.
2. In that environment, `inserter_linux.clipboard_command()` returns
   `['xclip', '-selection', 'clipboard']` (65 globals, only `ext_data_control_manager_v1`).
3. A KWin script logged every activation:
   `workspace.windowActivated.connect(w => print("FOCUSLOG " + Date.now() + " " + (w ? w.resourceClass + " | " + w.caption : "null")))`,
   loaded with `qdbus6 org.kde.KWin /Scripting org.kde.kwin.Scripting.loadScript <file> focuslog`
   and then `…Scripting.start`. Output goes to `journalctl --user` (`kwin_wayland_wrapper`, `js:`
   lines). Unload it with `…Scripting.unloadScript focuslog`.
4. Calibration: `xclip -selection clipboard` caused no activation. `wl-copy` caused
   `wl-copy | wl-clipboard`, then focus went back to Konsole.
5. During Daniel's dictation the log shows no `wl-copy` (Hebrish's 0.7.4 fix holds). Every paste
   is followed by two `wl-paste | wl-clipboard` activations.

## Ruled out

- **Hebrish still runs wl-copy:** no `wl-copy` activations during dictation. (V)
- **The overlay:** `"overlay": "off"` in `~/.config/hebrish/config.json`. (V)
- **The uinput Ctrl+V itself:** the activations are wl-paste's toplevel, not a change of
  Konsole's focus by the key event. (V)

## Fix

Nothing to fix in Hebrish's clipboard path. Ways to avoid it:

- Paste shortcut `ctrl+shift+v` (Settings → paste shortcut) when dictating into terminals. Konsole
  then pastes from its own clipboard as the focused client and sends the text as a bracketed
  paste, so Claude Code never sees Ctrl+V and never runs wl-paste. (I, not yet tried)
- A wl-clipboard that binds `ext_data_control_manager_v1` would fix it for every app. Not in
  Ubuntu 26.04's archive (2.2.1 only, 2026-10-22).

## Verified / not verified

- (V) The two activations per paste above, in two Konsole windows both running Claude Code.
- (I) The flicker happens only with apps that read the clipboard through wl-paste on Ctrl+V.
  Not yet checked by dictating into a non-terminal window (Kate, a browser).
- (I) The `ctrl+shift+v` workaround; not yet tried.

## Related

- [2026-10-22-paste-flicker-kde.md](2026-10-22-paste-flicker-kde.md): the first cause (Hebrish's
  own wl-copy), fixed in 0.7.4.
