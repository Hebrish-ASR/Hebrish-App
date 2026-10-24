"""Paragraphs in Transcription Mode (B-44, D-2026-10-24-09): None, Time-based or Paragraph model.

The spec, shared with Android, is ../shared/paragraphs.md; ../shared/paragraph-cases.json is the
parity test (tests/test_paragraphs.py).

- `Pieces` keeps one transcript's decoded pieces and where each Time-based paragraph starts, so the
  transcript can be laid out again (`text(mode)`) when the setting changes.
- `Breaker` is the Paragraph model: a MiniLM-L12 word classifier (ONNX, int8) that scores "a
  paragraph starts at this word". The tokenizer is BERT-uncased WordPiece written out here, so the
  app needs no `tokenizers` package; the ONNX session is created on first use and kept.
- `download()` fetches the model from the CDN like a speech model (`.part` resume, SHA-256 checked,
  manifest.json written last) into <models>/paragraph-breaks/<version>/. It is not a speech model
  and never appears in the model picker.

No Qt import: the UI (ui/transcribe.py) runs everything slow here on a worker thread.
"""

import json
import shutil
import threading
import unicodedata
from pathlib import Path

from . import model_store

MANIFEST_URL = "https://cdn.hebrish.app/models/paragraph-breaks/latest.json"
MODEL_ID = "paragraph-breaks"
MODEL_FILE, VOCAB_FILE, CONFIG_FILE = "model_int8.onnx", "vocab.txt", "config.json"
FILES = (MODEL_FILE, VOCAB_FILE, CONFIG_FILE)
MAXTOK, STRIDE = 510, 256      # content tokens per window (+ [CLS]/[SEP]); window step in tokens
MAX_WORD_CHARS = 100           # WordPiece: a longer piece is [UNK]

NONE, TIME, MODEL = "none", "time", "model"
MODES = (NONE, TIME, MODEL)


# -- layout of one transcript -----------------------------------------------------

class Pieces:
    """One transcript's pieces, in order, each with whether a Time-based paragraph starts there.

    `every` is the Time-based spacing in samples (PARAGRAPH_S * SAMPLE_RATE): a piece starts a
    paragraph when at least that much audio has been decoded since the last one started (the first
    piece always does). A piece with no text is dropped, and a paragraph start it carried moves to
    the next piece."""

    def __init__(self, every: int):
        self.every = every
        self.items: list[tuple[str, bool]] = []
        self._at = None
        self._carry = False

    def add(self, text: str, done: int, mode: str) -> str | None:
        """Record a piece that ends `done` samples into the audio. Returns what goes before it in
        `mode` ("" for the first piece, "\\n\\n" or " "), or None when it has no text."""
        new = self._at is None or done - self._at >= self.every
        if new:
            self._at = done
        new = new or self._carry
        if not text.strip():
            self._carry = new
            return None
        self._carry = False
        self.items.append((text, new))
        return self._sep(len(self.items) - 1, mode)

    def _sep(self, i: int, mode: str) -> str:
        if i == 0:
            return ""
        return "\n\n" if mode == TIME and self.items[i][1] else " "

    def text(self, mode: str, breaker: "Breaker | None" = None) -> str:
        """The transcript laid out in `mode`. MODEL needs `breaker` and may raise; the caller
        falls back to TIME."""
        if mode == MODEL:
            return breaker.apply(self.text(NONE))
        return "".join(self._sep(i, mode) + t for i, (t, _new) in enumerate(self.items))


# -- tokenizer: BERT uncased WordPiece (spec step 2) --------------------------------

# BERT's _is_chinese_char: CJK ideographs get spaces around them
_CJK = ((0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0x20000, 0x2A6DF), (0x2A700, 0x2B73F),
        (0x2B740, 0x2B81F), (0x2B820, 0x2CEAF), (0xF900, 0xFAFF), (0x2F800, 0x2FA1F))


_DROP = ("Cc", "Cf", "Co", "Cs")


def _is_cjk(cp: int) -> bool:
    return any(a <= cp <= b for a, b in _CJK)


def _is_punct(ch: str) -> bool:
    cp = ord(ch)
    return (33 <= cp <= 47 or 58 <= cp <= 64 or 91 <= cp <= 96 or 123 <= cp <= 126
            or unicodedata.category(ch).startswith("P"))


def normalize(word: str) -> str:
    """BertNormalizer(clean_text, handle_chinese_chars, lowercase, strip_accents=None), as the
    Hugging Face `tokenizers` Rust code runs it: drop NUL, U+FFFD and control, format and
    private-use characters (Cc, Cf, Co; unassigned Cn code points stay, and end up [UNK]) except
    tab/newline/CR, which become spaces like all whitespace; spaces around CJK; strip accents (NFD,
    drop Mn); then lower-case character by character (so no final-sigma rule: "ΣΑΣ" -> "σασ").
    Checked against `tokenizers` on ~195k random words, 2026-10-24 (maintaining.md)."""
    out = []
    for ch in word:
        cp = ord(ch)
        if ch in "\t\n\r" or ch.isspace():
            out.append(" ")
        elif cp == 0 or cp == 0xFFFD or unicodedata.category(ch) in _DROP:
            continue
        elif _is_cjk(cp):
            out.append(f" {ch} ")
        else:
            out.append(ch)
    s = "".join(c for c in unicodedata.normalize("NFD", "".join(out))
                if unicodedata.category(c) != "Mn")
    return "".join(c.lower() for c in s)


def pre_tokenize(text: str) -> list[str]:
    """BertPreTokenizer: split on whitespace, and every punctuation character on its own."""
    out, cur = [], []
    for ch in text:
        if ch.isspace() or _is_punct(ch):
            if cur:
                out.append("".join(cur))
                cur = []
            if not ch.isspace():
                out.append(ch)
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur))
    return out


class WordPiece:
    def __init__(self, vocab: dict[str, int]):
        self.vocab = vocab
        self.unk, self.cls, self.sep = vocab["[UNK]"], vocab["[CLS]"], vocab["[SEP]"]

    @classmethod
    def from_file(cls, path: Path) -> "WordPiece":
        # line n (from 0) is id n; split on \n only (vocab.txt has no other line breaks)
        lines = Path(path).read_text(encoding="utf-8").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        return cls({tok.rstrip("\r"): i for i, tok in enumerate(lines)})

    def _piece(self, s: str) -> list[int]:
        if len(s) > MAX_WORD_CHARS:
            return [self.unk]
        ids, start = [], 0
        while start < len(s):
            end = len(s)
            while start < end:
                sub = s[start:end] if start == 0 else "##" + s[start:end]
                if sub in self.vocab:
                    ids.append(self.vocab[sub])
                    break
                end -= 1
            else:
                return [self.unk]          # some part isn't in the vocabulary: the whole piece
            start = end
        return ids

    def word(self, word: str) -> list[int]:
        """The ids of one whitespace-separated word; [UNK] when it yields none."""
        ids = [i for p in pre_tokenize(normalize(word)) for i in self._piece(p)]
        return ids or [self.unk]


def windows(pieces: list[list[int]]) -> list[tuple[int, int]]:
    """(first_word, end_word) spans of at most MAXTOK tokens, cut at word boundaries, each
    starting about STRIDE tokens after the last (spec step 3)."""
    n = len(pieces)
    if not n:
        return []
    starts = [0]
    for p in pieces:
        starts.append(starts[-1] + len(p))
    out, w0 = [], 0
    while True:
        w1 = w0
        while w1 < n and starts[w1 + 1] - starts[w0] <= MAXTOK:
            w1 += 1
        w1 = max(w1, w0 + 1)
        out.append((w0, w1))
        if w1 >= n:
            return out
        nxt = w0 + 1
        while nxt < n and starts[nxt] < starts[w0] + STRIDE:
            nxt += 1
        w0 = max(w0 + 1, min(nxt, w1))


# -- the model ----------------------------------------------------------------------

class Breaker:
    """The Paragraph model in one installed folder. The ONNX session is made on first use."""

    def __init__(self, folder: Path, threshold: float | None = None, threads: int = 0):
        self.dir = Path(folder)
        self.tok = WordPiece.from_file(self.dir / VOCAB_FILE)
        if threshold is None:
            threshold = _threshold(self.dir)
        self.threshold = float(threshold)
        self.threads = threads
        self._sess = None
        self._lock = threading.Lock()

    def session(self):
        with self._lock:
            if self._sess is None:
                import onnxruntime as ort
                opts = ort.SessionOptions()
                if self.threads:
                    opts.intra_op_num_threads = self.threads
                self._sess = ort.InferenceSession(str(self.dir / MODEL_FILE), opts,
                                                  providers=["CPUExecutionProvider"])
            return self._sess

    def word_pieces(self, words: list[str]) -> list[list[int]]:
        return [self.tok.word(w) for w in words]

    def probs(self, words: list[str]) -> list[float]:
        """P(a paragraph starts at word i), from the window where the word's first token is
        closest to the middle (spec step 4). The first word is always 0."""
        import numpy as np
        if not words:
            return []
        pieces = self.word_pieces(words)
        sess = self.session()
        best: dict[int, tuple[float, float]] = {}
        for w0, w1 in windows(pieces):
            ids, pos = [self.tok.cls], []
            for w in range(w0, w1):
                pos.append((len(ids), w))
                ids += pieces[w]
            ids.append(self.tok.sep)
            a = np.array([ids], dtype=np.int64)
            logits = sess.run(["logits"], {"input_ids": a, "attention_mask": np.ones_like(a)})[0][0]
            e = np.exp(logits - logits.max(-1, keepdims=True))
            pr = e[:, 1] / e.sum(-1)
            mid = (len(ids) - 1) / 2
            for p, w in pos:
                c = -abs(p - mid)
                if w not in best or c > best[w][0]:      # a tie keeps the earlier window
                    best[w] = (c, float(pr[p]))
        return [0.0] + [best[i][1] for i in range(1, len(words))]

    def apply(self, text: str) -> str:
        """`text` with a blank line before every word that starts a paragraph and one space
        before every other; returns `text` itself if it has no words or (never expected) the
        result would differ in anything but whitespace."""
        words = text.split()
        if not words:
            return text
        out = []
        for w, p in zip(words, self.probs(words)):
            out.append(("\n\n" if p >= self.threshold else " ") + w if out else w)
        res = "".join(out)
        return res if res.split() == words else text


def _threshold(folder: Path) -> float:
    mf = folder / "manifest.json"
    try:
        thr = json.loads(mf.read_text()).get("threshold")
        if thr is not None:
            return float(thr)
    except (OSError, ValueError):
        pass
    return float(json.loads((folder / CONFIG_FILE).read_text())["paragraph_threshold"])


# -- on disk and download -------------------------------------------------------------

def root() -> Path:
    """<models>/paragraph-breaks: beside the speech models, so it moves with the model folder."""
    return model_store.ROOT / MODEL_ID


def installed() -> Path | None:
    """The newest complete version folder (manifest.json present, written last), else None."""
    base = root()
    if not base.is_dir():
        return None
    done = [d for d in base.iterdir() if (d / "manifest.json").is_file()
            and all((d / n).is_file() for n in FILES)]
    return max(done, key=lambda d: (d / "manifest.json").stat().st_mtime) if done else None


def fetch_manifest() -> dict:
    doc = json.loads(model_store._get(MANIFEST_URL))
    missing = [n for n in FILES if n not in doc.get("files", {})]
    if missing or not doc.get("version") or not doc.get("base_url"):
        raise RuntimeError(f"{MANIFEST_URL} is missing {', '.join(missing) or 'version/base_url'}")
    return doc


def download(on_progress=None, cancel: threading.Event | None = None, doc: dict | None = None) -> Path:
    """Fetch and verify the model, then make it the installed one (older versions are deleted).
    on_progress(done_bytes, total_bytes, file_name)."""
    doc = doc or fetch_manifest()
    version = "".join(c if c.isalnum() or c in "-_." else "_" for c in doc["version"])
    dest = root() / version
    base = doc["base_url"] if doc["base_url"].endswith("/") else doc["base_url"] + "/"
    files = {n: doc["files"][n] for n in FILES}
    model_store.fetch_files(dest, files, lambda n: base + n, on_progress, cancel)
    (dest / "manifest.json").write_text(json.dumps(doc, indent=2))
    for d in root().iterdir():
        if d.is_dir() and d.name != dest.name:
            shutil.rmtree(d, ignore_errors=True)
    return dest


_breaker: Breaker | None = None
_breaker_lock = threading.Lock()


def breaker() -> Breaker:
    """The installed model, kept between transcripts (its ONNX session too). Raises when it is
    not installed or its files don't load."""
    global _breaker
    folder = installed()
    if folder is None:
        raise FileNotFoundError("the paragraph model isn't downloaded")
    with _breaker_lock:
        if _breaker is None or _breaker.dir != folder:
            _breaker = Breaker(folder)
        return _breaker
