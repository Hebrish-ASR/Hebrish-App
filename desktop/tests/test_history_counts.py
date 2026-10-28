"""1.009: history counts from 1,000 up are rounded to the nearest thousand (K), from a million
to the nearest fifth of a million (M)."""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hebrish.ui.window import kilo  # noqa: E402


@pytest.mark.parametrize("n, shown", [(0, "0"), (999, "999"), (1000, "1K"), (1499, "1K"),
                                      (1500, "2K"), (12345, "12K"), (999_499, "999K"),
                                      (999_500, "1M"), (1_099_999, "1M"), (1_100_000, "1.2M"),
                                      (1_234_567, "1.2M"), (1_300_000, "1.4M"), (12_345_678, "12.4M")])
def test_kilo(n, shown):
    assert kilo(n) == shown
