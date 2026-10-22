"""Live insertion cut points, quiet hours, and the 0.4.0 config upgrade."""

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from hebrish.config import DEFAULTS, in_quiet_hours, threads, upgrade  # noqa: E402
from hebrish.engine import LIVE_FORCE_S, live_cut  # noqa: E402

SR = 16000
rng = np.random.default_rng(0)


def speech(s):
    return (rng.standard_normal(int(s * SR)) * 0.2).astype(np.float32)


def silence(s):
    return (rng.standard_normal(int(s * SR)) * 0.002).astype(np.float32)


def test_no_cut_before_interval():
    assert live_cut(np.concatenate([speech(5), silence(1), speech(3)]), 15) is None


def test_cuts_inside_the_pause():
    x = np.concatenate([speech(12), silence(0.8), speech(4)])
    cut = live_cut(x, 15)
    assert cut is not None and 12 * SR < cut < 12.8 * SR


def test_waits_without_a_pause_then_forces():
    assert live_cut(speech(16), 15) is None
    assert live_cut(speech(15 + LIVE_FORCE_S), 15) is not None


def test_quiet_hours_cross_midnight():
    cfg = {**DEFAULTS, "quiet_hours": True, "quiet_from": "22:00", "quiet_to": "07:00"}
    at = lambda h, m=0: time.struct_time((2026, 10, 21, h, m, 0, 0, 294, -1))  # noqa: E731
    assert in_quiet_hours(cfg, at(23)) and in_quiet_hours(cfg, at(6, 59))
    assert not in_quiet_hours(cfg, at(7)) and not in_quiet_hours(cfg, at(12))
    cfg.update(quiet_from="13:00", quiet_to="14:00")
    assert in_quiet_hours(cfg, at(13, 30)) and not in_quiet_hours(cfg, at(14))
    assert not in_quiet_hours({**cfg, "quiet_hours": False}, at(13, 30))


def test_old_default_threads_become_auto():
    assert upgrade({"num_threads": 4})["num_threads"] == 0
    assert upgrade({"num_threads": 4, "live_insert_s": 0})["num_threads"] == 4
    assert threads({"num_threads": 3}) == 3 and 1 <= threads({"num_threads": 0}) <= 8


def test_old_default_interval_becomes_normal():
    # 0.7.0: ~10 s was the default before send_chord existed; a chosen value stays
    assert upgrade({"feedback": "beeps", "live_insert_s": 10})["live_insert_s"] == 7
    assert upgrade({"feedback": "beeps", "live_insert_s": 15})["live_insert_s"] == 15
    assert upgrade({"send_chord": "enter", "live_insert_s": 10})["live_insert_s"] == 10
    assert DEFAULTS["live_insert_s"] == 7 and DEFAULTS["send_chord"] == "enter"


def test_cuts_at_fast_interval():
    x = np.concatenate([speech(4.5), silence(0.8), speech(1)])
    cut = live_cut(x, 5)
    assert cut is not None and 4.5 * SR < cut < 5.3 * SR
