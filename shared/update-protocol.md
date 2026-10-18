# Model source, updates, and model quirks (both apps)

Written 2026-10-18. (V) = verified, (I) = inferred.

Both apps download the same files from the same place and use the same rule to decide
whether a new model is out. The values live in [`model.json`](model.json). Android:
`ModelStore.kt` / `ModelDownload.kt`. Desktop: `voice_to_hebrish/model_store.py`.
`desktop/tests/test_shared.py` fails if either app's constants drift from `model.json`.

## Where the model comes from

`danielrosehill/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching`, folder
`sherpa-onnx/int8/` on `main`. It holds `encoder.int8.onnx`, `decoder.int8.onnx`,
`joiner.int8.onnx` and `tokens.txt` (~660 MB), plus `version.json`. The fine-tune repo's
`export_sherpa` writes all of them. **Don't move this folder**: every installed app checks
this exact path. The separate `…-sherpa-onnx-int8` repo is a mirror for other apps; neither
app reads it.

## Deciding there is an update

1. `GET https://huggingface.co/api/models/<repo>/revision/main` returns `sha`.
2. `GET https://huggingface.co/api/models/<repo>/tree/<sha>/sherpa-onnx/int8` returns each
   file's `size` and `lfs.oid` (the SHA-256). `tokens.txt` is a plain git file with no
   `lfs`, so only its size is known.
3. Optionally, `GET https://huggingface.co/<repo>/resolve/<sha>/sherpa-onnx/int8/version.json`
   returns `{"version": "v4", "run": "r4-en30"}`. It is only the label. If it is missing,
   the label is `rev <sha7>`.
4. Offer an update **only if the weights differ** from the installed ones (SHA-256, or size
   for `tokens.txt`). Never offer one just because `main` moved: model-card and eval
   commits move it many times a day (10 on 2026-10-18 alone, none of them weight changes).

## Installing it

- Download into `<version>-<sha12>/`, pinned to the `sha` from step 1, so a push in
  mid-download can't mix versions.
- Use `.part` files that resume, and check free space first.
- Verify each file's SHA-256.
- Only then switch to the new model. The previous one stays usable until that point.
  - Android always deletes the old folder after switching.
  - Desktop keeps it unless *Keep previous versions* is off.

## Model quirks the apps must work around

Both were measured on v4 (sherpa-onnx int8, greedy search) on 2026-10-18 (V).

- **It needs ≥0.6 s of trailing silence.** With less, it dropped the end of the audio,
  sometimes a whole final sentence. 0.3 s of padding was not enough; 0.6 s and 1.0 s were.
  Both apps pad every decode with 1.0 s (desktop since 0.1.0; Android since 0.5.0).
- **Short pauses between sentences can swallow speech.** Two sentences 0.3 s apart in one
  decode lost the first half of the second sentence, though it decodes perfectly alone.
  With gaps ≥0.6 s nothing was lost. Since 0.2.0, desktop stretches inner pauses of
  0.12–0.6 s to 0.6 s before decoding (`engine.stretch_pauses`; measurements in
  `desktop/docs/maintaining.md`). Android doesn't yet; its takes are short dictations, where
  this matters less (I).
