"""Live insertion cut points, quiet hours, and the 0.4.0 config upgrade."""

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from hebrish.config import DEFAULTS, in_quiet_hours, threads, upgrade  # noqa: E402
from hebrish.engine import LIVE_BREAK_S, LIVE_FORCE_S, live_cut, live_split  # noqa: E402

SR = 16000
rng = np.random.default_rng(0)


def speech(s):
    return (rng.standard_normal(int(s * SR)) * 0.2).astype(np.float32)


def silence(s):
    return (rng.standard_normal(int(s * SR)) * 0.002).astype(np.float32)


def test_no_cut_before_interval():
    assert live_cut(np.concatenate([speech(5), silence(0.8), speech(3)]), 15) is None


def test_a_long_pause_cuts_before_the_interval():
    # 0.7.1: stopping to think (>= LIVE_BREAK_S) inserts what was said, whatever the interval
    x = np.concatenate([speech(3), silence(1.3), speech(0.5)])
    r = live_split(x, 15)
    assert r is not None and 3 * SR < r[0] < 4.3 * SR and r[1] >= LIVE_BREAK_S
    assert live_cut(silence(4), 15) is None                     # no speech yet: nothing to cut
    assert live_cut(np.concatenate([speech(0.5), silence(1.2)]), 15) is None   # under LIVE_MIN_S


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
    # (0.7.1 then moves each preset down: 7 -> 5, 10 -> 8)
    assert upgrade({"feedback": "beeps", "live_insert_s": 10})["live_insert_s"] == 5
    assert upgrade({"feedback": "beeps", "live_insert_s": 15})["live_insert_s"] == 15
    assert upgrade({"send_chord": "enter", "live_insert_s": 10})["live_insert_s"] == 8
    assert DEFAULTS["live_insert_s"] == 5 and DEFAULTS["send_chord"] == "enter"


def test_presets_move_down_once():
    # 0.7.1: Fast 5 -> 3, Normal 7 -> 5, Relaxed 10 -> 8; a config with stream_release has moved
    for old, new in ((5, 3), (7, 5), (10, 8), (12, 12), (0, 0)):
        assert upgrade({"feedback": "beeps", "send_chord": "enter", "live_insert_s": old})["live_insert_s"] == new
    assert upgrade({"send_chord": "enter", "stream_release": "phrase", "live_insert_s": 7})["live_insert_s"] == 7


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
    assert s._release("Reminder, ask", False, now=0) == ""                  # one word: too short
    assert s._release("Reminder, ask Avi for a dgima, of", False, now=0.5) == "Reminder, ask Avi for a dgima,"
    assert s._release("Reminder, ask Avi for a dgima, of the", False, now=1) == ""
    assert s._release("Reminder, ask Avi for a dgima, of the marinade.", False, now=1.5) == " of the marinade."
    # a full stop goes out at once, whatever the length; the space after it is never sent alone
    assert s._release("Reminder, ask Avi for a dgima, of the marinade. ", False, now=2) == ""
    assert s._release("Reminder, ask Avi for a dgima, of the marinade. OK.", False, now=2.5) == " OK."


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
    sent = "".join(out)
    assert sent and sent == words.strip()[: len(sent)]
    assert all(len(o.split()) >= 3 for o in out if o)      # whole words, never one at a time
    assert 1 <= sum(1 for o in out if o) <= 2              # every ~2.5 s


def test_seams_hold_the_full_stop_of_a_piece_cut_mid_sentence():
    # 0.7.1: Parakeet ends every piece with a full stop and starts the next with a capital
    from hebrish.engine import after_held_stop, hold_stop
    assert hold_stop("after the kids are asleep.", 0.7)
    assert hold_stop("after the kids are asleep.", LIVE_BREAK_S)    # 0.7.6: the context decides
    assert not hold_stop("after the kids are asleep.", None)            # the last piece
    assert not hold_stop("are you there?", 0.7) and not hold_stop("and so on...", 0.7)
    assert after_held_stop("So nothing else is running.") == " so nothing else is running."
    assert after_held_stop("since my son started.") == " since my son started."
    assert after_held_stop("Esti said she'll book it.") == ". Esti said she'll book it."
    assert after_held_stop("I think so.") == ". I think so."


def test_finish_releases_the_rest():
    s = _stream("sentence")
    assert s._release("Hello there", False, now=0) == ""
    assert s._release("Hello there friend.", True, now=0.2) == "Hello there friend."


def _run_worker(texts, jobs, cfg=None):
    """Drive Controller._worker with a scripted Parakeet engine; return (pastes, transcript).
    Skipped where PySide6 isn't installed (Linux CI), as in test_overlay."""
    import pytest
    pytest.importorskip("PySide6")
    import queue
    import threading
    from types import SimpleNamespace
    from hebrish.ui.app import Controller
    # a text, or (text, stop) for a piece decoded with context (engine.transcribe_after)
    _say = lambda t: t if isinstance(t, tuple) else (t, None)
    pastes, done = [], threading.Event()
    sig = SimpleNamespace(piece=SimpleNamespace(emit=lambda t: None),
                          transcribed=SimpleNamespace(emit=lambda t, e, a: (pastes.append(("DONE", t)), done.set())))
    it = iter(texts)
    ctl = SimpleNamespace(
        engine=SimpleNamespace(streaming=False, transcribe_after=lambda s, c, vad=False: _say(next(it))),
        cfg={"vad": False, "trailing_space": True, "all_caps": False, "out_cursor": True, "out_clipboard": False,
             "out_window": False, "paste_chord": "ctrl+v", **(cfg or {})},
        sig=sig, inserter=SimpleNamespace(insert=lambda t, how, chord: pastes.append(t)),
        _take=1, _send_take=0, _jobs=queue.Queue())
    ctl._show = lambda t: Controller._show(ctl, t)
    ctl._insert = lambda t: Controller._insert(ctl, t)
    for pause, final in jobs:
        ctl._jobs.put((1, np.zeros(SR, np.float32), final, pause))
    threading.Thread(target=Controller._worker, args=(ctl,), daemon=True).start()
    assert done.wait(5)
    return pastes[:-1], pastes[-1][1]


def test_worker_joins_a_sentence_cut_at_a_short_pause():
    pastes, text = _run_worker(
        ["Do it after the kids are asleep.", "So nothing else is running.", "Esti said yes.", "Thanks."],
        [(0.7, False), (0.7, False), (1.4, False), (None, True)])
    # 0.7.6: the full stop is held at every pause length (the 1.4 s one too)
    assert pastes == ["Do it after the kids are asleep", " so nothing else is running",
                      ". Esti said yes", ". Thanks. "]
    assert text == "Do it after the kids are asleep so nothing else is running. Esti said yes. Thanks."


def test_worker_pastes_a_held_full_stop_at_stop():
    pastes, text = _run_worker(["We are done.", ""], [(0.7, False), (None, True)])
    assert pastes == ["We are done", ". "] and text == "We are done."


def test_worker_all_caps_keeps_the_seams():
    # 0.7.2: capitals only in what is pasted, so the held full stop still joins, and History
    # (possible training data) keeps the normal case
    pastes, text = _run_worker(["Do it after the kids are asleep.", "So nothing runs.", ""],
                               [(0.7, False), (0.7, False), (None, True)], {"all_caps": True})
    assert pastes == ["DO IT AFTER THE KIDS ARE ASLEEP", " SO NOTHING RUNS", ". "]
    assert text == "Do it after the kids are asleep so nothing runs."


def test_worker_context_decides_the_seam():
    # 0.7.6: decoded after the previous piece, the model's own mark at the seam decides, whatever
    # the next word is ("So" after a real sentence end; "I" carrying on a sentence)
    pastes, text = _run_worker(
        ["The hardest part is.", ("is the room noise?", False), "That is a sentence.",
         ("So we stop here.", True), ("Then I.", True), ("I think it works.", False), ""],
        [(1.4, False), (0.7, False), (1.2, False), (0.8, False), (2.0, False), (0.7, False), (None, True)])
    assert pastes == ["The hardest part is", " is the room noise? ", "That is a sentence",
                      ". So we stop here", ". Then I", " I think it works", ". "]
    assert text == ("The hardest part is is the room noise? That is a sentence. So we stop here. "
                    "Then I I think it works.")


def test_context_capitalises_a_sentence_the_model_starts():
    from hebrish.engine import after_held_stop
    assert after_held_stop("we stop.", True) == ". We stop."
    assert after_held_stop("Modal runs it.", False) == " Modal runs it."
