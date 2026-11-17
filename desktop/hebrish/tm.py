"""Transcription Mode's text, Qt-free (B-108, 2026-11-17): split out of ui/transcribe.py so the
Transcription tab and the local API (`POST /v1/app/transcribe`) make the same transcript from the
same audio.

`run` is the tab's worker: the engine's pieces (voice detection per `vad`), the disfluency chop and
the personal dictionary per piece, laid out per paragraph mode (paragraphs.Pieces), then the
clean-up model over the whole text when asked, else the paragraph model when that is the mode.
`layout` is the tab's `_finished`, minus the widgets: which text is shown, the raw text kept beside
a saved transcript, the layout actually used, the History extras and the status-line notes.
"""

from dataclasses import dataclass

from . import audio, cleanup, dictionary, disfluency, paragraphs

PARAGRAPH_S = 30        # Time-based: a paragraph about every 30 s of audio (../shared/paragraphs.md)


@dataclass
class Layout:
    shown: str              # the transcript as the tab shows it (and History stores)
    raw: str                # as transcribed, laid out without the paragraph model or clean-up
    flow: str               # the paragraph mode the pieces were laid out in (paragraphs.MODES)
    cleaned: bool
    extra: dict | None      # for History's decode info: the clean-up model that ran
    note: str               # for the status line; starts with a space when not empty


def run(engine, samples, mode: str, *, vad: bool, cancel=None, tidy_id: str | None = None,
        on_progress=None, on_stage=None):
    """Transcribe `samples` (16 kHz mono) on this thread. Returns (pieces, body, err, tidied):
    body is the cleaned or paragraph-model text (None otherwise), err the paragraph model's
    failure (then body is Time-based), tidied the cleanup.Result when clean-up ran."""
    words = dictionary.load()
    fix = dictionary.compile(words)                  # personal dictionary, as in dictation
    # pieces are ~10-25 s; Time-based starts a paragraph every ~30 s of audio. With the Paragraph
    # model they are joined with spaces until the end.
    pieces = paragraphs.Pieces(PARAGRAPH_S * audio.SAMPLE_RATE)
    for text in engine.transcribe_chunks(samples, cancel, vad=vad):
        done, total = engine.last_progress
        pieces.add(fix(disfluency.chop(text)), done, mode)
        if on_progress:
            on_progress(done / total)
    body, err, tidied = None, None, None
    if tidy_id and pieces.items and not (cancel is not None and cancel.is_set()):
        if on_stage:
            on_stage("Cleaning up the transcript…")
        tidied = cleanup.run(pieces.text(paragraphs.NONE), keep=tuple(e["word"] for e in words), aid=tidy_id)
        if tidied.cleaned:
            body = tidied.text
    if body is None and mode == paragraphs.MODEL and pieces.items:
        try:
            body = pieces.text(paragraphs.MODEL, paragraphs.breaker())
        except Exception as e:   # fall back, never lose text
            body, err = pieces.text(paragraphs.TIME), e
    return pieces, body, err, tidied


def layout(pieces, mode: str, body, err, tidied) -> Layout:
    cleaned = tidied is not None and tidied.cleaned
    flow = mode
    if mode == paragraphs.MODEL and pieces.items:
        flow = paragraphs.TIME if (err or body is None or cleaned) else paragraphs.MODEL
    raw = pieces.text(paragraphs.TIME if flow == paragraphs.MODEL and cleaned else flow) if pieces.items else ""
    if cleaned:
        shown = body
    elif mode == paragraphs.MODEL and pieces.items and body is not None:
        shown = body
    else:
        shown = pieces.text(mode if mode != paragraphs.MODEL else paragraphs.TIME) if pieces.items else ""
    extra, note = None, ""
    if cleaned:
        extra = {"cleanup": f"{tidied.model} {tidied.version}",     # id and version that ran
                 "cleanup_kept_raw": tidied.kept_raw}
        note += (f" Cleaned up with {tidied.name}." if not tidied.kept_raw else
                 f" Cleaned up, except {tidied.kept_raw} of {tidied.chunks} parts kept as "
                 f"transcribed ({tidied.error}).")
    elif tidied is not None:
        note += f" Clean-up failed ({tidied.error}), so the transcript is as transcribed."
    if not cleaned and mode == paragraphs.MODEL and err:
        note += f" The paragraph model failed ({err}), so paragraphs are time-based."
    return Layout(shown, raw, flow, cleaned, extra, note)
