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
    # (R-2026-10-25-3 then moves each up: 5 -> 6, 8 -> 10)
    assert upgrade({"feedback": "beeps", "live_insert_s": 10})["live_insert_s"] == 6
    assert upgrade({"feedback": "beeps", "live_insert_s": 15})["live_insert_s"] == 15
    assert upgrade({"send_chord": "enter", "live_insert_s": 10})["live_insert_s"] == 10
    assert DEFAULTS["live_insert_s"] == 6 and DEFAULTS["send_chord"] == "enter"


def test_presets_move_down_once():
    # 0.7.1: Fast 5 -> 3, Normal 7 -> 5, Relaxed 10 -> 8; a config with stream_release has moved
    m = {"mics": {}}
    for old, new in ((5, 3), (7, 5), (10, 8), (12, 12), (0, 0)):
        assert upgrade({"feedback": "beeps", "send_chord": "enter", "live_insert_s": old, **m})["live_insert_s"] == new
    assert upgrade({"send_chord": "enter", "stream_release": "phrase", "live_insert_s": 7, **m})["live_insert_s"] == 7


def test_presets_move_up_once():
    # R-2026-10-25-3: Fast 3 -> 4, Normal 5 -> 6, Relaxed 8 -> 10; a config with mics has moved
    s = {"feedback": "beeps", "send_chord": "enter", "stream_release": "phrase"}
    for old, new in ((3, 4), (5, 6), (8, 10), (7, 7), (0, 0)):
        assert upgrade({**s, "live_insert_s": old})["live_insert_s"] == new
    assert upgrade({**s, "mics": {}, "live_insert_s": 5})["live_insert_s"] == 5


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


def _run_worker(texts, jobs, cfg=None, enter_at=None, hold=False, late=None, sent=None, send_take=0,
                heard=0, keys=False):
    """Drive Controller._worker with a scripted Parakeet engine; return (pastes, transcript).
    Skipped where PySide6 isn't installed (Linux CI), as in test_overlay.
    enter_at: the user's send key is pressed while the decode call with that index runs (Enter
    guard), held by the key source if `hold`; words it keeps back go to `late`, presses of a
    chord (Stop and send, a replayed Enter) to `sent`. A job ("ENTER", False) is Press Enter after
    silence's marker, queued with the silence clock at 0; `heard` is where the clock is when it
    runs (not 0: speech since). keys: key presses also go in the pastes, as ("KEY", chord)."""
    import pytest
    pytest.importorskip("PySide6")
    import queue
    import threading
    from types import SimpleNamespace
    from hebrish.ui.app import Controller
    # a text, or (text, stop) for a piece decoded with context (engine.transcribe_after)
    _say = lambda t: t if isinstance(t, tuple) else (t, None)
    pastes, done = [], threading.Event()
    late = late if late is not None else []
    sent = sent if sent is not None else []
    sig = SimpleNamespace(piece=SimpleNamespace(emit=lambda t: None), take_began=SimpleNamespace(emit=lambda: None),
                          late=SimpleNamespace(emit=late.append),
                          transcribed=SimpleNamespace(emit=lambda t, e, a: (pastes.append(("DONE", t)), done.set())))
    it = iter(texts)
    calls = iter(range(10_000))

    def decode(s, c, vad=False, ref=None):
        if next(calls) == enter_at:
            ctl.hotkeys.holding = hold
            Controller._send_pressed(ctl, hold)
        return _say(next(it))

    ctl = SimpleNamespace(
        engine=SimpleNamespace(streaming=False, transcribe_after=decode),
        cfg={"vad": False, "trailing_space": True, "all_caps": False, "out_cursor": True, "out_clipboard": False,
             "out_window": False, "paste_chord": "ctrl+v", "send_chord": "enter", "enter_guard": "late",
             "auto_enter": False, **(cfg or {})},
        sig=sig, inserter=SimpleNamespace(insert=lambda t, how, chord: pastes.append(t),
                                          press=lambda c: (sent.append(c), keys and pastes.append(("KEY", c)))),
        hotkeys=SimpleNamespace(holding=False, hold_send=lambda on: False),
        _take=1, _dropped=set(), _send_take=send_take, _jobs=queue.Queue(), _pasted_at=0.0,
        _guard=threading.Lock(), _unfinished={1}, _diverted=set(), _late={}, _enter_held=False, _hold_timer=None,
        _typed=False, state="recording", recorder=SimpleNamespace(paused=False), _silence=SimpleNamespace(heard=heard))
    for name in ("_show", "_insert", "_out", "_finish_take", "_sends", "_send", "_release_hold", "_replay_enter",
                 "_auto_enter"):
        setattr(ctl, name, getattr(Controller, name).__get__(ctl))
    for pause, final in jobs:
        if pause == "ENTER":
            ctl._jobs.put((1, None, False, 0))
        else:
            ctl._jobs.put((1, np.zeros(SR, np.float32), final, pause))
    threading.Thread(target=Controller._worker, args=(ctl,), daemon=True).start()
    assert done.wait(5)
    time.sleep(0.3)               # _finish_take runs after the transcript; a replayed Enter after 0.15 s
    return pastes[:-1], pastes[-1][1]


def test_enter_before_the_last_words_keeps_them_back():
    # R-2026-10-22-2: Enter pressed while the last piece decodes; the earlier piece was already
    # pasted (and sent), the rest is kept for Paste, and History still gets the whole take
    late = []
    pastes, text = _run_worker(["Send the arnona form.", "And the receipt."],
                               [(0.7, False), (None, True)], enter_at=1, late=late)
    assert pastes == ["Send the arnona form"]
    assert late == ["and the receipt."]       # joined at the seam: no held stop
    assert text == "Send the arnona form and the receipt."


def test_enter_guard_off_pastes_as_before():
    late = []
    pastes, _ = _run_worker(["Send the arnona form.", "And the receipt."],
                            [(0.7, False), (None, True)], {"enter_guard": "off"}, enter_at=1, late=late)
    assert pastes == ["Send the arnona form", " and the receipt. "] and late == []


def test_held_enter_is_replayed_after_the_last_paste():
    late, sent = [], []
    pastes, _ = _run_worker(["Send the arnona form.", "And the receipt."],
                            [(0.7, False), (None, True)], {"enter_guard": "hold"}, enter_at=1, hold=True,
                            late=late, sent=sent)
    assert pastes == ["Send the arnona form", " and the receipt. "] and late == []
    assert sent == ["enter"]


def test_early_enter_cancels_stop_and_send():
    # the user already sent: Stop and send must not press a second Enter into the next message
    sent = []
    _run_worker(["Done.", ""], [(0.7, False), (None, True)], send_take=1, sent=sent)
    assert sent == ["enter"]                       # without an early Enter, it sends
    sent.clear()
    _run_worker(["Done.", ""], [(0.7, False), (None, True)], enter_at=1, send_take=1, sent=sent)
    assert sent == []


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


def _level(s, dbfs, seed=0):
    """s seconds of noise at an RMS of dbfs."""
    return (np.random.default_rng(seed).standard_normal(int(s * SR)) * 10 ** (dbfs / 20)).astype(np.float32)


def test_last_piece_is_judged_by_the_take():
    # R-2026-10-25-3: a headset at its default gain (B-46: floor -76, soft speech about -41 dBFS).
    # The last piece alone stays under VAD_QUIET and was dropped; against the take it is speech.
    from hebrish.engine import has_speech
    take = np.concatenate([_level(1, -76, 1), _level(6, -30, 2), _level(1, -76, 3)])
    tail = np.concatenate([_level(0.4, -76, 4), _level(1.5, -45, 5), _level(0.3, -76, 6)])
    assert has_speech(tail, ref=take)                               # (and alone too since B-46's gate)
    assert not has_speech(_level(2, -74, 7), ref=take)          # room noise after Stop: still nothing


def test_last_piece_keeps_its_soft_speech():
    # shorten_silences must not take a soft last piece for a long silence
    from hebrish.engine import shorten_silences
    take = np.concatenate([_level(1, -76, 1), _level(6, -30, 2)])
    tail = _level(3, -45, 5)
    assert len(shorten_silences(tail)) < len(tail)
    assert len(shorten_silences(tail, ref=take)) == len(tail)


def test_a_quiet_take_is_speech():
    # B-46: a whole take on a headset at default gain (floor -76, speech -45 dBFS) was "no speech"
    from hebrish.engine import has_speech
    take = np.concatenate([_level(0.5, -76, 1), _level(1.5, -45, 2), _level(0.5, -76, 3)])
    assert has_speech(take)
    assert not has_speech(_level(3, -60, 4))                        # flat noise, however loud: nothing
    assert not has_speech(np.zeros(SR * 2, np.float32))


def test_unk_never_reaches_the_text():
    # Six history rows (2026-10-21 to 25) had "<unk>" at a clause break, e.g. "then<unk>and".
    from hebrish.engine import drop_unk
    assert drop_unk("then<unk>and don't") == "then and don't"
    assert drop_unk("manually<unk> we can") == "manually we can"
    assert drop_unk("helpful <unk> checking") == "helpful checking"
    assert drop_unk("no marks here") == "no marks here"


def test_beep_styles_are_well_formed():
    from hebrish.audio import BEEP_STYLE_NAMES, BEEP_STYLES, _pip
    import numpy as np
    assert DEFAULTS["beep_style"] == "soft" and {k for k, _ in BEEP_STYLE_NAMES} == set(BEEP_STYLES)
    peak = {k: float(np.abs(_pip(880, k, 0.25, 48000)).max()) for k in BEEP_STYLES}
    assert all(0 < v <= 0.25 for v in peak.values())
    assert peak["soft"] < 0.6 * peak["classic"]           # soft is clearly quieter
    assert DEFAULTS["quiet_sound"] == "off"               # quiet hours stay silent unless chosen


# -- Press Enter after silence (R-2026-10-31-1): the worker's Enter marker -------------------------

ON = {"auto_enter": True}


def test_enter_after_silence_follows_the_text_and_its_held_full_stop():
    pastes, text = _run_worker(["Fix the failing test.", "Thanks."],
                               [(0.7, False), ("ENTER", False), (None, True)], ON, keys=True)
    # the held full stop goes out before the Enter; the next words start a new message
    assert pastes == ["Fix the failing test", ".", ("KEY", "enter"), "Thanks. "]
    assert text == "Fix the failing test. Thanks."


def test_enter_after_silence_presses_the_send_key():
    sent = []
    _run_worker(["Ship it.", ""], [(0.7, False), ("ENTER", False), (None, True)],
                {**ON, "send_chord": "ctrl+enter"}, sent=sent)
    assert sent == ["ctrl+enter"]


def test_no_enter_after_silence_when_off_or_nothing_typed():
    sent = []
    _run_worker(["Ship it.", ""], [(0.7, False), ("ENTER", False), (None, True)], sent=sent)
    assert sent == []                                   # off by default
    _run_worker(["", ""], [(0.7, False), ("ENTER", False), (None, True)], ON, sent=sent)
    assert sent == []                                   # nothing typed


def test_no_enter_after_silence_once_speech_resumed():
    sent = []
    _run_worker(["Ship it.", ""], [(0.7, False), ("ENTER", False), (None, True)], ON, heard=SR, sent=sent)
    assert sent == []


def test_no_enter_after_silence_after_the_users_own_enter():
    # the user pressed Enter after the text went in: nothing typed since, so no second Enter,
    # and the held full stop isn't sent on its own
    sent = []
    pastes, text = _run_worker(["Ship it.", "", ""], [(0.7, False), (0.7, False), ("ENTER", False), (None, True)],
                               ON, enter_at=1, sent=sent)
    assert sent == [] and pastes == ["Ship it"] and text == "Ship it."


def test_enter_after_silence_once_per_batch():
    sent = []
    _run_worker(["One.", "Two.", ""],
                [(0.7, False), ("ENTER", False), ("ENTER", False), (0.7, False), ("ENTER", False), (None, True)],
                ON, sent=sent)
    assert sent == ["enter", "enter"]                   # the second marker had nothing new to send
