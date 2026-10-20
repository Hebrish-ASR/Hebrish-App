# Model catalogue, updates, and model quirks (both apps)

Written 2026-10-18 for one model; catalogue added 2026-10-19. (V) = verified, (I) = inferred.

Both apps read the same catalogue, download the same files from the same places, and use
the same rule to decide whether a new version is out. Android: `ModelStore.kt` /
`ModelDownload.kt`. Desktop: `hebrish/model_store.py`. `desktop/tests/test_shared.py` fails
if either app's bundled catalogue drifts from [`models.json`](models.json).

## The catalogue

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
| `tech`, `personal` | not published yet | | |

**Since 0.2.2 (2026-10-20): the Hebrish CDN.** A catalogue entry may carry `manifest_url`; apps
0.2.2+ use it in place of the Hugging Face API. One GET of
`https://cdn.hebrish.app/models/parakeet-codeswitch/latest.json` returns `{schema, model,
version, run, revision, base_url, files: {name: {size, sha256}}}`; each file is fetched from
`base_url + name` (Range-resumable, SHA-256 checked as before; `tokens.txt` has `sha256: null`,
checked by size, like the HF tree). `revision` is kept equal to the HF commit the files came
from, so an install from Hugging Face is the same version (`v1.0-bb137e504b97`) and is not
re-downloaded. Version folders under `models/<model>/<version>/` on the CDN never change; a new
version is a new folder plus a new `latest.json` (cache 5 min). `repo` stays in the entry for
apps up to 0.2.1. Uploading: the `r2-upload` skill (parakeet-finetune-ops).

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
