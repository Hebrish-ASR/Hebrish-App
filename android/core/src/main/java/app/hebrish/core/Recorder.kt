package app.hebrish.core

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder

/**
 * 16 kHz mono capture into memory. The model is offline (whole-utterance), so audio is
 * buffered until [stop] and handed over in one piece. A take can be paused and resumed:
 * [pause] releases the microphone and keeps what was recorded, [start] appends to it.
 *
 * With [onSegment] set, the take is cut into segments at pauses while it is still being
 * recorded (see [Segmenting]) and each finished segment is handed to [onSegment] on the
 * capture thread, so the caller can decode it while the user keeps talking ([TakeDecoder]).
 * [stop] then returns only the audio after the last cut, and a take may run to
 * [MAX_SEGMENTED_SECONDS] instead of [MAX_SECONDS].
 */
class Recorder(
    private val onLevel: (Float) -> Unit,
    private val onLimit: () -> Unit,
    private val onSegment: ((FloatArray) -> Unit)? = null,
) {
    companion object {
        // The sherpa-onnx export uses full attention, so memory grows with length; keep takes short.
        const val MAX_SECONDS = 90
        /** Segmented takes never decode more than [Segmenting.MAX_SECONDS] at once, so they can be long. */
        const val MAX_SEGMENTED_SECONDS = 20 * 60
    }

    /** Where cuts go. Times are in seconds of audio. */
    object Segmenting {
        /** No cut before a segment has this much audio: short takes stay one piece. */
        const val MIN_SECONDS = 8f
        /** A pause at least this long ends a segment (the model also wants ≥0.6 s of trailing silence). */
        const val PAUSE_SECONDS = 0.6f
        /** Hard cut, at the quietest moment of the last [LOOKBACK_SECONDS], if nobody pauses. */
        const val MAX_SECONDS = 28f
        const val LOOKBACK_SECONDS = 4f
    }

    @Volatile private var running = false
    private var thread: Thread? = null
    private var chunks = ArrayList<ShortArray>()
    /** RMS of each chunk in [chunks], for choosing a hard cut. */
    private var chunkRms = ArrayList<Float>()
    private var segmentSamples = 0
    private var silentSamples = 0
    /** Slowly tracked background level, so "silence" adapts to the room. */
    private var noiseFloor = 0.01f

    /** Samples recorded so far in this take, across pauses and segments. */
    @Volatile var samples = 0
        private set

    val seconds: Int get() = samples / Transcriber.SAMPLE_RATE

    /** The longest take this recorder allows, in seconds. */
    val maxSeconds: Int get() = if (onSegment == null) MAX_SECONDS else MAX_SEGMENTED_SECONDS

    /** Starts capture, or resumes it after [pause]. */
    @SuppressLint("MissingPermission") // Checked by the caller before start().
    fun start() {
        if (running) return
        val rate = Transcriber.SAMPLE_RATE
        if (samples >= rate * maxSeconds) return onLimit()
        val minBuf = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val record = AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION, rate,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(minBuf, rate),
        )
        running = true
        record.startRecording()
        thread = Thread {
            val buf = ShortArray(rate / 10)
            try {
                while (running) {
                    val n = record.read(buf, 0, buf.size)
                    if (n <= 0) continue
                    val chunk = buf.copyOf(n)
                    chunks.add(chunk)
                    samples += n
                    var peak = 0
                    var sum = 0.0
                    for (s in chunk) {
                        val v = s.toInt()
                        peak = maxOf(peak, kotlin.math.abs(v))
                        sum += v.toDouble() * v
                    }
                    onLevel(peak / 32768f)
                    if (onSegment != null) segment(chunk.size, (kotlin.math.sqrt(sum / chunk.size) / 32768).toFloat())
                    if (samples >= rate * maxSeconds) {
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

    /** Called on the capture thread after each chunk: cuts at a pause, or hard-cuts a long run. */
    private fun segment(n: Int, rms: Float) {
        val rate = Transcriber.SAMPLE_RATE
        chunkRms.add(rms)
        segmentSamples += n
        noiseFloor = if (rms < noiseFloor) (noiseFloor + rms) / 2 else noiseFloor * 0.998f + rms * 0.002f
        silentSamples = if (rms < maxOf(0.004f, noiseFloor * 3)) silentSamples + n else 0
        when {
            segmentSamples >= rate * Segmenting.MIN_SECONDS && silentSamples >= rate * Segmenting.PAUSE_SECONDS ->
                cut(chunks.size)
            segmentSamples >= rate * Segmenting.MAX_SECONDS -> {
                // Nobody paused: cut after the quietest chunk of the last few seconds.
                var back = 0
                var at = chunks.size
                var best = Float.MAX_VALUE
                for (i in chunks.indices.reversed()) {
                    back += chunks[i].size
                    if (back > rate * Segmenting.LOOKBACK_SECONDS) break
                    if (chunkRms[i] < best) { best = chunkRms[i]; at = i + 1 }
                }
                cut(at)
            }
        }
    }

    /** Hands chunks [0, k) to [onSegment] and keeps the rest as the start of the next segment. */
    private fun cut(k: Int) {
        val out = toFloats(chunks.subList(0, k))
        chunks = ArrayList(chunks.subList(k, chunks.size))
        chunkRms = ArrayList(chunkRms.subList(k, chunkRms.size))
        segmentSamples = chunks.sumOf { it.size }
        silentSamples = 0
        onSegment?.invoke(out)
    }

    /** Stops capture and frees the microphone; the take so far is kept. */
    fun pause() {
        running = false
        thread?.join()
        thread = null
    }

    /** Stops capture and returns what was recorded (since the last segment cut) as floats in [-1, 1]. */
    fun stop(): FloatArray {
        pause()
        val out = toFloats(chunks)
        reset()
        return out
    }

    fun cancel() {
        pause()
        reset()
    }

    private fun toFloats(cs: List<ShortArray>): FloatArray {
        val out = FloatArray(cs.sumOf { it.size })
        var i = 0
        for (c in cs) for (s in c) out[i++] = s / 32768f
        return out
    }

    private fun reset() {
        chunks = ArrayList()
        chunkRms = ArrayList()
        samples = 0
        segmentSamples = 0
        silentSamples = 0
    }
}
