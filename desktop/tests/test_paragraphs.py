"""Paragraphs (B-44): the parity cases in ../shared/paragraph-cases.json, and the None /
Time-based / Paragraph model layout of a transcript (paragraphs.Pieces).

The model tests fetch the model from the CDN once into ~/.cache/hebrish-tests (or
$HEBRISH_TEST_CACHE) with paragraphs.download(), so the download path is exercised too; they are
skipped when offline or when onnxruntime isn't installed. The strict score parity runs on the fp32
model (onnx/model.onnx, fetched from the Hub into the same cache), because int8 scores depend on the
CPU (shared/paragraphs.md, "Parity test"); the shipped int8 model gets a break-decision check."""

import json
import os
import shutil
import urllib.request
from pathlib import Path

import pytest

from hebrish import model_store, paragraphs as P

CASES = json.loads((Path(__file__).resolve().parents[2] / "shared" / "paragraph-cases.json")
                   .read_text(encoding="utf-8"))
IDS = [c["name"] for c in CASES["cases"]]
TOL = 0.001
FP32_URL = ("https://huggingface.co/danielrosehill/MiniLM-L12-ASR-Paragraph-Breaks/resolve/main/"
            "onnx/model.onnx")


@pytest.fixture(scope="module")
def model_dir():
    pytest.importorskip("onnxruntime")
    cache = Path(os.environ.get("HEBRISH_TEST_CACHE") or Path.home() / ".cache" / "hebrish-tests")
    old = model_store.ROOT
    model_store.set_root(cache / "models")
    try:
        d = P.installed()
        if d is None:
            try:
                d = P.download()
            except OSError as e:          # URLError is an OSError: offline
                pytest.skip(f"paragraph model not cached and not downloadable: {e}")
        yield d
    finally:
        model_store.set_root(old)


@pytest.fixture(scope="module")
def breaker(model_dir):
    return P.Breaker(model_dir)


@pytest.fixture(scope="module")
def breaker32(model_dir):
    """The fp32 model in a folder laid out like an install (vocab and config from the int8 one)."""
    d = model_dir.parent.parent / f"{P.MODEL_ID}-fp32" / model_dir.name
    if not (d / P.MODEL_FILE).exists():
        d.mkdir(parents=True, exist_ok=True)
        for f in (P.VOCAB_FILE, "config.json"):
            shutil.copy(model_dir / f, d / f)
        part = d / (P.MODEL_FILE + ".part")
        try:
            with urllib.request.urlopen(FP32_URL, timeout=60) as r, open(part, "wb") as out:
                shutil.copyfileobj(r, out)
        except OSError as e:
            pytest.skip(f"fp32 paragraph model not cached and not downloadable: {e}")
        part.rename(d / P.MODEL_FILE)
    return P.Breaker(d)


def test_threshold(breaker):
    assert breaker.threshold == CASES["threshold"]


@pytest.mark.parametrize("case", CASES["cases"], ids=IDS)
def test_word_pieces_and_windows(breaker, case):
    words = case["input"].split()
    pieces = breaker.word_pieces(words)
    assert pieces == case["word_pieces"]
    assert [list(w) for w in P.windows(pieces)] == case["windows"]


@pytest.mark.parametrize("case", CASES["cases"], ids=IDS)
def test_probs_fp32(breaker32, case):
    got = breaker32.probs(case["input"].split())
    assert len(got) == len(case["probs_fp32"])
    worst = max((abs(a - b) for a, b in zip(got, case["probs_fp32"])), default=0)
    assert worst <= TOL, worst


@pytest.mark.parametrize("case", CASES["cases"], ids=IDS)
def test_output_fp32(breaker32, case):
    if any(abs(p - CASES["threshold"]) <= TOL for p in case["probs_fp32"][1:]):
        pytest.skip("a score is within the tolerance of the threshold")
    assert breaker32.apply(case["input"]) == case["output_fp32"]


@pytest.mark.parametrize("case", CASES["cases"], ids=IDS)
def test_int8_decisions(breaker, case):
    """int8 scores vary by CPU; its break decisions must still match fp32 almost everywhere."""
    thr = CASES["threshold"]
    got = breaker.probs(case["input"].split())[1:]
    want = case["probs_fp32"][1:]
    differ = sum((a >= thr) != (b >= thr) for a, b in zip(got, want))
    assert differ <= max(2, 0.02 * len(want)), differ


def test_only_whitespace_changes(breaker):
    for c in CASES["cases"]:
        assert breaker.apply(c["input"]).split() == c["input"].split()
    assert breaker.apply("   \n\t ") == "   \n\t "
    assert breaker.apply("") == ""


def test_installed_layout(model_dir):
    assert model_dir.parent.name == P.MODEL_ID
    mf = json.loads((model_dir / "manifest.json").read_text())
    assert mf["model"] == "paragraph-breaks"
    for n in P.FILES:
        assert (model_dir / n).stat().st_size == mf["files"][n]["size"]


def test_runs_beside_sherpa_onnx(breaker):
    """sherpa-onnx brings its own onnxruntime library; the onnxruntime package links its own
    statically. Both loaded in one process must still run."""
    pytest.importorskip("sherpa_onnx")
    c = CASES["cases"][2]
    assert abs(breaker.probs(c["input"].split())[-1] - c["probs_int8"][-1]) <= TOL


# -- None / Time-based / Paragraph model layout (no model needed) ---------------------

SR = 16000
EVERY = 30 * SR


def _decode(pieces: P.Pieces, takes, mode):
    """What the Transcription tab writes while decoding: each piece with its separator."""
    out = []
    for text, done in takes:
        sep = pieces.add(text, done, mode)
        if sep is not None:
            out.append(sep + text)
    return "".join(out)


TAKES = [("One.", 12 * SR), ("Two.", 25 * SR), ("Three.", 40 * SR), ("", 55 * SR),
         ("  ", 62 * SR), ("Four.", 75 * SR), ("Five.", 80 * SR)]


@pytest.mark.parametrize("mode", [P.NONE, P.TIME, P.MODEL])
def test_live_text_is_the_layout(mode):
    p = P.Pieces(EVERY)
    live = _decode(p, TAKES, mode)
    assert live == p.text(P.NONE if mode == P.MODEL else mode)   # MODEL shows spaces while decoding


def test_time_based_breaks():
    p = P.Pieces(EVERY)
    _decode(p, TAKES, P.TIME)
    # paragraphs start at 12 s (first), 55 s (empty piece: carried to "Four." at 75 s)
    assert p.text(P.TIME) == "One. Two. Three.\n\nFour. Five."
    assert p.text(P.NONE) == "One. Two. Three. Four. Five."


def test_reflow_between_modes():
    p = P.Pieces(EVERY)
    _decode(p, TAKES, P.MODEL)

    class Fake:
        def apply(self, text):
            assert text == "One. Two. Three. Four. Five."
            return "One. Two.\n\nThree. Four. Five."
    assert p.text(P.MODEL, Fake()) == "One. Two.\n\nThree. Four. Five."
    assert p.text(P.TIME) == "One. Two. Three.\n\nFour. Five."
    assert p.text(P.NONE) == "One. Two. Three. Four. Five."


def test_model_failure_propagates():
    """The UI falls back to Time-based when the model raises; Pieces doesn't swallow it."""
    p = P.Pieces(EVERY)
    _decode(p, TAKES, P.MODEL)

    class Broken:
        def apply(self, text):
            raise RuntimeError("no session")
    with pytest.raises(RuntimeError):
        p.text(P.MODEL, Broken())


def test_not_installed(tmp_path):
    old = model_store.ROOT
    model_store.set_root(tmp_path)
    try:
        assert P.installed() is None
        (tmp_path / P.MODEL_ID / "r5b").mkdir(parents=True)     # partial download
        (tmp_path / P.MODEL_ID / "r5b" / "vocab.txt").write_text("x")
        assert P.installed() is None
        with pytest.raises(FileNotFoundError):
            P.breaker()
    finally:
        model_store.set_root(old)
