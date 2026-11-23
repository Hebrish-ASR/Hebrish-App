package app.hebrish.dictation

import app.hebrish.core.Recorder
import app.hebrish.core.VoiceDetection
import kotlin.math.PI
import kotlin.math.sin
import kotlin.random.Random
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class VoiceDetectionTest {
    private val rate = 16000

    private fun hiss(seconds: Float, amp: Float, r: Random = Random(1)) =
        FloatArray((rate * seconds).toInt()) { (r.nextFloat() * 2 - 1) * amp }

    /** Bursts of tone over a hiss, with gaps: the loudness shape of speech. */
    private fun talking(seconds: Float, amp: Float, floor: Float): FloatArray {
        val x = hiss(seconds, floor)
        for (i in x.indices) if ((i / (rate / 4)) % 2 == 0) x[i] += amp * sin(2 * PI * 200 * i / rate).toFloat()
        return x
    }

    @Test fun steadyRoomNoiseIsDropped() = assertTrue(VoiceDetection.noiseOnly(hiss(2f, 0.05f), VoiceDetection.DEFAULT))

    @Test fun nearSilenceIsDropped() = assertTrue(VoiceDetection.noiseOnly(hiss(2f, 0.002f), VoiceDetection.DEFAULT))

    @Test fun speechOverNoiseIsKept() = assertFalse(VoiceDetection.noiseOnly(talking(2f, 0.2f, 0.01f), VoiceDetection.DEFAULT))

    @Test fun quietSpeechIsKeptAtTheDefault() = assertFalse(VoiceDetection.noiseOnly(talking(2f, 0.03f, 0.002f), VoiceDetection.DEFAULT))

    @Test fun zeroIsOff() = assertFalse(VoiceDetection.noiseOnly(hiss(2f, 0.05f), 0))

    @Test fun tooShortToJudgeIsKept() = assertFalse(VoiceDetection.noiseOnly(hiss(0.1f, 0.05f), 100))

    /** 2026-11-24, as desktop 1.046: a breath after speech, or alone in 8 s of quiet, must not be decoded by itself. */
    @Test fun faintTailIsDropped() {
        val level = VoiceDetection.speechLevel(talking(8f, 0.2f, 0.001f))
        assertTrue(VoiceDetection.faint(talking(1f, 0.2f * 0.04f, 0.0005f), level))      // 28 dB under the take
        assertFalse(VoiceDetection.faint(talking(0.5f, 0.2f, 0.001f), level))            // a short real last word
        assertFalse(VoiceDetection.faint(talking(0.5f, 0.2f * 0.2f, 0.001f), level))     // a soft one, 14 dB under
        assertFalse(VoiceDetection.faint(talking(6f, 0.2f * 0.04f, 0.0005f), level))     // a long soft passage is kept
        assertFalse(VoiceDetection.faint(talking(1f, 0.008f, 0.0005f), 0f))              // nothing to compare with
    }

    @Test fun breathAloneIsNotCut() {
        assertFalse(Recorder.Segmenting.cutsAtPause(8.5f, 1f, 0.5f))
        assertTrue(Recorder.Segmenting.cutsAtPause(8.5f, 1f, 3f))
        assertFalse(Recorder.Segmenting.cutsAtPause(5f, 1f, 3f))
    }

    @Test fun higherIsStricter() {
        for (l in 1 until 100) {
            assertTrue(VoiceDetection.minLoud(l + 1) > VoiceDetection.minLoud(l))
            assertTrue(VoiceDetection.minRatio(l + 1) > VoiceDetection.minRatio(l))
        }
    }
}
