---
date: 2026-11-10
platform: android
environment: Pixel 11 (cubs), Android 17 / SDK 37, F-Droid build 1.026 and 1.027; also seen by Daniel on his own phone
component: android/app/src/main/java/app/hebrish/dictation/FloatingMicService.kt
affected: "0.6.0 to 1.028 (every version with a draggable floating mic; 1.010's guard did not help)"
fixed_in: "unreleased (next Android release, 1.029)"
status: fixed
---

# The app crashes when the floating mic is dragged

## Symptom

A user reported "intermittent crashing" on 1.027. It looked like memory pressure, because the
model-memory hotfixes (1.010, 1.011) were the last time this phone was looked at. Daniel then confirmed
that on his phone too, the app crashes when the floating mic is dragged (2026-11-10).

## Cause

The drag re-enters `place()` while `place()` is detaching the bar's children (V, stack trace below):

1. `Drag.onTouch(ACTION_UP)` with `dragging` set calls `savePosition()`.
2. `savePosition()` writes `bubble_y` (`Prefs.setBubbleY`). `apply()` calls the prefs listener
   synchronously: `onSharedPreferenceChanged` → `place()`.
3. `place()` calls `r.removeAllViews()`. The dragged view is still the root's touch target (the
   ACTION_UP is still being dispatched), so `removeAllViewsInLayout` → `cancelTouchTarget` sends it
   ACTION_CANCEL.
4. `Drag.onTouch(ACTION_CANCEL)` still has `dragging == true`, so it calls `savePosition()` →
   `place()` again, inside step 3's `removeAllViews()`. The nested `place()` detaches and re-adds
   every child.
5. The outer `removeAllViewsInLayout` then finishes clearing a child array that the nested call has
   already rebuilt. A child is left with `mParent` set to the root, but the root no longer lists it.
   The outer `place()` then calls `r.addView(c)` and throws `IllegalStateException: The specified
   child already has a parent` (I for the exact interleaving inside `ViewGroup`, V for the re-entry).

It fires when a drag ends and the save changes a stored value (no listener call when nothing
changed), which is why it looked intermittent.

Why 1.010's guard did nothing: it runs `(c.parent as? ViewGroup)?.removeView(c)` before `addView`.
At that point the parent's child list doesn't contain `c`, so `removeView` finds nothing and leaves
`mParent` set (I, from `ViewGroup.removeView` → `indexOfChild` = -1).

## How it was found

Paired with the phone over wireless debugging (QR pairing), then:

- `adb shell dumpsys activity exit-info app.hebrish.dictation`: 15 exits 2026-11-08 to 2026-11-10, all
  `reason=4 (APP CRASH(EXCEPTION))`. None were `LOW_MEMORY` or lmkd kills. The RSS at crash ranged
  from 128 MB to 1.3 GB, so the crashes happened with and without the model loaded. Memory was ruled out (V).
- `adb shell dumpsys dropbox --print data_app_crash`: 16 `app.hebrish.dictation` entries (8 on 1.026,
  8 on 1.027), every one the same exception. The full trace shows the nesting:

```
java.lang.IllegalStateException: The specified child already has a parent. ...
    at android.view.ViewGroup.addView(ViewGroup.java:5225)
    at app.hebrish.dictation.FloatingMicService.place(FloatingMicService.kt:549)
    at app.hebrish.dictation.FloatingMicService.savePosition(FloatingMicService.kt:603)
    at app.hebrish.dictation.FloatingMicService$Drag.onTouch(FloatingMicService.kt:660)   <- ACTION_CANCEL
    ...
    at android.view.ViewGroup.cancelTouchTarget(ViewGroup.java:3147)
    at android.view.ViewGroup.removeAllViewsInLayout(ViewGroup.java:5960)
    at android.view.ViewGroup.removeAllViews(ViewGroup.java:5913)
    at app.hebrish.dictation.FloatingMicService.place(FloatingMicService.kt:526)
    at app.hebrish.dictation.FloatingMicService.onSharedPreferenceChanged(FloatingMicService.kt:373)
    at android.app.SharedPreferencesImpl$EditorImpl.apply(SharedPreferencesImpl.java:521)
    at app.hebrish.dictation.Prefs.setBubbleY(Prefs.kt:185)
    at app.hebrish.dictation.FloatingMicService.savePosition(FloatingMicService.kt:601)
    at app.hebrish.dictation.FloatingMicService$Drag.onTouch(FloatingMicService.kt:660)   <- ACTION_UP
```

## Ruled out

- Memory pressure / lmkd (the first guess): no low-memory exits in `exit-info` (V). The memory
  review of 1.028 found nothing that crashes, only peaks worth trimming: Transcription Mode keeps the
  clean-up and paragraph models until the screen is destroyed, and a note's title model loads alongside the
  ASR model. Not changed here.
- A child listed twice in the `place()` loop (the 1.010 theory): the list has no duplicates (V, code).

## Fix

1.029, `FloatingMicService.kt`:

- `place()` is not re-entrant: a nested call sets `placeAgain` and returns. The outer call runs
  it once more (posted to the main thread) after it finishes. The work moved to `placeOnce()`.
- `Drag` clears `dragging` before calling `savePosition()` on ACTION_UP and ACTION_CANCEL, so the
  ACTION_CANCEL that `removeAllViews()` sends cannot save and place again.

The 1.010 `removeView` guard is kept. It is harmless.

## Verified / not verified

- Compiles: `compileFdroidDebugKotlin`, `compilePlayDebugKotlin`, JDK 21 (V, 2026-11-10).
- Not yet run on a phone. To check: drag the mic and the bar to a new place several times, and
  between the edges, with the bar open and closed. Then confirm that `dumpsys dropbox --print
  data_app_crash` has no new entry.

## Related

- `android/docs/maintaining.md`, "Model memory and the drag crash guard (1.010 hotfix)": the first
  sighting (0.6.0, 14 crashes, 2026-10-29 to 2026-10-31) and the guard that did not fix it.
