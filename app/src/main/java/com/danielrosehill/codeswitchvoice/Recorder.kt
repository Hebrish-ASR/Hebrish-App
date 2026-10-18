package com.danielrosehill.codeswitchvoice

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder

/**
 * 16 kHz mono capture into memory. The model is offline (whole-utterance), so audio is
 * buffered until [stop] and handed over in one piece.
 */
class Recorder(private val onLevel: (Float) -> Unit, private val onLimit: () -> Unit) {
    companion object {
        // The sherpa-onnx export uses full attention, so memory grows with length; keep takes short.
        const val MAX_SECONDS = 90
    }

    @Volatile private var running = false
    private var thread: Thread? = null
    private var chunks = ArrayList<ShortArray>()

    @SuppressLint("MissingPermission") // Checked by the caller before start().
    fun start() {
        val rate = Transcriber.SAMPLE_RATE
        val minBuf = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val record = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION, rate,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(minBuf, rate),
        )
        chunks = ArrayList()
        running = true
        record.startRecording()
        thread = Thread {
            val buf = ShortArray(rate / 10)
            var total = 0
            try {
                while (running) {
                    val n = record.read(buf, 0, buf.size)
                    if (n <= 0) continue
                    chunks.add(buf.copyOf(n))
                    total += n
                    var peak = 0
                    for (i in 0 until n) peak = maxOf(peak, kotlin.math.abs(buf[i].toInt()))
                    onLevel(peak / 32768f)
                    if (total >= rate * MAX_SECONDS) {
                        running = false
                        onLimit()
                    }
                }
            } finally {
                record.stop()
                record.release()
            }
        }.apply { start() }
    }

    /** Stops capture and returns everything recorded as floats in [-1, 1]. */
    fun stop(): FloatArray {
        running = false
        thread?.join()
        thread = null
        val out = FloatArray(chunks.sumOf { it.size })
        var i = 0
        for (c in chunks) for (s in c) out[i++] = s / 32768f
        chunks = ArrayList()
        return out
    }

    fun cancel() {
        running = false
        thread?.join()
        thread = null
        chunks = ArrayList()
    }
}
