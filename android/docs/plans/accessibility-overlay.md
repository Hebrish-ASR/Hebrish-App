# Plan: accessibility overlay (floating mic)

Status: **built in 0.3.0** (2026-10-20) as `FloatingMicService`; see `docs/maintaining.md`, "Floating mic", for what
was built and what differs from this plan. Written 2026-10-18 at Daniel's request ("save that as a plan").
Statements marked (I) are inferred from Android docs and behaviour, not tested.

## Why

The IME route needs a keyboard switch for every dictation, and switching back is where voice
IMEs most often fail (0.4.0 hardens it; see `docs/maintaining.md`). An `AccessibilityService`
overlay avoids switching entirely: a floating mic sits over any app, HeliBoard stays the
keyboard, and text goes straight into the focused field. Whisperian and Wispr Flow both
offer a floating toolbar for this reason.

## Shape

- `OverlayService : AccessibilityService`, declared with `BIND_ACCESSIBILITY_SERVICE`. Config
  XML sets `canRetrieveWindowContent=true` and listens for `typeViewFocused` and
  `typeWindowStateChanged`.
- Bubble: a `TYPE_ACCESSIBILITY_OVERLAY` window added through `WindowManager`. It needs no
  `SYSTEM_ALERT_WINDOW` permission. It is draggable, its position is saved in Prefs, and it
  is shown only while an editable node has focus (option: always).
- Same engine: `Recorder` plus `Transcriber` in the same process, so the overlay and the IME
  share one loaded model and one download.
- Same take controls as the IME: tap to start and stop, plus pause / restart / discard.

## Insertion, the hard part

1. Find the target: `rootInActiveWindow.findFocus(FOCUS_INPUT)`, which must be
   `isEditable`. Skip `isPassword` nodes.
2. Insert at the cursor. `ACTION_SET_TEXT` **replaces the whole field**, so build
   `before + text + after` from `node.text` plus `textSelectionStart/End`, then
   `ACTION_SET_SELECTION` to put the cursor after the insert. Hint text can come back in
   `node.text` on an empty field. Compare against `hintText` (API 26+) (I).
3. Fallback when SET_TEXT is refused (WebViews, some Compose fields) (I): put the text on
   the clipboard and run `ACTION_PASTE`, then restore the old clipboard. Android 13+ shows a
   "copied" toast each time.
4. Last resort: keep the text as the last transcript (`Prefs.lastTranscript`, already
   there) and show an "Insert" chip on the bubble, which is the IME's Insert-last idea.

## Android constraints to settle before building

- **Restricted settings (Android 13+):** a sideloaded app's accessibility toggle is greyed
  out until App info → ⋮ → *Allow restricted settings*. Setup must walk the user through it.
- **Microphone from a service:** recording while another app is in front needs a foreground
  service of type `microphone` (Android 14+ `FOREGROUND_SERVICE_MICROPHONE`). Starting it from
  a bubble tap counts as a user interaction (I). Check whether an AccessibilityService is
  exempt from the background-start restriction (I).
- **OxygenOS (Nord 3) kills background services:** needs a battery-optimisation exemption and
  probably "allow auto-launch". Document the toggles.
- **RAM:** the 650 MB encoder stays resident only while the process lives. The overlay keeps
  the process alive longer, which makes later dictations faster but uses memory.
- **Play policy** restricts accessibility use to accessibility purposes. That doesn't matter
  for a GitHub-distributed APK, but it rules out the Play Store for this route.

## Order of work

1. Service skeleton plus enable flow (restricted-settings walkthrough), bubble with no audio.
2. Focus tracking: show the bubble only on editable focus.
3. Recording through a foreground service; reuse `Recorder` and `Transcriber`.
4. Insertion (SET_TEXT with selection merge, then paste fallback, then the Insert chip). Test in
   Gmail, WhatsApp, Chrome (WebView) and a Compose app.
5. Setup screen: "Floating mic" section with its status, mirroring the keyboard step.
