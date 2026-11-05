package app.hebrish.dictation

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

    @Test fun higherIsStricter() {
        for (l in 1 until 100) {
            assertTrue(VoiceDetection.minLoud(l + 1) > VoiceDetection.minLoud(l))
            assertTrue(VoiceDetection.minRatio(l + 1) > VoiceDetection.minRatio(l))
        }
    }
}
