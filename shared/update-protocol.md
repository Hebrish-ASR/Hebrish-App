# Model catalogue, updates, and model quirks (both apps)

Written 2026-10-18 for one model; catalogue added 2026-10-19. (V) = verified, (I) = inferred.

Both apps read the same catalogue (since 2026-10-21 [`catalogue.json`](catalogue.json), schema 2), download the same files from the same places, and use
the same rule to decide whether a new version is out. Android: `ModelStore.kt` /
`ModelDownload.kt`. Desktop: `hebrish/model_store.py`. `desktop/tests/test_shared.py` fails
if either app's bundled catalogue drifts from it, or `models.json` from it.

## Catalogue v2: lines and variants (2026-10-21)

[`catalogue.json`](catalogue.json) (`schema: 2`) is what **Android 0.7.0+ and desktop 0.6.0+**
read; they bundle it (Android: gradle `copyCatalogue` into assets; desktop:
`hebrish/data/catalogue.json`, byte-identical) and re-fetch `catalogue_v2_url` (this file on
`main`, raw GitHub) on every update check, exactly as schema 1 below. Cache: desktop
`<data>/catalogue-v2.json`, Android pref `catalogue_v2`. **`models.json` (schema 1) stays,
unchanged in shape, for older builds**, which reject any schema but 1; `test_shared.py` fails if a
schema-1 model differs from its v2 variant (repo, subdir, manifest_url, version_label, status).

Why (Daniel, 2026-10-21): one line (Sabich) now has versions on several base models, and users
need to see them as a speed/accuracy choice inside the line, with a recommendation each.

Shape (abridged; `_comment` in the file is the field reference):

```json
{"schema": 2, "catalogue_v2_url": "…/main/shared/catalogue.json", "recommended": "sabich",
 "version_file": "version.json", "tiers": {"estimate": true, "speed": "…", "accuracy": "…"},
 "engines": {"sherpa_offline_transducer": {"name": "…", "files": ["encoder.int8.onnx", "…"], "model_type": "nemo_transducer"},
             "sherpa_online_transducer": {…}, "qwen3_asr": {…}, "asr4all": {…}},
 "lines": [{"id": "sabich", "name": "Sabich", "summary": "…", "card": "https://hebrish.app/models/sabich",
            "variants": [{"id": "sabich", "name": "Sabich", "base_model": "nvidia/parakeet-tdt-0.6b-v2",
                          "size_label": "0.6B", "engine": "sherpa_offline_transducer", "status": "available",
                          "platforms": ["android", "linux", "windows"], "devices": ["phone", "desktop"],
                          "requirements": {"ram_mb": 1500, "gpu": null}, "hardware": "Phone or computer, …",
                          "download_mb": 661, "speed": 3, "accuracy": 4,
                          "recommendation": "Start here: …", "repo": "Hebrish/Sabich-sherpa-onnx-int8",
                          "subdir": "", "card": "…", "manifest_url": "https://cdn.hebrish.app/models/parakeet-sabich/latest.json"}]}]}
```

- **Lines** are what a model is trained for: `sabich` (everything), `jachnun` (code-switching
  only), `shakshuka` (streaming), `stock`. **Variants** are the line on a base model, named
  `<Line>-<Base>-<Size>` (ASR-Training `docs/training.md`, "Variants on other bases keep the line
  name"). Variant ids are the permanent ids of schema 1 (`sabich`, `codeswitch`, `stock`) plus new
  ones (`sabich-parakeet-110m`, `sabich-qwen3-asr-1.7b`, `sabich-canary-qwen-2.5b`,
  `sabich-asr4all-m`, `sabich-asr4all-s`, `shakshuka`); they name `models/<id>/`, so never rename or reuse one.
- **Supported engines.** Each app has a set (`SUPPORTED_ENGINES`: Android `Catalogue.kt`, desktop
  `model_store.py`; the test keeps them equal). Both are `{"sherpa_offline_transducer"}` as of
  0.7.0 / 0.6.0. A variant is downloadable only if its engine is supported, the app's platform
  (`android`, `linux`, `windows`) is in `platforms`, and `status` is `available` with a `repo` or
  `manifest_url`. Everything else is listed greyed with `runs_on` and a card link. In code,
  `models()` / `Data.models` hold only supported variants, so the download, select and update
  paths below never see the others; `lines()` / `Data.lines` hold all of them for display.
- `status` is about publication, independent of the engine: Qwen3-ASR is `available` (published
  on HF) but no app can run it yet.
- **`speed`, `accuracy` (1–5) and `gradient` (0 = smallest and fastest, 100 = most accurate) are
  estimates**, the same numbers as hebrish.app/models/choose (Hebrish-Website
  `data/variants.json`); both apps print "(estimates)". `test_shared.py`
  `test_numbers_and_rules_match_the_website` compares them when the website repo is checked out
  next to this one (skipped in CI). For reference, best val WER (ASR-Training
  `data/checkpoints.json`; val, not test): Sabich r7-all 4.63%, Shakshuka r8-nemotron-all 6.66%,
  Sabich-Parakeet-110M r8-ctc110m-all 9.43%.
- `requirements.gpu` is `null` or `{vram_gb, backends}` (`cuda`, `hip`, `vulkan`); `devices` is a
  subset of `wearable`, `phone`, `desktop`. Display only; the chooser does not read them.
- **`chooser.rules`** is the site's decision list, copied verbatim except `jachnun` → `codeswitch`
  (2026-10-21): checked in order, first match wins, an absent `when` key matches anything. Form:
  device `phone|computer|wearable`, gpu `none|amd|nvidia|apple`, vram bucket `4|8|12|16` (GB,
  rounded up), priority `speed|balanced|accuracy`, live `true|false`. Each rule has `pick`, `how`,
  `reason`, optional `runner_up`, `runner_how`, `note`. The desktop's Help me choose
  (`model_store.recommend`) uses it; when the pick isn't runnable in the app it names it with its
  `how`, then the best variant the app can run (pick, else runner-up, else `recommended`). **Edit
  the rules on the site and here together.**
- `feature_dim` (offline sherpa variants): 128 for the 0.6B models, 80 for Sabich-Parakeet-110M;
  both apps pass it to sherpa-onnx. (V, 2026-10-21, sherpa-onnx 1.13.8 Python) sherpa-onnx also
  reads it from the NeMo encoder metadata and that wins: the 110M decoded the stock repo's
  `test_wavs/0.wav` identically with 80 and 128, so desktop builds before 0.6.1 (which pass 128)
  and Android 0.7.0 (which passes 80 for every model) run it correctly.
- No pick yet: the first downloaded supported model (recommended first), else `recommended`. So
  a desktop install that ran on schema 1's `default` (`stock`) without an explicit pick keeps it.
- **Publishing a planned variant**: flip its `status` to `available` and push; no app release when
  its engine is already supported. Done for Sabich-Parakeet-110M on 2026-10-21 once
  `https://cdn.hebrish.app/models/parakeet-sabich-110m/latest.json` returned 200 (V: desktop code
  path fetched it, downloaded 136 MB, SHA-256 checked, loaded at 80 mels and transcribed
  correctly). The HF sherpa repos of the new variants are **gated** (checked 2026-10-21:
  `…-110M-sherpa-onnx-int8`, `Shakshuka-sherpa-onnx-int8`), so the apps can only use the CDN
  `manifest_url`. The CDN manifests carry extra keys (`recognizer`, `model_type`, `feature_dim`,
  `chunk_ms`) that the apps ignore. A variant whose engine no app has needs an app release that
  adds it (phase 2): Shakshuka (`sherpa_online_transducer`, published and `available`, 560 ms
  chunks, 128 mels), Sabich-Qwen3-ASR-1.7B (`qwen3_asr`), Sabich-Canary-Qwen-2.5B (`nemo_salm`),
  Sabich-asr4all-S/-M (`asr4all`). Canary-Qwen and asr4all were flipped to `available` on
  2026-10-21 once their HF pages returned 200 (gated, by access request); still not downloadable
  in the apps.

## The catalogue (schema 1, builds up to Android 0.6.0 / desktop 0.5.2)

[`models.json`](models.json) (`schema: 1`) lists every model with an `id`, `name`,
`summary`, `status` (`available` or `planned`), and for available ones the HF `repo`,
`subdir` (may be empty) and optional `version_label`. Shared fields: `files` (the four the
recognizer loads), `version_file`, `default` (the id selected on a fresh install).

- Each app ships the file inside its package and, on every update check, re-fetches
  `catalogue_url` (this file on `main`, raw GitHub). A copy that parses with `schema == 1`
  replaces the cached one; anything else is ignored. **A new model therefore needs no app
  release**: publish the HF repo, flip the entry to `available`, push.
- `planned` entries are shown as "coming soon" and can't be selected or downloaded.
- Ids are permanent: they name the on-disk folder (`models/<id>/`). Never reuse or rename one.

| id | repo | subdir | label without version.json |
| --- | --- | --- | --- |
| `stock` | `csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8` (k2-fsa's int8 export of NVIDIA's release; static since 2025-08-16) | *(root)* | `v2` |
| `codeswitch` | `Hebrish/Jachnun-sherpa-onnx-int8` (since 2026-10-19; named `Hebrish/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching-sherpa-onnx-int8` until 2026-10-20, which redirects with 307) | *(root)* | `rev <sha7>` |
| `sabich` | `Hebrish/Sabich-sherpa-onnx-int8` (Sabich v1.0, run `r7-all`, the kitchen-sink line: code-switching plus tech; added 2026-10-20). Apps 0.2.2+ use its `manifest_url`, `https://cdn.hebrish.app/models/parakeet-sabich/latest.json`; Android has no `BUNDLED` manifest for it, so `checkLatest` resolves it before the first download | *(root)* | from `version.json`: `Sabich v1.0` |
| `tech`, `personal` | not in Hebrish: fine-tunes without Hebrew (Boxty) belong to Parlance | | |

**Since 0.2.2 (2026-10-20): the Hebrish CDN.** A catalogue entry may carry `manifest_url`; apps
0.2.2+ use it in place of the Hugging Face API. One GET of
`https://cdn.hebrish.app/models/parakeet-codeswitch/latest.json` returns `{schema, model,
version, run, revision, base_url, files: {name: {size, sha256}}}`; each file is fetched from
`base_url + name` (Range-resumable, SHA-256 checked as before; `tokens.txt` has `sha256: null`,
checked by size, like the HF tree). `revision` is kept equal to the HF commit the files came
from, so an install from Hugging Face is the same version (`v1.0-bb137e504b97`) and is not
re-downloaded. Version folders under `models/<model>/<version>/` on the CDN never change; a new
version is a new folder plus a new `latest.json` (cache 5 min). `repo` stays in the entry for
apps up to 0.2.1. Uploading: the `r2-upload` skill (voice-ops).

**2026-10-19: moved to the mirror.** The main repo `danielrosehill/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching`
became **gated** (manual access requests), so its `sherpa-onnx/int8/` returns 401 to the apps.
The catalogue now points at the ungated mirror `Hebrish/…-sherpa-onnx-int8`, files at the root,
with a `version.json` added there (`{"version": "v1.0", "run": "r6-en30"}`, HF commit `bb137e50`).
Apps that read this catalogue (Hebrish 0.2.x) follow it on their next update check; older
builds that hard-code the main repo path (Voice To Hebrish, Parlance 0.1.x) cannot download the
code-switching model any more. **A model release must now update the mirror and its
`version.json`**, not just the main repo. The paragraph below describes the layout before the move.

For `codeswitch`, the fine-tune repo's `export_sherpa` writes the four files plus
`version.json`. **Don't move that folder**: installed apps (including Voice To Hebrish, the
predecessor) check this exact path. The separate `…-sherpa-onnx-int8` repo is a mirror for
other apps; neither app reads it.

## Deciding there is an update

1. `GET https://huggingface.co/api/models/<repo>/revision/main` returns `sha`.
2. `GET https://huggingface.co/api/models/<repo>/tree/<sha>/<subdir>` (no trailing segment
   when `subdir` is empty) returns each
   file's `size` and `lfs.oid` (the SHA-256). `tokens.txt` is a plain git file with no
   `lfs`, so only its size is known.
3. Optionally, `GET https://huggingface.co/<repo>/resolve/<sha>/<subdir>/version.json`
   returns `{"version": "v4", "run": "r4-en30"}`. It is only the label. If it is missing,
   the label is the entry's `version_label`, else `rev <sha7>`.
4. Offer an update **only if the weights differ** from the installed ones (SHA-256, or size
   for `tokens.txt`). Never offer one just because `main` moved: model-card and eval
   commits move it many times a day (10 on 2026-10-18 alone, none of them weight changes).

## Installing it

- Download into `models/<id>/<version>-<sha12>/`, pinned to the `sha` from step 1, so a push in
  mid-download can't mix versions.
- Use `.part` files that resume, and check free space first.
- Verify each file's SHA-256.
- Only then switch to the new model. The previous one stays usable until that point.
  - Android always deletes the old folder after switching.
  - Desktop keeps it unless *Keep previous versions* is off.

Each model keeps its own versions; switching models never deletes another model's files
(the user deletes them explicitly).

## Model quirks the apps must work around

Both were measured on the code-switching model (sherpa-onnx int8, greedy search) on 2026-10-18 (V).

- **It needs ≥0.6 s of trailing silence.** With less, it dropped the end of the audio,
  sometimes a whole final sentence. 0.3 s of padding was not enough; 0.6 s and 1.0 s were.
  Both apps pad every decode with 1.0 s (desktop since 0.1.0; Android since 0.5.0).
- **Short pauses between sentences can swallow speech.** Two sentences 0.3 s apart in one
  decode lost the first half of the second sentence, though it decodes perfectly alone.
  With gaps ≥0.6 s nothing was lost. Since 0.2.0, desktop stretches inner pauses of
  0.12–0.6 s to 0.6 s before decoding (`engine.stretch_pauses`; measurements in
  `desktop/docs/maintaining.md`). Android doesn't yet; its takes are short dictations, where
  this matters less (I). Stock Parakeet is assumed to share both quirks (same architecture
and decoder; not measured) (I); the padding and stretching are applied to every model.
