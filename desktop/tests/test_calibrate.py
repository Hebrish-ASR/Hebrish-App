"""Noise filter calibration: the two limits, Safe and Optimized, the saved figures, the dialog."""

import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from hebrish import calibrate  # noqa: E402
from hebrish.calibrate import FRAME, SAMPLE_RATE, measure  # noqa: E402
from hebrish.history import History  # noqa: E402

rng = np.random.default_rng(0)


def noise(s, amp=0.001):
    return (rng.standard_normal(int(s * SAMPLE_RATE)) * amp).astype(np.float32)


class Fake:
    """Speech is kept up to `keep`; the room stops counting as speech at `room`; soft speech past `keep`."""

    def __init__(self, keep, room, lost=0.05):
        self.keep, self.room, self.lost, self.level, self.calls = keep, room, lost, 0, 0

    def set_level(self, level):
        self.level = level

    def speech_frames(self, x, frame):
        self.calls += 1
        n = len(x) // frame
        m = np.zeros(n, bool)
        if self.calls % 2:              # measure() asks about the quiet recording first
            if self.level < self.room:
                m[:] = True
        else:
            m[:] = True
            if self.level > self.keep:
                m[: int(n * self.lost * (self.level - self.keep) / 5)] = False
        return m


def talk(s):
    """Word-sized bursts with gaps."""
    x = noise(s, 0.1)
    w = SAMPLE_RATE // 10
    for i in range(0, len(x), 4 * w):
        x[i + 3 * w: i + 4 * w] *= 0.01
    return x


def run(keep, room):
    return measure(noise(5), talk(10), Fake(keep, room))


def test_a_clean_gap_gives_two_settings_inside_it():
    r = run(keep=80, room=40)
    assert r.clean and r.noise_beaten and not r.clips
    assert 40 <= r.safe <= r.optimized <= 80
    assert r.safe_noise_s < 0.25 and r.optimized_kept >= calibrate.KEEP


def test_crossed_limits_are_a_trade_off():
    r = run(keep=45, room=70)
    assert not r.clean and (r.safe, r.optimized) == (45, 70)
    assert r.safe_kept >= calibrate.KEEP and r.safe_noise_s > 1       # Safe lets noise through
    assert r.optimized_kept < r.safe_kept and r.optimized_noise_s < 0.25   # Optimized clips


def test_a_quiet_sample_doesnt_send_safe_to_zero():
    assert run(keep=100, room=0).safe == calibrate.SAFE_MIN


def test_a_room_that_beats_the_filter_says_so():
    r = run(keep=60, room=500)
    assert not r.noise_beaten and not r.clean and r.optimized == 100


def test_trimmed_edges_are_not_lost_speech():
    # found on real speech, 2026-11-05: frame counting gave silent rooms the lowest suggestions
    ref = np.zeros(100, bool)
    ref[10:30] = ref[50:90] = True
    runs = calibrate.bursts(ref)
    assert runs == [(10, 30), (50, 90)]
    mask = ref.copy()
    mask[10:14] = mask[86:90] = False                  # both words lose their edges
    assert calibrate.kept_share(runs, mask) == 1
    mask[10:30] = False                                # a whole word is lost
    assert calibrate.kept_share(runs, mask) == 40 / 60


def test_short_gaps_join_and_clicks_are_dropped():
    ref = np.zeros(40, bool)
    ref[5:12] = ref[14:20] = ref[30:32] = True
    assert calibrate.bursts(ref) == [(5, 20)]


def test_no_speech_gives_no_suggestion():
    r = measure(noise(5), noise(10), Fake(50, 50))
    assert not r.heard_speech and (r.safe, r.optimized) == (0, 0)


def test_history_keeps_runs_and_what_was_applied(tmp_path):
    h = History(tmp_path / "h.db")
    a = h.add_calibration("Yeti", -60.2, -22.5, 45, 70, at=1)
    h.add_calibration("Laptop mic", -50, -25, 30, 55, at=2)
    h.set_calibration_applied(a, 70)
    rows = h.calibrations()
    assert [r["mic"] for r in rows] == ["Laptop mic", "Yeti"]
    assert rows[0]["applied"] is None and rows[1]["applied"] == 70
    h.close()


def test_a_new_table_arrives_in_an_existing_history(tmp_path):
    p = tmp_path / "h.db"
    h = History(p)
    h.db.execute("DROP TABLE calibrations")
    h.close()
    h = History(p)
    assert h.calibrations() == []
    h.close()


def test_dialog_shows_a_result_and_applies_it(tmp_path):
    from PySide6.QtWidgets import QApplication
    from hebrish.ui import calibrate as ui
    QApplication.instance() or QApplication([])

    class Ctl:
        history = History(tmp_path / "h.db")
        cfg = {"audio_device": "Yeti"}
        state = "idle"

        def stop_monitor(self):
            pass

    applied = []
    d = ui.CalibrateDialog(None, Ctl(), applied.append)
    r = run(keep=45, room=70)
    d._show(r, None)
    assert "Safe: 45" in d.btn_safe.text() and "Optimized: 70" in d.btn_opt.text()
    assert not d.btn_opt.isHidden() and d.table.rowCount() == 1
    d.btn_opt.click()
    assert applied == [70] and Ctl.history.calibrations()[0]["applied"] == 70
    assert d.table.item(0, 6).text() == "70"

    d._show(measure(noise(5), noise(10), Fake(50, 50)), None)      # no speech: nothing saved or offered
    assert d.btn_start.isEnabled() and d.table.rowCount() == 1
    Ctl.history.close()


def test_a_room_the_filter_cant_beat_offers_nothing(tmp_path):
    from PySide6.QtWidgets import QApplication
    from hebrish.ui import calibrate as ui
    QApplication.instance() or QApplication([])

    class Ctl:
        history = History(tmp_path / "h.db")
        cfg = {"audio_device": "Yeti"}

    d = ui.CalibrateDialog(None, Ctl(), lambda level: None)
    d._show(run(keep=60, room=500), None)
    assert d.btn_safe.isHidden() and d.btn_opt.isHidden() and Ctl.history.calibrations() == []
    Ctl.history.close()


def test_every_outcome_has_words():
    for r in (run(80, 40), run(45, 70), run(60, 500), measure(noise(5), noise(10), Fake(50, 50))):
        from hebrish.ui.calibrate import summary
        assert summary(r)
