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


def test_recorder_drops_input_while_a_cue_plays():
    from hebrish.audio import Recorder
    r = Recorder()
    block = np.full((160, 1), 0.1, np.float32)
    r.mute(10)
    r._cb(block, 160, None, None)
    assert r.peek().size == 0 and r.level > 0      # the meter still moves
    r._mute_until = 0.0
    r._cb(block, 160, None, None)
    assert r.peek().size == 160


class _FakeRec:
    """Stands in for sherpa-onnx's OnlineRecognizer: each decode reveals the next result."""

    def __init__(self, results):
        self.results, self.i = results, -1

    def create_stream(self):
        return type("S", (), {"accept_waveform": lambda *a: None, "input_finished": lambda *a: None})()

    def is_ready(self, s):
        return False

    def decode_stream(self, s):
        pass

    def get_result(self, s):
        self.i = min(self.i + 1, len(self.results) - 1)
        return self.results[self.i]

    def get_result_all(self, s):
        return type("R", (), {"tokens": self.results[self.i].split()})()


def test_streaming_releases_whole_words_only():
    """Shakshuka's result grows in BPE pieces ("ask Av", "i for"); only text up to the last
    space goes out while recording, and the pieces join back into the exact result."""
    from hebrish.engine import Engine
    e = Engine()
    e._rec, e.streaming = _FakeRec(["Reminder", "Reminder, ask Av", "Reminder, ask Avi for",
                                    "Reminder, ask Avi for a dgima."]), True
    ls, chunk = e.live("word"), np.zeros(SR // 2, np.float32)
    out = [ls.feed(chunk), ls.feed(chunk), ls.feed(chunk)]
    assert out == ["", "Reminder, ask ", "Avi "]
    out.append(ls.finish(chunk))
    assert out[-1] == "for a dgima."
    assert "".join(out) == "Reminder, ask Avi for a dgima."


def test_streaming_never_rewrites_inserted_text():
    """If a result ever contradicted text already pasted, nothing more is pasted for it."""
    from hebrish.engine import Engine
    e = Engine()
    e._rec, e.streaming = _FakeRec(["Hi Ann ", "Hi, I'm confirming "]), True
    ls, chunk = e.live("word"), np.zeros(SR // 2, np.float32)
    assert ls.feed(chunk) == "Hi Ann "
    assert ls.feed(chunk) == ""


# -- streaming release (engine.STREAM_RELEASE, 0.7.1) --------------------------------------

from hebrish.engine import LiveStream  # noqa: E402


def _stream(release):
    s = LiveStream.__new__(LiveStream)
    s.sent, s._text, s._grew_at, s._held_at = "", "", 0.0, None
    from hebrish.engine import STREAM_RELEASE
    s._rule = STREAM_RELEASE[release]
    return s


def test_word_release_holds_the_last_word():
    s = _stream("word")
    assert s._release("Reminder, ask Av", False, now=0) == "Reminder, ask "
    assert s._release("Reminder, ask Avi for", False, now=10) == "Avi "     # never at a pause


def test_phrase_release_waits_for_punctuation():
    s = _stream("phrase")
    assert s._release("Reminder, ask", False, now=0) == "Reminder, "
    assert s._release("Reminder, ask Avi", False, now=0.5) == ""


def test_phrase_release_flushes_at_a_pause():
    # Daniel, 2026-10-22: pausing for thought left the last words unsent
    s = _stream("phrase")
    assert s._release("I think we should", False, now=0) == ""
    assert s._release("I think we should", False, now=0.6) == ""
    assert s._release("I think we should", False, now=1.1) == "I think we should"
    assert s._release("I think we should go", False, now=2) == ""
    assert s._release("I think we should go", False, now=3.1) == " go"      # continues exactly


def test_phrase_release_caps_the_hold():
    s = _stream("phrase")
    words = ""
    out = []
    for i in range(10):          # a new word every 0.5 s, no punctuation, no pause
        words += f"w{i} "
        out.append(s._release(words.strip(), False, now=i * 0.5))
    assert "".join(out) and "".join(out) == words.strip()[: len("".join(out))]


def test_finish_releases_the_rest():
    s = _stream("sentence")
    assert s._release("Hello there", False, now=0) == ""
    assert s._release("Hello there friend.", True, now=0.2) == "Hello there friend."
