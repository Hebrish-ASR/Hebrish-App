---
date: 2026-10-22
platform: desktop-linux
environment: KDE Plasma 6.6.6 (KWin 6.6.6) Wayland, Ubuntu 26.04.1, wl-clipboard 2.2.1-2build1, xclip 0.13-4build1
component: desktop/hebrish/inserter_linux.py (clipboard_command)
affected: "<= 0.7.3 on compositors without zwlr_data_control_manager_v1"
fixed_in: "0.7.4"
status: fixed
---

# Focused window's title bar flickers on every paste (KDE Wayland)

## Symptom

Daniel, 2026-10-22, dictating into a terminal: "a little but very noticeable flicker" at the top
of the window each time Hebrish pasted. With insert-as-you-go that is many times a minute. It was
first noticed with 0.7.0's word-by-word Shakshuka pastes and logged then as "cause not
established" (`desktop/docs/maintaining.md`, 0.7.1).

## Cause

`wl-copy` stole focus to set the clipboard. (V)

- A client can set the Wayland clipboard without having focus only through a data-control
  protocol. KWin 6.6 advertises `ext_data_control_manager_v1` and no longer advertises
  `zwlr_data_control_manager_v1` (`wayland-info`: 65 globals, `zwlr` absent).
- wl-clipboard 2.2.1, Ubuntu 26.04's version and the only one in the archive, binds only the wlr
  protocol. Without it, wl-copy falls back to mapping a toplevel and taking keyboard focus.
- The focused window therefore went inactive and active again on every paste: the title-bar
  flicker.

## How it was found

1. `inserter_linux.LinuxInserter.insert()` is: `copy_to_clipboard()` (subprocess), 120 ms wait,
   a Ctrl+V chord on Hebrish's long-lived uinput device. The uinput device is created once at
   start, so the only per-paste component that touches the compositor is the clipboard tool.
2. `XDG_CURRENT_DESKTOP=KDE`, so `clipboard_command()` picked `wl-copy` (only GNOME went to xclip).
3. `wayland-info | grep data_control` gave only `ext_data_control_manager_v1`.
4. `echo probe | WAYLAND_DEBUG=1 wl-copy` showed the fallback directly: the registry announces
   `ext_data_control_manager_v1` but wl-copy never binds it. Instead it binds `xdg_wm_base`, calls
   `wl_seat.get_keyboard`, and creates `xdg_toplevel` with `set_title("wl-clipboard")`.
5. `xclip -selection clipboard` with a Wayland-native window focused, then `wl-paste`, returned
   the text: KWin's XWayland bridge accepts the X11 selection from an unfocused X client. xclip
   owns the selection from an unmapped window, so nothing gets focus.

## Ruled out

- **The uinput Ctrl+V:** a key event on an existing device doesn't change focus, and the device
  isn't recreated per paste (`LinuxInserter.__init__`). (I, from the code)
- **The overlay:** it is an XWayland override-redirect window that can't take focus
  (`maintaining.md`, "Floating overlay"), and the protocol trace above already shows a toplevel
  taking focus. (I)
- **"KWin has data-control, so wl-copy is fine":** the 0.3.0 Wayland table said so and marked it
  (V) KDE. That was the wlr protocol on an older KWin; KWin 6.6 offers only ext. A row marked
  verified can go stale when the compositor is upgraded.

## Fix

Commit `99bd061`, released as desktop 0.7.4 (tag `desktop-v0.7.4`).

- `wayland_globals()` reads the compositor's global list straight off the Wayland socket:
  `wl_display.get_registry` and `wl_display.sync`, collecting `wl_registry.global` until the sync
  callback's `done`. It needs no dependency, and its result is cached for the life of the process.
- `clipboard_command()` uses `wl-copy` only if `zwlr_data_control_manager_v1` is advertised
  (wlroots, Hyprland). Otherwise xclip comes first, wl-copy only when xclip is missing. The old
  `XDG_CURRENT_DESKTOP == GNOME` check is gone: Mutter has neither protocol, so it takes the xclip
  route through the same test.

## Verified / not verified

- (V) The probe returns the same 65 globals as `wayland-info` on KWin 6.6.6, and picks xclip.
- (V) `copy_to_clipboard()` then `wl-paste` round-trips the text on KDE Wayland.
- (V) Tests: `desktop/tests/test_inserter_linux.py` (registry parsing against a fake socket with
  a message split across reads; tool choice for wlr, ext-only, none, no xclip, X11). The full
  suite passed: 144 locally, and Linux CI on the tag.
- (V) 0.7.4 installed from the APT repo on the reporting machine and restarted.
- (V) Hebrish no longer causes a focus change (KWin activation log, 2026-10-22). Pasting into a
  terminal running Claude Code still flickers, because Claude Code's own `wl-paste` takes focus:
  [2026-10-22-paste-flicker-claude-code.md](2026-10-22-paste-flicker-claude-code.md).
- (I) GNOME behaves the same as before (it already used xclip); not run on GNOME.
- If a later wl-clipboard learns ext data-control, wl-copy would work on KWin again. There is no
  need to switch back: xclip works everywhere XWayland runs.

## Related

- `desktop/docs/maintaining.md`, "Wayland" table, row "Clipboard while unfocused".
- Parlance (`Parlance-Dictation`, same code lineage) has the same `clipboard_command()` and the
  same bug; not fixed there (Daniel, 2026-10-22).
