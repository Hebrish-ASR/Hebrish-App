---
date: 2026-11-25
platform: desktop-linux
environment: KDE Plasma 6 (KWin) Wayland, Ubuntu 26.04, wl-clipboard 2.2.1-2build1, xclip 0.13-4build1
component: desktop/hebrish/inserter_linux.py
affected: "<= 1.046"
fixed_in: "unreleased (after 1.046)"
status: fixed
---

# Every paste fails with "Install wl-clipboard and xclip" although both are installed

## Symptom
After a login, dictation transcribed but nothing was pasted: `RuntimeError: Install wl-clipboard
and xclip`.

## Cause
(V) The running app's environment had no `WAYLAND_DISPLAY`, `DISPLAY` or `XAUTHORITY`, so
`clipboard_command()` found neither tool usable and raised the missing-package error.
(I) Start at login is an XDG autostart entry. systemd started it in the same second as
`plasma-kwin_wayland.service`, before the compositor published the display variables to the user
manager; the process keeps that environment for life. `graphical-session.target` had been reached
6 s earlier, and the generated unit orders only after that.

## How it was found
`/proc/<pid>/environ` of the running app, against `systemctl --user show-environment` (which had
all three by then), and the start times in `journalctl --user -b`.

## Ruled out
- **Missing packages:** both installed, in the app's PATH. (V)
- **Old version:** 1.042 was installed, but 1.046 has the same code. (V)

## Fix
`refresh_session_env()` fills missing display variables from `systemctl --user show-environment`
before a clipboard tool is picked (copy and read). With no display at all the error now says so.

## Verified / not verified
- (V) Restarting the unit gave the app all three variables.
- (V) With the variables removed, `clipboard_command()` recovers them and picks xclip. Unit tests.
- Not verified: a login that hits the race with the fix installed. Other readers of `DISPLAY`
  (`ui/overlay.py`, `keyboard_layout.py`) run before the first paste and do not refresh.

## Related
[2026-10-24-xclip-holds-clipboard.md](2026-10-24-xclip-holds-clipboard.md)
