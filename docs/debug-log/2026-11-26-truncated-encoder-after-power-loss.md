---
date: 2026-11-26
platform: desktop-linux    # Android ported the same day
environment: Ubuntu, Hebrish desktop 1.046 (.deb), ext4 on LVM
component: desktop/hebrish/model_store.py, desktop/hebrish/ui/app.py
affected: "<= 1.046"
fixed_in: "desktop 1.047, Android next release (both unreleased)"
status: fixed
---

# The app can't load the model

## Symptom

After a restart on 2026-11-26 every take failed with nothing pasted. The journal showed
`transcript '' err=RuntimeError('Model not loaded')` for each piece. The selected model was Sabich
(`sabich-rolling`), version Sabich v5.7 (r73-roll, revision `30fef8d`), installed at 04:45 local time that morning. (V)

## Cause

`Sabich v5.7-30fef8ddfdba/encoder.int8.onnx` was 188,743,680 bytes (exactly 180 MiB). Its manifest says 652,282,308,
and its SHA-256 didn't match. (V) The download had verified: `hebrish-model download sabich-rolling --replace`
printed `verifying encoder.int8.onnx` and `installed to ...` at 04:45 (02:45 UTC). (V) The encoder's change time is
04:45:42.51 (the rename), and the previous boot's journal ends at 04:45:42, so the machine went down about one
second after the rename. (V) `fetch_files` never called fsync, so the rest of the verified file was still only in the
page cache when power went, and ext4 kept the renamed file with only the part already written back. (I: the
mechanism; the timing and sizes are V.)

The app then treated it as installed (`installed()` only checked that `manifest.json` parses). sherpa-onnx failed on
the truncated encoder, and every later take raised "Model not loaded". The previous version (v5.6) had been
deleted by `--replace`, so there was nothing to fall back to. (V)

## How it was found

1. Journal: `journalctl --user | grep hebrish` showed the "Model not loaded" tracebacks after the restart. (V)
2. Model folder: `ls -l ~/.local/share/hebrish/models/sabich-rolling/*/`. The encoder size, compared with
   `manifest.json`, then checked with `sha256sum`. (V)
3. No app code writes model files outside `fetch_files`, which checks size and SHA-256 before the rename, so the
   file must have shrunk after installation. (V, by grep for every writer)
4. `stat` (birth 04:44:34, modify 04:45:41, change 04:45:42) against `journalctl --list-boots` (previous boot
   ended 04:45:42; next started 11:19:54). (V)

## Ruled out

- A bad file on the CDN or a broken release: the same manifest's files downloaded again and all four SHA-256s
  match. (V)
- A download that skipped verification: the CLI output shows "verifying" for every file. (V)
- Disk errors: no ext4 or NVMe errors in `dmesg`, or in the previous boot's journal. (V)

## Fix

`model_store`: fsync each verified `.part` and the folder around the rename; `manifest.json` goes through a
temporary file, fsync and replace. `installed()` skips installs whose files don't match their manifest sizes
(`damaged_files`), and `damaged()` lists them. `hebrish-model status` shows them, and `download` repairs them.
`ui/app.py` `_redownload_damaged`: with no complete install of the selected model, a damaged one is downloaded again
automatically (status line and a notification). The rule is in `desktop/docs/maintaining.md`, "Downloads are flushed
to disk".

Repair on the affected machine: `PYTHONPATH=desktop python3 -m hebrish.model_store download sabich-rolling` from the
fixed checkout refetched only the encoder. The installed 1.046 CLI reports "up to date", because it doesn't check
sizes.

## Verified / not verified

- (V) Two new tests in `desktop/tests/test_model_store.py`. Desktop suite: 764 passed; `test_cleanup.py::test_utilities_rows_and_choice`
  fails with and without this change (pre-existing).
- (V) After the repair, all four files match the manifest's SHA-256, and the app restarted, loaded and transcribed a take.
- (I) That fsync prevents a repeat: no power cut was simulated.
- Android had the same gap: model downloads (not app updates) didn't sync before the rename. Ported on 2026-11-26
  (unreleased): `ModelStore.sync`, `ModelStore.damaged`, `ModelRepair`; see `android/docs/maintaining.md`, "Damaged
  models are downloaded again". (I) It compiles in CI and has a JVM test; it hasn't been run on a device.

## Related

- `docs/debug-log/2026-11-16-model-downloads-time-out.md` (the download retry loop this sits in).
