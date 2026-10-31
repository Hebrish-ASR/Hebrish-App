"""engine.Engine._decode_retry: a piece with speech that decodes to nothing is decoded again in halves
(2026-10-31, docs/debug-log/2026-10-31-empty-piece.md). No model: _decode_piece is faked."""

import numpy as np

from hebrish import engine
from hebrish.engine import SAMPLE_RATE, Engine


def _speechy(seconds: float) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    x = 0.3 * np.sin(2 * np.pi * 200 * t) * (np.sin(2 * np.pi * 2 * t) > 0)   # bursts with gaps
    return x.astype(np.float32)


class Fake(Engine):
    def __init__(self, empty_over_s):
        super().__init__()
        self.empty_over_s, self.calls = empty_over_s, []

    def _decode_piece(self, x):
        s = (len(x) / SAMPLE_RATE) - engine.TAIL_PAD_S
        self.calls.append(round(s, 1))
        return ("" if s > self.empty_over_s else "words"), 1


PAD = np.zeros(int(engine.TAIL_PAD_S * SAMPLE_RATE), np.float32)


def test_empty_piece_is_split_and_recovered():
    e = Fake(empty_over_s=14)       # either half (7-13 s) decodes
    text, _ = e._decode_retry(_speechy(20), PAD)
    assert text == "words words" and len(e.calls) == 3


def test_retry_depth_is_bounded():
    e = Fake(empty_over_s=0)            # always empty
    text, _ = e._decode_retry(_speechy(20), PAD)
    assert text == "" and len(e.calls) == 1 + 2 + 4


def test_silence_is_not_retried():
    e = Fake(empty_over_s=0)
    text, _ = e._decode_retry(np.zeros(20 * SAMPLE_RATE, np.float32), PAD)
    assert text == "" and e.calls == [20.0]
