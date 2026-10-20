# Desktop 0.5.0: plan

Status on 2026-10-21: **built, pushed, not released.** Daniel wants to add a few more things
before the release. Add them under "Still to add", then follow "Release". Delete this file once
0.5.0 is released (the decisions live in `maintaining.md`, "0.5.0").

## Done (main, commits 4425f94 and 79c4443)

From Daniel's feedback on 0.4.0, on Ubuntu (2026-10-21):

| Request | What was built | Where |
| --- | --- | --- |
| Insert as you go on by default, ~10 s | `live_insert_s` default 10; applied once to existing configs | `config.py` `DEFAULTS`, `upgrade()` |
| Branding: "dictation for English speakers in Israel" | Header and splash tagline | `config.TAGLINE` |
| Models page: download button and icon per model, no need to switch first, base Parakeet too | A card per model with its icon and its own Download / Use / Delete | `ui/window.py` `_model_row`; `ui/app.py` `download_model`, `use_model`; `data/icons/model-*.svg` |
| TTS instead of pips; nothing when the transcript lands | Sounds: beeps (softer), voice prompts, or off | `ui/app.py` `cue`; `audio.say`; `data/voice/*.wav` from `scripts/make_voice.py` |
| History off by default, as an option | `keep_history` default false (applied once); History tab only when on | `config.py`; `ui/window.py` `_history_page` |
| Custom model folder, default shown | Models tab, "Where the models are stored": change, move, back to default, open | `model_store.set_root`; `config.models_root`; `ui/window.py` `_set_store` |
| Record into the text box on the main screen; file upload only on the other tab | Dictate tab: Talk, Pause, Discard, editable text box, Output combo. Transcribe tab → File tab (drop zone) | `ui/window.py` `_dictate_page`; `ui/transcribe.py` |
| VAD toggle | Energy VAD, on by default: no-speech takes not decoded, long silences shortened | `engine.has_speech`, `engine.shorten_silences`; `config.vad` |
| Show and switch the mic | Mic in use (real device behind "System default" via `pactl` on Linux), switcher, rescan | `ui/window.py` `_fill_mics`; `audio.default_input_name` |
| Level diagnostics: clipping, good zone | Level meter with zones, peak tick, clip lamp; Test mic | `ui/meter.py`; `Controller.monitor` |
| About: by Daniel Rosehill near the top, link to danielrosehill.com | Byline under the title in the About hero | `ui/about.py` `AUTHOR_SITE` |
| Port to Windows (parity skill) | Shared code; parity matrix written | `../docs/feature-parity.json` |

Verified: 54 tests on Linux, all tabs rendered off-screen, the decode path through the real
`Controller` (silence → "no speech"; speech either side of a 6 s gap decoded). CI run
39516726092 (workflow_dispatch on main): tests on Linux and Windows, the Windows freeze, and the
frozen-exe self-test (model icons and voice prompts bundled) all pass.

Not verified: a live mic (meter, Test mic, VAD on real speech), the voice prompts and new
beeps through real speakers, moving the model folder across disks, any of it on a real
Windows machine.

## Added after the first push (2026-10-21)

- Esc discards a recording take; double tap of the toggle key = Retake (both on by default,
  toggles in Settings → Dictation). Distinct sounds for discard ("doo-doo") and retake.
- Diagnostics tab: tokens per second, × real time, compute per audio second, stop → text
  latency over the last N decodes; CPU, threads, model, memory; Run benchmark; Copy as JSON.
  This laptop: 12.9× real time, 61 tokens/s (`maintaining.md`, "0.5.0 additions").
- Training sentences for "hebrish.app" and the model names: in progress in `ASR-Training` (separate
  repo, not part of this release).

## Still to add / to decide

- GPU inference: not supported today (CPU-only onnxruntime; no ROCm in sherpa-onnx; DirectML on
  Windows would need a DirectML build). Decide whether it is worth it after measuring older
  CPU-only laptops with the Diagnostics tab.
- (Further requests go here.)

## Release (after the additions)

Use the asr-dev `hebrish-release` skill. In order:

1. Bump `hebrish/__init__.py` if the additions warrant it (now `0.5.0`).
2. Rewrite `.github/desktop-release-notes.md` for 0.5.0. It still holds 0.4.0's notes;
   0.4.0 was never tagged, so 0.5.0's notes should cover 0.4.0's changes too.
3. Tag `desktop-v0.5.0` and push the tag: CI builds and attaches the Windows zip.
4. Build the .deb on this machine (`desktop/build-deb.sh`) and `gh release upload` it.
5. Copy both files to the Hebrish CDN and rewrite `downloads/latest.json` (`r2-upload` skill).
   The site's `/get/<platform>` links then follow; no site edit is needed for the links.
6. Website (`Hebrish-App` repo): `changelog.html` entry for desktop 0.5.0.
7. Re-run the parity check: `released` in `../docs/feature-parity.json` becomes 0.5.0 for
   Ubuntu and Windows, and `unreleased.desktop` empties.
8. Optionally port the Android gaps the matrix lists (voice prompts, clip lamp, silent-take
   skip, history, file transcription, author line) and the Parlance twin (`sync-hebrish-to-parlance`).
