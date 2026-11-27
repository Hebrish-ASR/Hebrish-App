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
        val rms = frameRms(samples)
        rms.sort()
        val noise = rms[frames / 10]
        val loud = rms[frames * 95 / 100]
        return loud < minLoud(level) || loud < noise * minRatio(level)
    }

    private fun frameRms(samples: FloatArray) = FloatArray(samples.size / FRAME) { f ->
        var sum = 0.0
        for (i in f * FRAME until (f + 1) * FRAME) sum += samples[i].toDouble() * samples[i]
        sqrt(sum / FRAME).toFloat()
    }

    /** The speech level of a piece that held speech: the 95th percentile of its 20 ms frames. */
    fun speechLevel(samples: FloatArray): Float {
        val rms = frameRms(samples)
        if (rms.size < MIN_FRAMES) return 0f
        rms.sort()
        return rms[rms.size * 95 / 100]
    }

    /**
     * True when a piece after speech holds only breath or murmur (desktop engine.faint, 1.046): under 1 s of
     * speech frames and under [FAINT_LOUD_FRAMES] frames within 18 dB of [takeLevel], the take's speech level so far, or before the
     * take's first text the [usualLevel] (0 = nothing to compare with). A real short last word ("Done.") is about as loud as the rest of the take.
     */
    fun faint(samples: FloatArray, takeLevel: Float): Boolean {
        val rms = frameRms(samples)
        if (takeLevel <= 0f || rms.isEmpty()) return false
        val sorted = rms.sortedArray()
        val noise = sorted[rms.size / 10]
        // Speech frames as Transcriber.speechFrames counts them: a longer soft passage is kept.
        val own = maxOf(0.003f, noise + (sorted[rms.size * 95 / 100] - noise) * 0.1f)
        if (rms.count { it > own } >= FAINT_MAX_SPEECH_FRAMES) return false
        val line = takeLevel * FAINT_RATIO
        return rms.count { it > line } < FAINT_LOUD_FRAMES
    }

    /**
     * The usual speech level (the [speechLevel] of pieces that gave text, a running mean), for pieces
     * before a take's first text: up to 1.037 a take's first piece, or a take of breath and room noise,
     * had nothing to be compared with and could come out as "My mother's mother" (desktop 1.047,
     * engine.faint_level, 2026-11-27). 0 = nothing learnt yet.
     */
    fun usualLevel(ctx: Context) = sp(ctx).getFloat("usual_speech_level", 0f)

    /** Learn from a piece that gave text: [USUAL_ALPHA] of the newest, so a new mic or gain is learnt within a few pieces. */
    fun learnLevel(ctx: Context, samples: FloatArray) {
        val level = speechLevel(samples)
        if (level <= 0f) return
        val old = usualLevel(ctx)
        sp(ctx).edit().putFloat("usual_speech_level", if (old <= 0f) level else old * (1 - USUAL_ALPHA) + level * USUAL_ALPHA).apply()
    }

    private const val USUAL_ALPHA = 0.2f
    private const val FAINT_RATIO = 0.12589f      // -18 dB
    private const val FAINT_MAX_SPEECH_FRAMES = 50   // 1 s
    private const val FAINT_LOUD_FRAMES = 4       // 0.08 s (0.06 up to 1.037: a breath at exactly 3 frames passed; desktop 1.047)
}
