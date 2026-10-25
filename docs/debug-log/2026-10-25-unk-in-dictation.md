# `<unk>` in dictated text (2026-10-25)

**Report (Daniel, 2026-10-25):** desktop dictation now and then puts in junk like "<uk>".

**Found:** six `<unk>` in `~/.local/share/hebrish/history.db`, all Sabich v2.0 (app 0.7.5 to
1.003, `sherpa_offline_transducer`), at a clause break: "then<unk>and don't mention…",
"manually<unk> we can add him". Searched with
`sqlite3 -readonly history.db "select … where text like '%<unk>%'"`; the only bracketed token in
the history is `<unk>`.

**Cause:** `<unk>` is token 0 of the model's BPE vocabulary. Training sentences with `;` (eight in
the public dataset, all "…is; he is…") tokenize to it, so the model writes it at that kind of
pause. Details and the training-side fix: ASR-Training `docs/training.md`, "`<unk>` at clause breaks".

**Fix:** `drop_unk` (desktop `hebrish/engine.py`, applied to every decode: offline pieces and
streaming) and `Transcriber.dropUnk` (Android `core`, `decode` and `transcribeAfter`) replace it
with a space. Test: `desktop/tests/test_live.py::test_unk_never_reaches_the_text`.

**Ruled out:** a paste or keyboard-layout artefact (it is in History, which stores the decoder's
text before insertion); LibriSpeech-PC replay text (no `;`, dashes or quotes in train-clean-100).
