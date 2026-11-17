"""hebrish.tm (B-108): Transcription Mode's layout, shared by the Transcription tab and the local API."""

from types import SimpleNamespace

from hebrish import paragraphs, tm


def _pieces():
    p = paragraphs.Pieces(30 * 16000)
    for i, t in enumerate(["One.", "Two.", "Three."]):
        p.add(t, (i + 1) * 20 * 16000, paragraphs.TIME)
    return p


def test_time_based_without_model_or_cleanup():
    lay = tm.layout(_pieces(), paragraphs.TIME, None, None, None)
    assert lay.flow == paragraphs.TIME and lay.shown == lay.raw and "\n\n" in lay.shown
    assert not lay.cleaned and lay.extra is None and lay.note == ""


def test_paragraph_model_failure_is_time_based_and_said():
    p = _pieces()
    lay = tm.layout(p, paragraphs.MODEL, p.text(paragraphs.TIME), RuntimeError("boom"), None)
    assert lay.flow == paragraphs.TIME and "paragraph model failed (boom)" in lay.note


def test_cleaned_text_is_shown_and_credited():
    tidied = SimpleNamespace(cleaned=True, text="One. Two. Three!", model="s1-mini", version="v1", name="S1-mini",
                             kept_raw=0, chunks=1, error=None)
    lay = tm.layout(_pieces(), paragraphs.TIME, tidied.text, None, tidied)
    assert lay.shown == "One. Two. Three!" and lay.cleaned and lay.extra["cleanup"] == "s1-mini v1"
    assert "Cleaned up with S1-mini" in lay.note and lay.raw != lay.shown


def test_failed_cleanup_keeps_the_transcript():
    tidied = SimpleNamespace(cleaned=False, error="server didn't start")
    lay = tm.layout(_pieces(), paragraphs.NONE, None, None, tidied)
    assert lay.shown == "One. Two. Three." and "Clean-up failed" in lay.note
