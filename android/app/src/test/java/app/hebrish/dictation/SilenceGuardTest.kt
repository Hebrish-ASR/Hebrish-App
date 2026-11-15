package app.hebrish.dictation

import app.hebrish.core.Recorder.SilenceGuard
import app.hebrish.core.Transcriber
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Silence guard (2026-11-15): 10 s recorded with no chunk above -70 dBFS warns; anything else doesn't. */
class SilenceGuardTest {
    private val tenSeconds = Transcriber.SAMPLE_RATE * SilenceGuard.SECONDS

    @Test fun digitalSilenceForTenSecondsWarns() = assertTrue(SilenceGuard.silent(tenSeconds, 0))
    @Test fun atTheThresholdStillWarns() = assertTrue(SilenceGuard.silent(tenSeconds, SilenceGuard.PEAK))
    @Test fun underTenSecondsDoesNot() = assertFalse(SilenceGuard.silent(tenSeconds - 1, 0))
    @Test fun quietRoomNoiseDoesNot() = assertFalse(SilenceGuard.silent(tenSeconds, 33))   // about -60 dBFS
}
