package app.hebrish.core

import android.annotation.SuppressLint
import android.os.Build
import android.media.AudioDeviceInfo
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
    /** The take reached [maxSeconds], or the microphone stopped delivering audio. Capture thread. */
    private val onLimit: () -> Unit,
    private val onSegment: ((FloatArray) -> Unit)? = null,
    /**
     * Hard cut when nobody pauses ([Segmenting.MAX_SECONDS] by default). The voice keyboard's Live
     * draft (I-4) sets a shorter one, because every draft pass re-decodes the whole open segment.
     */
    private val segmentMaxSeconds: Float = Segmenting.MAX_SECONDS,
    /**
     * Silence guard (2026-11-15, as desktop 1.035): called once per take, on the capture thread, when
     * [SilenceGuard.SECONDS] of the take have been recorded and no chunk peaked above
     * [SilenceGuard.PEAK]: the mic is muted (Android 12+'s privacy toggle delivers zeros), dead or
     * the wrong one, so nothing usable reaches the model. Capture carries on.
     */
    private val onSilence: (() -> Unit)? = null,
) {
    companion object {
        // The sherpa-onnx export uses full attention, so memory grows with length; keep takes short.
        const val MAX_SECONDS = 90
        /** Segmented takes never decode more than [Segmenting.MAX_SECONDS] at once, so they can be long. */
        const val MAX_SEGMENTED_SECONDS = 20 * 60
    }

    object SilenceGuard {
        const val SECONDS = 10
        /** -70 dBFS in 16-bit samples (32768 x 10^-3.5): below any working mic's noise floor. */
        const val PEAK = 10
        /** The start pip may be in the first ~0.1 s (Feedback): those chunks don't count. */
        const val SKIP_SECONDS = 0.5f

        /** True when a take of [samples] whose loudest counted chunk peaked at [loudest] is all silence. */
        fun silent(samples: Int, loudest: Int): Boolean =
            samples >= Transcriber.SAMPLE_RATE * SECONDS && loudest <= PEAK
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
        /**
         * Sound a segment must hold to be cut at a pause (desktop LIVE_CUT_SPEECH_S, 1.046): decoded alone, a
         * breath or murmur in 8 s of quiet comes back as a phrase nobody said ("My mother's mother"). With less,
         * it stays with what follows; nothing is dropped, and the hard cut is unchanged.
         */
        const val MIN_VOICED_SECONDS = 1f

        fun cutsAtPause(segment: Float, quiet: Float, voiced: Float): Boolean =
            segment >= MIN_SECONDS && quiet >= PAUSE_SECONDS && voiced >= MIN_VOICED_SECONDS
    }

    @Volatile private var running = false
    private var thread: Thread? = null
    /**
     * Guards [chunks] (and [cuts]) against [openSegment], which reads them from another thread (I-4).
     * Everything else touching them runs on the capture thread, or after [pause] has joined it.
     */
    private val chunkLock = Any()
    /** Segments handed to [onSegment] so far in this take. */
    private var cuts = 0
    private var chunks = ArrayList<ShortArray>()
    /** RMS of each chunk in [chunks], for choosing a hard cut. */
    private var chunkRms = ArrayList<Float>()
    /** Samples in each chunk of [chunks] that were above the silence line; 0 for a quiet chunk. */
    private var chunkVoiced = ArrayList<Int>()
    private var segmentSamples = 0
    private var silentSamples = 0
    /** Slowly tracked background level, so "silence" adapts to the room. */
    private var noiseFloor = 0.01f
    /** Loudest chunk peak of this take after [SilenceGuard.SKIP_SECONDS], and whether [onSilence] has fired. */
    private var loudest = 0
    private var silenceWarned = false

    /**
     * Microphone to ask for (AudioRecord.setPreferredDevice), or null for the system's choice.
     * Read at each [start], so it can change between takes and on resume. A Bluetooth headset
     * mic also needs the caller to route the call audio to it first (the app's Mic.route).
     * Android treats this as a preference: [routedDevice] says what it actually used.
     */
    @Volatile var preferredDevice: AudioDeviceInfo? = null

    /** The microphone capture is actually using, known once [start] has run; null before or if unknown. */
    @Volatile var routedDevice: AudioDeviceInfo? = null
        private set

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
        // API checks keep this compiling for Hebrish Keyboard (minSdk 21); the app is minSdk 28.
        // An AudioRecord that couldn't get the mic is STATE_UNINITIALIZED, and startRecording() on
        // it throws. Up to 0.7.0 `running` was set first and stayed true after that throw, so a later
        // Resume returned at once and "recorded" with no capture thread.
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            record.release()
            throw IllegalStateException("couldn't open the microphone")
        }
        val want = preferredDevice
        if (want != null && Build.VERSION.SDK_INT >= 23) record.setPreferredDevice(want)
        try {
            record.startRecording()
        } catch (e: Exception) {
            record.release()
            throw e
        }
        running = true
        if (Build.VERSION.SDK_INT >= 24) routedDevice = record.routedDevice
        thread = Thread {
            val buf = ShortArray(rate / 10)
            try {
                while (running) {
                    val n = record.read(buf, 0, buf.size)
                    if (n < 0) {
                        // The mic went away (ERROR_DEAD_OBJECT: a Bluetooth headset switched off, the
                        // audio server restarted). Up to 0.7.0 this spun on read() at full CPU until
                        // Stop. End the take like the length limit does, so what was heard is decoded.
                        if (running) {
                            running = false
                            onLimit()
                        }
                        break
                    }
                    if (n == 0) continue
                    val chunk = buf.copyOf(n)
                    synchronized(chunkLock) { chunks.add(chunk) }
                    samples += n
                    var peak = 0
                    var sum = 0.0
                    for (s in chunk) {
                        val v = s.toInt()
                        peak = maxOf(peak, kotlin.math.abs(v))
                        sum += v.toDouble() * v
                    }
                    onLevel(peak / 32768f)
                    if (samples - n >= rate * SilenceGuard.SKIP_SECONDS) loudest = maxOf(loudest, peak)
                    if (onSilence != null && !silenceWarned && SilenceGuard.silent(samples, loudest)) {
                        silenceWarned = true
                        onSilence.invoke()
                    }
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
        val quiet = rms < maxOf(0.004f, noiseFloor * 3)
        silentSamples = if (quiet) silentSamples + n else 0
        chunkVoiced.add(if (quiet) 0 else n)
        when {
            Segmenting.cutsAtPause(segmentSamples / rate.toFloat(), silentSamples / rate.toFloat(), chunkVoiced.sum() / rate.toFloat()) ->
                cut(chunks.size)
            segmentSamples >= rate * segmentMaxSeconds -> {
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
        val out = synchronized(chunkLock) {
            val head = toFloats(chunks.subList(0, k))
            chunks = ArrayList(chunks.subList(k, chunks.size))
            cuts++
            head
        }
        chunkRms = ArrayList(chunkRms.subList(k, chunkRms.size))
        chunkVoiced = ArrayList(chunkVoiced.subList(k, chunkVoiced.size))
        segmentSamples = chunks.sumOf { it.size }
        silentSamples = 0
        onSegment?.invoke(out)
    }

    /** The audio not yet handed to [onSegment] ([samples]), and how many segments came before it ([cut]). */
    class OpenSegment(val cut: Int, val samples: FloatArray)

    /**
     * A copy of the open segment, safe to call from any thread while recording (I-4, the voice
     * keyboard's Live draft). At most [Segmenting.MAX_SECONDS] (or the recorder's own cap) of audio.
     */
    fun openSegment(): OpenSegment = synchronized(chunkLock) { OpenSegment(cuts, toFloats(chunks)) }

    /** Stops capture and frees the microphone; the take so far is kept. */
    fun pause() {
        running = false
        thread?.join()
        thread = null
    }

    /** Stops capture and returns what was recorded (since the last segment cut) as floats in [-1, 1]. */
    fun stop(): FloatArray {
        pause()
        val out = synchronized(chunkLock) { toFloats(chunks) }
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
        synchronized(chunkLock) {
            chunks = ArrayList()
            cuts = 0
        }
        chunkRms = ArrayList()
        chunkVoiced = ArrayList()
        samples = 0
        segmentSamples = 0
        silentSamples = 0
        loudest = 0
        silenceWarned = false
    }
}
