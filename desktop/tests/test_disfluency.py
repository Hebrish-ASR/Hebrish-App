"""Disfluency chop: the shared test set (../shared/disfluency-cases.json)."""

import json
from pathlib import Path

import pytest

from hebrish import disfluency

CASES = json.loads((Path(__file__).resolve().parents[2] / "shared" / "disfluency-cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda c: c["in"] or "empty")
def test_shared_cases(case):
    assert disfluency.chop(case["in"], case.get("before", "")) == case["out"]


def test_untouched_text_is_returned_as_is():
    text = "Nothing to remove here,  with odd  spacing ."
    assert disfluency.chop(text) is text
