"""1.009: History tab counts from 1,000 up are rounded to the nearest thousand, in K."""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hebrish.ui.window import kilo  # noqa: E402


@pytest.mark.parametrize("n, shown", [(0, "0"), (999, "999"), (1000, "1K"), (1499, "1K"),
                                      (1500, "2K"), (12345, "12K"), (1234567, "1,235K")])
def test_kilo(n, shown):
    assert kilo(n) == shown
