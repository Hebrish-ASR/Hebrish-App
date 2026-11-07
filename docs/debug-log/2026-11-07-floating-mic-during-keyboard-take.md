---
date: 2026-11-07
platform: android
environment: found in use by Daniel; no device attached when this was fixed
component: android/app/src/main/java/app/hebrish/dictation/FloatingMicService.kt, VoiceImeService.kt
affected: "<= 1.026"
fixed_in: "unreleased"
status: fixed
---

# The floating mic doesn't start recording while a keyboard take is open

## Symptom

Start a take in the voice keyboard, then decide to use the floating mic: tapping it does not start a recording there.

## Cause

(V, from the code) `VoiceImeService` and `FloatingMicService` each keep their own `state`, `recorder` and `take`, and
neither knew about the other. With a keyboard take open, the floating mic's `state` was still `IDLE`, so its
`startRecording` opened a second `AudioRecord` in the same process while the first kept capturing. They also share
`Mic`: whichever take ended first called `Mic.release` and closed a Bluetooth link the other could still be using.

(I) What the user sees then comes from Android's concurrent capture rules, which decide which of the two
`AudioRecord`s gets audio. That was not observed: no device was attached and no logs were taken.

## How it was found

Reading both services' start paths after Daniel's report (2026-11-07). Not reproduced on a device.

## Ruled out

- Separate processes (V): neither service sets `android:process` in the manifest, so a direct call between them works.
- Shared decoding (V): each `TakeDecoder` has its own single-thread executor, so one take's decoder can't block or
  cancel the other's.

## Fix

Each service's `startRecording` first calls the other's `yieldMic()`, which drops a take open there. It runs before
`Mic.prepare`, so the other side's `Mic.release` can't close a link opened for the new take. The rule is in
`android/docs/maintaining.md`, "One open take across the keyboard and the floating mic".

## Verified / not verified

- (V, 2026-11-07) Compiles (`:app:testFdroidDebugUnitTest`, JDK 21).
- (I) The symptom is gone on a phone: not yet tried. If the floating mic still doesn't record after this, the cause is
  something else, and the capture rules above should be checked with `adb shell dumpsys audio`.

## Related

R-2026-11-07-1, B-97.
