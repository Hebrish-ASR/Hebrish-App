package app.hebrish.dictation

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.os.VibrationEffect
import android.os.Vibrator
import kotlin.math.PI
import kotlin.math.min
import kotlin.math.sin

/**
 * Short sounds and buzzes for the moments of a take, so a take can be started and stopped
 * without looking (a Bluetooth button, the phone in a pocket). Sounds are on with
 * Prefs.beeps, buzzes with Prefs.vibrate; both are set on the Sound, microphone and buttons screen.
 *
 * Each cue is a few tens of milliseconds of synthesised sine, played with the "sonification"
 * audio usage, so it goes wherever system sounds go (a connected Bluetooth headset included).
 * - [Cue.START]: one rising pip. [Cue.STOP]: one falling pip.
 * - [Cue.RESTART]: a quick double pip (Retake). [Cue.DISCARD]: one low pip.
 *
 * The start pip plays as recording starts, so the first ~0.1 s of a take may hold it; the model
 * has been fine with that in desktop use of the same idea (I: not yet checked on a phone).
 */
object Feedback {
    enum class Cue { START, STOP, RESTART, DISCARD }

    private const val RATE = 44_100

    fun cue(ctx: Context, cue: Cue) {
        if (Prefs.beeps(ctx)) Thread { runCatching { play(cue) } }.start()
        if (Prefs.vibrate(ctx)) buzz(ctx, cue)
    }

    /** Plays a cue regardless of the setting: the screen's Test buttons. */
    fun preview(cue: Cue) = Thread { runCatching { play(cue) } }.start()

    /** (frequency Hz, duration ms) steps; frequency 0 = silence. */
    private fun steps(cue: Cue) = when (cue) {
        Cue.START -> listOf(660 to 45, 990 to 55)
        Cue.STOP -> listOf(990 to 45, 660 to 55)
        Cue.RESTART -> listOf(990 to 45, 0 to 55, 990 to 45)
        Cue.DISCARD -> listOf(330 to 110)
    }

    private fun play(cue: Cue) {
        val pcm = synth(steps(cue))
        val track = AudioTrack.Builder()
            .setAudioAttributes(AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANCE_SONIFICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build())
            .setAudioFormat(AudioFormat.Builder().setSampleRate(RATE)
                .setEncoding(AudioFormat.ENCODING_PCM_16BIT).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
            .setTransferMode(AudioTrack.MODE_STATIC)
            .setBufferSizeInBytes(pcm.size * 2)
            .build()
        try {
            track.write(pcm, 0, pcm.size)
            track.play()
            Thread.sleep(pcm.size * 1000L / RATE + 60)
        } finally {
            track.release()
        }
    }

    /** Sine steps at 35% of full scale, each with 4 ms fades so they don't click. */
    private fun synth(steps: List<Pair<Int, Int>>): ShortArray {
        val out = ShortArray(steps.sumOf { it.second } * RATE / 1000)
        var i = 0
        for ((hz, ms) in steps) {
            val n = ms * RATE / 1000
            val fade = min(n / 2, 4 * RATE / 1000)
            for (k in 0 until n) {
                val env = min(1f, min(k, n - 1 - k) / fade.toFloat())
                val v = if (hz == 0) 0.0 else sin(2 * PI * hz * k / RATE) * 0.35 * env
                out[i++] = (v * Short.MAX_VALUE).toInt().toShort()
            }
        }
        return out
    }

    private fun buzz(ctx: Context, cue: Cue) {
        val v = ctx.getSystemService(Vibrator::class.java) ?: return
        if (!v.hasVibrator()) return
        val effect = when (cue) {
            Cue.START -> VibrationEffect.createOneShot(40, VibrationEffect.DEFAULT_AMPLITUDE)
            Cue.STOP -> VibrationEffect.createOneShot(25, VibrationEffect.DEFAULT_AMPLITUDE)
            Cue.RESTART -> VibrationEffect.createWaveform(longArrayOf(0, 30, 70, 30), -1)
            Cue.DISCARD -> VibrationEffect.createOneShot(80, VibrationEffect.DEFAULT_AMPLITUDE)
        }
        runCatching { v.vibrate(effect) }
    }
}
