---
date: 2026-11-17
platform: models
environment: Desktop 1.039 (Ubuntu, KDE Plasma Wayland), laptop internal mic; model Sabich v4.8 (run r61-roll)
component: model weights (Sabich, app id sabich-rolling); CDN cdn.hebrish.app/models/sabich/
affected: "Sabich v4.8 (r61-roll, HF revision fda3db6a6e38), every app version that installed it"
fixed_in: "CDN rollback to Sabich v4.7 (no app release needed)"
status: fixed
---

# The app stopped recognising any audio input

## Symptom

Starting about 19:50 on 2026-11-17, desktop dictation returned `err='no speech'` for normal takes, or a
fluent sentence that was never said ("I'll be able to use the same number.", "I think that we can't. I think
the two of you can."). One 26 s take came out as "1.3 s of audio" and no words. The log also showed `empty
piece of 8.5 s with speech: decoding it as 3.6 + 4.9 s`, still with no text. Takes worked normally until 18:01
the same day. (V, journal of the running app.)

## Cause

The model. The automatic model update installed **Sabich v4.8** (run `r61-roll`) at 18:35:40, between the last
good take (18:01) and the first bad one (19:50) (V: `update check (all)` at 18:34:55, `idle -> busy -> idle`
18:35:40–18:35:43 = the hot reload, model folder `Sabich v4.8-fda3db6a6e38` timestamped 18:35). v4.8 was
the first release after **tokenizer surgery**: 8 tokens (`@ & + # ( ) _ =`) were added at ids 1024–1031,
which moved `<blk>` from 1024 to 1032 and resized the decoder embedding and the joiner. Why the trained weights
decode badly is not diagnosed (I). The export is internally consistent (see Ruled out), so the fault is in
the training or the surgery itself, not in the packaging. The decision: the surgery is not retried
(ASR-Training docs).

## How it was found

1. Journal (`journalctl --user | grep hebrish`): transcripts fine until 18:01, then no speech and
   hallucinations from 19:50. The take language was English, decided the same way, in both periods (V). No
   model switch was logged, so the model was first assumed unchanged. That was wrong: a hot model *update*
   logs only `update check` and a busy blip, not "model loaded".
2. Daniel suspected the newly trained model. The model store showed `sabich-rolling/Sabich v4.8-…` written at
   18:35 (V).
3. `GET /health` on the local API: `sabich-rolling`, "Sabich v4.8" loaded (V).
4. Switched to Shakshuka v2.1 (`POST /v1/app/models/select {"id":"shakshuka"}`). Daniel's next live take
   transcribed correctly ("That seems to do it") (V).

## Ruled out

- **Export or packaging mismatch.** `tokens.txt` 1,033 lines, `<blk>` last at 1032. The encoder metadata says
  `vocab_size 1032` (v2.4: 1024 with 1,025 tokens, the same convention). Joiner output 1038 = 1,033 + 5 TDT
  durations. Decoder hidden 640 as before (V, onnxruntime input/output shapes, encoder metadata read from the
  file's tail).
- **Mic gain.** A mic-tuning tool was also holding the mic, and the internal mic's volume was 18%
  (−45 dB). Raising it to 100% clipped on room noise (peak 32768). At 18% the raw level was −36 to −48 dBFS
  ambient, and speech registered. The volume was put back to 18%. Hebrish's own capture stream was on the
  right source, unmuted, at 100% stream volume (V, `pactl list source-outputs`). Not the cause: the same
  setup worked with Shakshuka.
- **The app.** 1.039 was installed and running since 10:50, through both the good and the bad periods (V).
- **A wrong turn:** transcribing the app's bundled voice clips (`desktop/hebrish/data/voice/*/*.wav`) through
  `POST /v1/audio/transcriptions` gave the same wrong text under v4.8 *and* Shakshuka. Those clips are not a
  usable model test. Use real dictation audio.

## Fix

Roll the CDN back: `cdn.hebrish.app/models/sabich/` serves Sabich v4.7 again (run `r58-roll`, sherpa int8 HF
revision `835e4ae2132e`; v4.8's files and the browser demo's `onnx/` copy removed). Done from ASR-Training (commits
`61794e8`, `e0324d1`; its `docs/training-log.md`, 2026-11-17), which also withdrew the tokenizer surgery for good and
pointed the rolling line's `init_from` back at r58-roll. The next Sabich release is v4.9; the v4.8 label is not reused.
For about 10 minutes (18:01–18:12 UTC) the CDN served v4.7 files under the v4.8 manifest, because `cdn_release`'s
public re-download of the encoder came back truncated and it stopped before rewriting `latest.json`. An app's sha256
check should have rejected those downloads rather than installing a mix (I).

How v4.8 reached users: since 2026-11-17, incremental runs skip validation, and `training/nebius/finish.sh` releases
a run with `best_val_wer None` with no WER gate ("released unattended … best val WER None", run journal). So nothing
stood between a broken run and the CDN (V, finish.sh lines 73–78). **No app release is needed:** both apps offer an update whenever
the published weights differ from the installed ones (desktop `model_store.needs_update` → `same_weights`;
Android `ModelDownload.updateAvailable` → `sameWeights`, both sha256 per file). They never compare version
numbers, so a lower version in `latest.json` reinstalls like any update (V, code read). Installs on v4.8 move to
v4.7 at their next model check.

## Verified / not verified

- (V) Cause timeline, model identity, export shapes, Shakshuka working live.
- (V) The CDN serves v4.7: `latest.json` and all four files' sha256 checked against the manifest and HF, the
  encoder in full (ASR-Training rollback, 2026-11-17).
- (I) v4.7 decodes well again after the rollback. The desktop app here started its update to v4.7; dictation not re-tested at the time of writing.
- (I) Android installs pick up the rollback. From the code, not run on a device.

## Related

- ASR-Training `docs/training-log.md` / `docs/training.md`: the r61-roll withdrawal and the no-surgery rule.
- `shared/update-protocol.md`: one CDN folder per model, overwritten on publish.
