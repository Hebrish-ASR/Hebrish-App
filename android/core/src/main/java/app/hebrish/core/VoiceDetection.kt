package app.hebrish.core

import android.content.Context
import kotlin.math.pow
import kotlin.math.sqrt

/**
 * Noise filter, 0-100 (Daniel, 2026-11-05): room noise came out as stray words, so a piece that is
 * only background is not decoded. The same dial as desktop's `vad_noise_filter`, but a different
 * rule underneath: Android has no Silero yet (B-71a), so this measures loudness. 0 is off, which is
 * how Android behaved up to 1.015 (a piece with no clear speech was decoded whole).
 *
 * Kept milder than [Transcriber.trim]'s rule on purpose: the Recorder cuts pieces at pauses, so a
 * piece of steady talking holds little silence, and dropping real speech is worse than a stray word.
 */
object VoiceDetection {
    const val DEFAULT = 60
    private const val FRAME = 320                 // 20 ms at 16 kHz
    private const val MIN_FRAMES = 10             // as Transcriber: too short to judge, so it is kept

    private fun sp(ctx: Context) = ctx.getSharedPreferences("prefs", Context.MODE_PRIVATE)

    fun level(ctx: Context) = sp(ctx).getInt("noise_filter", DEFAULT)
    fun setLevel(ctx: Context, v: Int) = sp(ctx).edit().putInt("noise_filter", v.coerceIn(0, 100)).apply()

    /** The loudest speech must reach this (RMS): 0.01 at 50, 0.0316 at 100. */
    fun minLoud(level: Int) = 0.01f * 10f.pow((level - 50) / 100f)

    /** The loudest frames must stand this far above the background: 2.0 at 50, 2.75 at 100. */
    fun minRatio(level: Int) = 1.25f + 0.015f * level

    /** True when [samples] are background only, so decoding them could only invent words. */
    fun noiseOnly(samples: FloatArray, level: Int): Boolean {
        val frames = samples.size / FRAME
        if (level <= 0 || frames < MIN_FRAMES) return false
        val rms = FloatArray(frames) { f ->
            var sum = 0.0
            for (i in f * FRAME until (f + 1) * FRAME) sum += samples[i].toDouble() * samples[i]
            sqrt(sum / FRAME).toFloat()
        }
        rms.sort()
        val noise = rms[frames / 10]
        val loud = rms[frames * 95 / 100]
        return loud < minLoud(level) || loud < noise * minRatio(level)
    }
}
