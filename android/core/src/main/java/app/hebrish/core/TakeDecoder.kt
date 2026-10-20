package app.hebrish.core

import android.content.Context
import java.util.concurrent.Executors

/**
 * Decodes one take while it is still being recorded. Pair it with a [Recorder] whose
 * `onSegment` calls [add]: every segment the recorder cuts at a pause is decoded at once on a
 * single worker thread, in order. When the user stops, [finish] decodes only the audio since the
 * last cut, so the wait after Stop is the tail of the take, not all of it.
 *
 * With [onText] set, each segment's text is handed over as soon as it is decoded ("type as you
 * go"), and [finish] returns only what has not been handed over yet. Without it, [finish] returns
 * the whole take. Callbacks run on the worker thread.
 */
class TakeDecoder(ctx: Context, private val onText: ((String) -> Unit)? = null) {
    private val app = ctx.applicationContext
    private val worker = Executors.newSingleThreadExecutor()
    private val held = StringBuilder()
    @Volatile private var cancelled = false
    @Volatile private var failure: Throwable? = null
    @Volatile var segmentsDecoded = 0
        private set
    /** Segments handed to [add] so far; a take with any is never "too short". */
    @Volatile var segmentsQueued = 0
        private set

    /** Queues one recorded segment. Called from the recorder's capture thread. */
    fun add(samples: FloatArray) {
        if (cancelled) return
        segmentsQueued++
        // runCatching: a cancel racing this call has already shut the worker down.
        runCatching { worker.execute {
            if (cancelled || failure != null) return@execute
            runCatching { Transcriber.transcribe(app, samples) }
                .onSuccess { text ->
                    segmentsDecoded++
                    if (text.isEmpty() || cancelled) return@onSuccess
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
        worker.execute {
            val result = runCatching {
                failure?.let { throw it }
                val last = if (tail.size >= minTail) Transcriber.transcribe(app, tail) else ""
                listOf(held.toString(), last).filter { it.isNotEmpty() }.joinToString(" ")
            }
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
