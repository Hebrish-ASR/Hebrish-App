# Targeted model lists

**Started:** 2026-11-12 (Daniel). Decision: [D-2026-11-12-01](decisions.md). Backlog: I-23.

## The principle

Each app offers the models that fit its hardware. Everything else stays published, on Hugging
Face and on <https://hebrish.app/models>, where anyone can download a build (GGUF, ONNX, NeMo)
for another app. Nothing is deleted. The variant ids stay in `shared/catalogue.json`.

The supported models are **Sabich** (dictation, the default), **Shakshuka** (streaming) and
**Falafel** (voice commands, in two sizes). Those three get continued training. The other Sabich
variants (Qwen3-ASR 1.7B, Canary-Qwen 2.5B, Parakeet 110M, asr4all S/M) stay at their last
version.

## How it works

`offered_on` on a catalogue variant lists the platforms (`android`, `linux`, `windows`) whose
Models screen shows it. If it is absent, the variant is shown on every platform it runs on. A
variant that is not offered stays visible and usable where it is already installed or in use.

| Variant | `offered_on` | Why |
| --- | --- | --- |
| sabich-qwen3-asr-1.7b | none | Proof of concept (one run to compare base models) |
| sabich-canary-qwen-2.5b | none | Not in the main development cycle; desktop GPU only |
| sabich-parakeet-110m | android | Small model for low-end phones; on a computer Sabich itself runs on the CPU |
| sabich-asr4all-s / -m | android | Wearables and very low-power boards |

## Done

- Desktop (Ubuntu, Windows): the Models tab honours `offered_on` (`model_store.listed_lines()`).
  It lists Sabich, Shakshuka, Falafel, Falafel 110M and stock Parakeet. The intro links to
  hebrish.app/models for the full list.

## Still to do

- **Android:** read `offered_on` in `core/Catalogue.kt`, so the Models screen stops listing the
  greyed desktop-only variants (Qwen3-ASR, Canary-Qwen). Decide whether Android keeps
  Sabich-Parakeet-110M and asr4all as a "for older phones" choice or drops them too. Add the same
  link to hebrish.app/models to `models_intro`.
- **Help me choose:** `chooser.rules` still picks asr4all and 110M for phones and wearables. That
  is right for the website's chooser, which covers any device. In the apps, the answer should name
  a model the app offers, or say "on hebrish.app/models" for one it doesn't.
- **Low-resource hardware (Raspberry Pi and similar):** later, a separate small CLI or service
  package for boards and wearables (asr4all, Parakeet 110M; sherpa-onnx or transcribe.cpp on the
  CPU), instead of listing those models in the desktop GUI. Not scheduled.
- **Stock Parakeet:** kept for now as the baseline to compare against. Review whether it still
  belongs in the list.
