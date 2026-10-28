# Visual status indicators

## Question

How should the desktop app (Ubuntu KDE first) show its state outside its own windows, as a
"digital tally light"? Candidates: a screen overlay in a few colours, KDE desktop notifications,
and a USB status light. Colours: recording red, transcribing (processing) amber, a short green
flash when the text is in, off when idle. Request
[R-2026-10-28-3](../../planning/requests.md) (Daniel, 2026-10-28): record the ideas and find the
first steps to build on. Backlog: [I-17](../../planning/backlog.md#ideas-for-future-versions).

## Status

open (2026-10-28). Ideas only, nothing scheduled.

## What the app has today (confirmed from the code, 2026-10-28)

- One state machine: `Controller.set_state` in `desktop/hebrish/ui/app.py` (`idle`, `recording`,
  `busy`), plus `recorder.paused` and the after-Stop "finishing" state behind the amber tray
  icon (B-48). Every indicator below can hang off `set_state` and `_overlay_push`.
- The floating overlay (`ui/overlay.py`) already turns its mic red while listening. On Wayland it
  runs as a child XWayland override-redirect process, which is also where a screen-edge tally
  would have to live: that is the only way the app gets an always-on-top, never-focused surface on
  KDE Wayland.
- `Controller.notify` sends tray balloons (`QSystemTrayIcon.showMessage`), which reach KDE's
  notification server (`org.freedesktop.Notifications`). It is used for errors and updates, not for
  state.

## Findings

| Option | What it gives | Notes | Source |
| --- | --- | --- | --- |
| Screen-edge tally (overlay) | A thin coloured border or corner dot, visible in any app, no hardware | Reuse the overlay child process: one more state, a frameless strip at a chosen edge. Must not take focus or catch clicks (input-transparent) | App code (confirmed) |
| KDE notifications | "Ready" or "Transcribing" popups via `org.freedesktop.Notifications` | Fine for one-off events, poor as a tally: popups stack, stay for seconds and Do Not Disturb hides them. Best kept to "ready" if at all | Inferred from the spec's behaviour; not tested |
| USB status light | A physical red/amber/green light on the desk or monitor | `busylight-for-humans` (Python, Linux and macOS) drives Luxafor Flag/Orb/Mute, ThingM blink(1), Kuando Busylight Alpha/Omega, Embrava Blynclight, BlinkStick, fit-statUSB, MuteMe, MuteSync, Plantronics Status Indicator (16 devices from 9 vendors). On Linux it needs a udev rule (`busylight udev-rules`, installed once as root) | <https://pypi.org/project/busylight-for-humans>, <https://github.com/JnyJny/busylight> (read 2026-10-28, from search summaries; licence and current device caveats not yet checked) |
| DIY light | Any microcontroller LED (serial, HID or USB MIDI) | Linux drives a USB-MIDI device with `amidi`; a serial device takes one byte per state | <https://lists.plug.org.au/pipermail/av/2022q3/001353.html> (read 2026-10-28) |
| Home Assistant / smart bulb | A room light as the "on air" sign | Possible through the hook or the state file below; not built into the app | Inferred |

## Recommendation: first steps, in order

1. **One status feed.** A small `status` module that `set_state` calls with one of
   `idle | recording | paused | transcribing | ready`. It writes
   `~/.local/state/hebrish/status.json` (`{"state", "since", "take"}`), emits a D-Bus signal, and
   can run a user hook command (`status_hook`, e.g. `my-light %s`). Anything (a USB light script,
   Home Assistant, a KDE widget) then works without app changes, so this is what to build first.
2. **Screen-edge tally in the overlay process.** Settings: off / edge (top, bottom, left, right) /
   corner dot, thickness, and whether the green "ready" flash shows (about 0.8 s). Same colours as
   the tray (`style.py` RED, AMBER, GREEN). Input-transparent, so it never catches a click.
3. **USB lights.** An optional extra (`hebrish[busylight]`) on `busylight-for-humans`: Settings →
   *Status light*: none / the first light found, with a Test button that cycles the colours. The
   udev rule goes in the `.deb` (`packaging/`), so there is no root step for users. Needs a light
   to test with: a Luxafor Flag or blink(1) is the cheapest well-supported one.
4. **KDE notifications** only as an opt-in "Text is ready" event, not as a tally.

Android: the floating mic already shows state; a status light there (Bluetooth Luxafor) is not
worth it before the desktop has steps 1 to 3.
