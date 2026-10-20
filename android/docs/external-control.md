# External control: intents and buttons (0.6.0, 2026-10-20)

Hebrish can be started, stopped and restarted from outside the app: from automation apps
(Tasker, MacroDroid, Key Mapper), from adb, and from physical buttons (a Bluetooth shutter
remote, a keyboard, a headset or media remote). Code: `app/.../Remote.kt`, consumed by
`FloatingMicService.onRemote` and `onKeyEvent`.

**Requirement: the floating mic must be on** (Settings → Accessibility → Hebrish floating mic).
It is the part of the app that is always running, so it is the receiver. With it off, broadcasts
go nowhere and keys are not seen. The "Sound, microphone and buttons" screen warns when it is off.

Status: compiled (V, 2026-10-20). Not yet run on a device (I for all runtime behaviour below).

## Broadcast intents

Package `app.hebrish.dictation`. Send as a broadcast, not as an activity or service intent.

| Action | Intent action | Effect |
| --- | --- | --- |
| TOGGLE | `app.hebrish.dictation.action.TOGGLE` | Idle: start a take. Recording: stop and transcribe (same as tapping the mic). |
| START | `app.hebrish.dictation.action.START` | Start a take if idle; ignored otherwise. |
| STOP | `app.hebrish.dictation.action.STOP` | Stop and transcribe the open take; ignored when idle. |
| RESTART | `app.hebrish.dictation.action.RESTART` | Throw the open take away and start a new one into the same field (double pip, amber flash). Idle: start a take. |
| PAUSE | `app.hebrish.dictation.action.PAUSE` | Pause or resume the open take. |
| DISCARD | `app.hebrish.dictation.action.DISCARD` | Drop the open take without transcribing. |

If no model is installed or the mic permission is missing, any action except STOP and DISCARD
behaves like a tap on the mic, which shows the explanation.

```bash
adb shell am broadcast -a app.hebrish.dictation.action.TOGGLE  -p app.hebrish.dictation
adb shell am broadcast -a app.hebrish.dictation.action.RESTART -p app.hebrish.dictation
```

`-p` (explicit package) is recommended; the receiver is registered at runtime with
`RECEIVER_EXPORTED`, so implicit broadcasts reach it too. No extras are read.

- **Tasker:** Task → System → Send Intent. Action as above, Package `app.hebrish.dictation`,
  Target **Broadcast Receiver**.
- **MacroDroid:** Action → Connectivity → Send Intent, Target **Broadcast**, same action and package.
- **Key Mapper:** map a key to the action "Send intent", type **Broadcast receiver**. Useful when
  a button sends a key Hebrish should not bind itself (e.g. one the system also uses).

## Buttons (Learn keys)

Settings → "Sound, microphone and buttons" → Buttons. Tap **Learn** next to an action, then press
the button; its key code is stored (`Prefs.keyFor`, key `key_<ACTION>`). **Clear** removes it.

- Only bound keys are consumed; every other key reaches the app as usual. Back, Home and Recents
  are never bound.
- Acts on key down, once; holding a key does not repeat the action.
- Key filtering needs `flagRequestFilterKeyEvents`, added in 0.6.0. **After upgrading from 0.5.x,
  turn the floating mic off and on again** in Accessibility settings, or Android may not deliver
  keys to it.
- Bluetooth shutter remotes (the cheap "AB Shutter3" kind) are HID keyboards that send
  VOLUME_UP and/or ENTER. Binding VOLUME_UP means the volume-up key on the phone triggers it too.
  If that matters, map the remote with Key Mapper (which can tell devices apart) to a broadcast
  instead.
- Headset/media buttons arrive as MEDIA_PLAY_PAUSE or HEADSETHOOK only when no media app has
  claimed them (I).

## Feedback while controlling blind

Optional beeps (off by default) and vibration (on): start = rising two tones, stop = falling,
restart = quick double pip, discard = one low tone (`Feedback.kt`). A restart also flashes the
floating mic's bar amber with "↺ New take" for one second, so it is visible with beeps off.
