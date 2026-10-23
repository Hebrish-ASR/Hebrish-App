package app.hebrish.core

import android.content.Context
import android.os.SystemClock
import java.util.concurrent.Executors

/**
 * Decodes one take while it is still being recorded. Pair it with a [Recorder] whose
 * `onSegment` calls [add]: every segment the recorder cuts at a pause is decoded at once on a
 * single worker thread, in order. When the user stops, [finish] decodes only the audio since the
 * last cut, so the wait after Stop is the tail of the take, not all of it.
 *
 * With [onText] set, each segment's text is handed over as soon as it is decoded ("type as you
 * go"), and [finish] returns only what has not been handed over yet. Without it, [finish] returns
 * the whole take. Callbacks run on the worker thread. Text goes through [OutputStyle], read once
 * per take, so a take never changes style halfway.
 */
class TakeDecoder(ctx: Context, private val onText: ((String) -> Unit)? = null) {
    private val app = ctx.applicationContext
    private val worker = Executors.newSingleThreadExecutor()
    private val held = StringBuilder()
    private val allCaps = OutputStyle.allCaps(app)
    @Volatile private var cancelled = false
    @Volatile private var failure: Throwable? = null
    @Volatile var segmentsDecoded = 0
        private set
    /** Segments handed to [add] so far; a take with any is never "too short". */
    @Volatile var segmentsQueued = 0
        private set

    /**
     * What one take cost (0.8.1, for the history export: "see how the Android inference is
     * doing", Daniel 2026-10-23). Times are wall clock on the worker thread. [decodeSeconds] is
     * the sum of every Transcriber.transcribe call (trim + pad + sherpa-onnx decode) and excludes
     * [loadSeconds], the model load a take paid when the model was not in memory yet.
     * [waitSeconds] is Stop to text: what the user actually waited.
     */
    data class Stats(
        val audioSeconds: Double,
        val decodeSeconds: Double,
        val loadSeconds: Double,
        val waitSeconds: Double,
        val segments: Int,
        val allCaps: Boolean,
        val typeAsYouGo: Boolean,
    )

    private val all = StringBuilder()
    @Volatile private var audioSamples = 0L
    @Volatile private var decodeMs = 0L
    @Volatile private var loadMs = 0L
    @Volatile private var waitMs = 0L

    /** The whole take's text, including parts already handed to [onText]. Valid once [finish] is done. */
    val text: String get() = synchronized(all) { all.toString() }

    /** Valid once [finish] has called back. */
    fun stats() = Stats(audioSamples / Transcriber.SAMPLE_RATE.toDouble(), decodeMs / 1000.0, loadMs / 1000.0,
        waitMs / 1000.0, segmentsDecoded, allCaps, onText != null)

    /** Worker thread only: loads the model if needed (timed apart), then decodes (timed). */
    private fun timedTranscribe(samples: FloatArray): String {
        if (!Transcriber.isLoaded(app)) {
            val t = SystemClock.elapsedRealtime()
            Transcriber.load(app)
            loadMs += SystemClock.elapsedRealtime() - t
        }
        val t = SystemClock.elapsedRealtime()
        return Transcriber.transcribe(app, samples).also { decodeMs += SystemClock.elapsedRealtime() - t }
    }

    private fun keep(text: String) = synchronized(all) { all.append(if (all.isEmpty()) "" else " ").append(text) }

    /** Queues one recorded segment. Called from the recorder's capture thread. */
    fun add(samples: FloatArray) {
        if (cancelled) return
        segmentsQueued++
        audioSamples += samples.size
        // runCatching: a cancel racing this call has already shut the worker down.
        runCatching { worker.execute {
            if (cancelled || failure != null) return@execute
            runCatching { timedTranscribe(samples) }
                .onSuccess { decoded ->
                    val text = OutputStyle.apply(decoded, allCaps)
                    segmentsDecoded++
                    if (text.isEmpty() || cancelled) return@onSuccess
                    keep(text)
                    if (onText != null) onText.invoke(text) else held.append(if (held.isEmpty()) "" else " ").append(text)
                }
                .onFailure { failure = it }
        } }
    }

    /**
     * Decodes [tail] after every queued segment, then calls [done] with the text not yet handed
     * to [onText]. A tail under [minTail] samples is skipped (a tap on Stop right after a cut).
     */
    fun finish(tail: FloatArray, minTail: Int = Transcriber.SAMPLE_RATE / 4, done: (Result<String>) -> Unit) {
        val stopped = SystemClock.elapsedRealtime()
        audioSamples += tail.size
        worker.execute {
            val result = runCatching {
                failure?.let { throw it }
                val last = if (tail.size >= minTail) OutputStyle.apply(timedTranscribe(tail), allCaps) else ""
                if (last.isNotEmpty()) keep(last)
                listOf(held.toString(), last).filter { it.isNotEmpty() }.joinToString(" ")
            }
            waitMs = SystemClock.elapsedRealtime() - stopped
            if (!cancelled) done(result)
        }
        worker.shutdown()
    }

    /** Drops the take: queued segments are skipped and no callback fires. */
    fun cancel() {
        cancelled = true
        worker.shutdownNow()
    }
}
