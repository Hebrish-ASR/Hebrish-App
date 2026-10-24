package app.hebrish.core

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.SystemClock
import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Transcription Mode's recorder (R-2026-10-24-5; the desktop's longform.TapeRecorder): a long
 * take written to a WAV file as it is captured, so nothing is held in memory and a crash loses
 * at most the last [HEADER_EVERY_MS]. Files live in the app's own storage ([dir]), which needs no
 * storage permission (the I-10 question: no all-files access). A recording is deleted once its
 * transcript is in History; one that never got there is offered again ([leftovers]).
 *
 * [gainDb] is digital gain, applied before the meter and the file, so the meter shows what is
 * recorded. [clippedAt] is set for clipping at the input (no gain setting undoes it) and for
 * clipping the gain causes.
 */
class Tape(
    /** The take reached [MAX_SECONDS], or the mic stopped delivering audio. Capture thread. */
    private val onLimit: () -> Unit,
) {
    companion object {
        const val MAX_SECONDS = 4 * 60 * 60
        const val GAIN_MIN_DB = -12
        const val GAIN_MAX_DB = 24
        const val CLIP = 0.98f
        private const val HEADER = 44
        private const val HEADER_EVERY_MS = 2000L
        private const val RATE = Transcriber.SAMPLE_RATE

        fun dir(ctx: Context) = File(ctx.filesDir, "recordings")

        /** Recordings not yet transcribed (or whose transcription failed), oldest first. */
        fun leftovers(ctx: Context): List<File> =
            dir(ctx).listFiles { f -> f.name.startsWith("recording-") && f.name.endsWith(".wav") && f.length() > HEADER }
                ?.sortedBy { it.name } ?: emptyList()

        fun header(dataBytes: Int): ByteArray = ByteBuffer.allocate(HEADER).order(ByteOrder.LITTLE_ENDIAN).apply {
            put("RIFF".toByteArray()); putInt(36 + dataBytes); put("WAVEfmt ".toByteArray())
            putInt(16); putShort(1); putShort(1); putInt(RATE); putInt(RATE * 2); putShort(2); putShort(16)
            put("data".toByteArray()); putInt(dataBytes)
        }.array()

        /** Fixes the header of a recording the app didn't close; returns its length in seconds. */
        fun recover(f: File): Float {
            val n = ((f.length() - HEADER).coerceAtLeast(0) / 2 * 2).toInt()
            RandomAccessFile(f, "rw").use { it.seek(0); it.write(header(n)) }
            return n / 2f / RATE
        }

        /**
         * Reads [f] in 100 ms chunks and cuts it the way a live take is cut ([Recorder.Segmenting]:
         * at a pause after 8 s, hard at 28 s), handing each segment to [onSegment] and returning
         * the rest. Memory stays at one segment; [onSegment] may block to throttle the reading.
         * Stops early (returning nothing) when [cancelled] says so.
         */
        fun segments(f: File, cancelled: () -> Boolean, onSegment: (FloatArray) -> Unit): FloatArray {
            recover(f)
            val cut = Cutter(onSegment)
            f.inputStream().buffered(1 shl 16).use { input ->
                input.skip(HEADER.toLong())
                val bytes = ByteArray(RATE / 10 * 2)
                while (!cancelled()) {
                    var got = 0
                    while (got < bytes.size) { val r = input.read(bytes, got, bytes.size - got); if (r < 0) break; got += r }
                    if (got < 2) break
                    val chunk = ShortArray(got / 2)
                    ByteBuffer.wrap(bytes, 0, got).order(ByteOrder.LITTLE_ENDIAN).asShortBuffer().get(chunk)
                    cut.push(chunk)
                    if (got < bytes.size) break
                }
            }
            return if (cancelled()) FloatArray(0) else cut.rest()
        }
    }

    /** Recorder.segment's cutting, for audio read back from a file. Tuning stays in [Recorder.Segmenting]. */
    private class Cutter(private val onSegment: (FloatArray) -> Unit) {
        private var chunks = ArrayList<ShortArray>()
        private var chunkRms = ArrayList<Float>()
        private var segmentSamples = 0
        private var silentSamples = 0
        private var noiseFloor = 0.01f

        fun push(chunk: ShortArray) {
            var sum = 0.0
            for (s in chunk) sum += s.toDouble() * s
            val rms = (kotlin.math.sqrt(sum / chunk.size) / 32768).toFloat()
            chunks.add(chunk)
            chunkRms.add(rms)
            segmentSamples += chunk.size
            noiseFloor = if (rms < noiseFloor) (noiseFloor + rms) / 2 else noiseFloor * 0.998f + rms * 0.002f
            silentSamples = if (rms < maxOf(0.004f, noiseFloor * 3)) silentSamples + chunk.size else 0
            val s = Recorder.Segmenting
            when {
                segmentSamples >= RATE * s.MIN_SECONDS && silentSamples >= RATE * s.PAUSE_SECONDS -> cut(chunks.size)
                segmentSamples >= RATE * s.MAX_SECONDS -> {
                    var back = 0
                    var at = chunks.size
                    var best = Float.MAX_VALUE
                    for (i in chunks.indices.reversed()) {
                        back += chunks[i].size
                        if (back > RATE * s.LOOKBACK_SECONDS) break
                        if (chunkRms[i] < best) { best = chunkRms[i]; at = i + 1 }
                    }
                    cut(at)
                }
            }
        }

        private fun cut(k: Int) {
            val out = floats(chunks.subList(0, k))
            chunks = ArrayList(chunks.subList(k, chunks.size))
            chunkRms = ArrayList(chunkRms.subList(k, chunkRms.size))
            segmentSamples = chunks.sumOf { it.size }
            silentSamples = 0
            onSegment(out)
        }

        fun rest(): FloatArray = floats(chunks)

        private fun floats(cs: List<ShortArray>): FloatArray {
            val out = FloatArray(cs.sumOf { it.size })
            var i = 0
            for (c in cs) for (v in c) out[i++] = v / 32768f
            return out
        }
    }

    @Volatile var gainDb = 0f
    /** RMS and peak of the last 100 ms after gain, 0..1, for the meter. */
    @Volatile var rms = 0f
        private set
    @Volatile var peak = 0f
        private set
    /** SystemClock.elapsedRealtime() of the last clipped block; 0 = never. */
    @Volatile var clippedAt = 0L
        private set
    @Volatile var samples = 0
        private set
    val seconds: Int get() = samples / RATE
    @Volatile var paused = false
        private set
    /** The recording in progress, or null. */
    var file: File? = null
        private set
    val active: Boolean get() = file != null

    /** As Recorder.preferredDevice: read at each start and resume. */
    @Volatile var preferredDevice: AudioDeviceInfo? = null
    @Volatile var routedDevice: AudioDeviceInfo? = null
        private set

    @Volatile private var running = false
    private var thread: Thread? = null
    private var out: RandomAccessFile? = null
    private var headerAt = 0L

    /** Starts a new recording. Throws if the mic can't be opened (nothing is left behind). */
    fun start(ctx: Context) {
        if (active) return
        val d = dir(ctx).apply { mkdirs() }
        val stamp = java.text.SimpleDateFormat("yyyy-MM-dd-HHmmss", java.util.Locale.US).format(java.util.Date())
        val f = File(d, "recording-$stamp.wav")
        out = RandomAccessFile(f, "rw").apply { setLength(0); write(header(0)) }
        file = f
        samples = 0
        clippedAt = 0L
        paused = false
        try {
            open()
        } catch (e: Exception) {
            out?.close(); out = null; file = null
            f.delete()
            throw e
        }
    }

    @SuppressLint("MissingPermission") // Checked by the caller.
    private fun open() {
        val minBuf = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val record = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, RATE,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(minBuf, RATE))
        if (record.state != AudioRecord.STATE_INITIALIZED) {
            record.release()
            throw IllegalStateException("couldn't open the microphone")
        }
        preferredDevice?.let { if (Build.VERSION.SDK_INT >= 23) record.setPreferredDevice(it) }
        try { record.startRecording() } catch (e: Exception) { record.release(); throw e }
        running = true
        if (Build.VERSION.SDK_INT >= 24) routedDevice = record.routedDevice
        thread = Thread {
            val buf = ShortArray(RATE / 10)
            val bytes = ByteBuffer.allocate(buf.size * 2).order(ByteOrder.LITTLE_ENDIAN)
            try {
                while (running) {
                    val n = record.read(buf, 0, buf.size)
                    if (n < 0) {               // the mic went away (Bluetooth off, audio server restart)
                        if (running) { running = false; onLimit() }
                        break
                    }
                    if (n == 0) continue
                    write(buf, n, bytes)
                    if (samples >= RATE * MAX_SECONDS) { running = false; onLimit() }
                }
            } finally {
                record.stop()
                record.release()
            }
        }.apply { start() }
    }

    /** Capture thread: gain, meter, then the file. */
    private fun write(buf: ShortArray, n: Int, bytes: ByteBuffer) {
        val g = Math.pow(10.0, gainDb / 20.0).toFloat()
        var inPeak = 0f
        var pk = 0f
        var sum = 0.0
        bytes.clear()
        for (i in 0 until n) {
            val x = buf[i] / 32768f
            inPeak = maxOf(inPeak, kotlin.math.abs(x))
            val y = (x * g).coerceIn(-1f, 1f)
            pk = maxOf(pk, kotlin.math.abs(y))
            sum += y.toDouble() * y
            bytes.putShort((y * 32767).toInt().toShort())
        }
        rms = kotlin.math.sqrt(sum / n).toFloat()
        peak = pk
        if (inPeak >= CLIP || pk >= CLIP) clippedAt = SystemClock.elapsedRealtime()
        synchronized(this) {
            val o = out ?: return
            o.write(bytes.array(), 0, n * 2)
            samples += n
            if (SystemClock.elapsedRealtime() - headerAt > HEADER_EVERY_MS) flushHeader()
        }
    }

    /** Rewrites the sizes so the file on disk is a valid WAV up to now. Holds the monitor. */
    private fun flushHeader() {
        val o = out ?: return
        val pos = o.filePointer
        o.seek(0)
        o.write(header(samples * 2))
        o.seek(pos)
        headerAt = SystemClock.elapsedRealtime()
    }

    private fun close() {
        running = false
        thread?.join()
        thread = null
        rms = 0f
        peak = 0f
    }

    /** Releases the mic and keeps the file open, so [resume] carries on in it. */
    fun pause() {
        if (!active || paused) return
        close()
        paused = true
        synchronized(this) { flushHeader() }
    }

    fun resume() {
        if (!active || !paused) return
        open()
        paused = false
    }

    /** Switches the mic mid-recording (or for the next resume when paused). */
    fun switchTo(device: AudioDeviceInfo?) {
        preferredDevice = device
        if (active && !paused) { close(); open() }
    }

    /** Ends the recording; returns the file, or null if nothing was captured. */
    fun stop(): File? {
        close()
        val f = file
        synchronized(this) {
            flushHeader()
            out?.close()
            out = null
        }
        file = null
        paused = false
        if (f != null && samples == 0) { f.delete(); return null }
        return f
    }

    fun discard() {
        stop()?.delete()
    }
}
