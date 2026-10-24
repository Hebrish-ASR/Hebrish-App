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
 * the whole take. Callbacks run on the worker thread. Text goes through the disfluency chop
 * ([Disfluency], always on), then the personal dictionary
 * ([PersonalDictionary]) and [OutputStyle], each read once per take, so a take never changes
 * style halfway.
 *
 * Seams (0.8.2, the desktop 0.7.6 fix; docs/maintaining.md, "Context at the seams"): each segment
 * after the first is decoded after the last [CONTEXT_SECONDS] of the one before it
 * ([Transcriber.transcribeAfter]), so Parakeet hears the sentence go on instead of treating every
 * segment as a whole utterance ("word. Capital", "word Capital"). A segment's closing "." is held
 * back until the next segment shows whether the sentence really ended ([afterHeldStop]). A piece
 * of text handed over can therefore start with ". " (the held stop, glued to the text before it):
 * callers put no separating space before text that starts with a mark ([join]).
 */
class TakeDecoder(ctx: Context, private val onText: ((String) -> Unit)? = null) {
    private val app = ctx.applicationContext
    private val worker = Executors.newSingleThreadExecutor()
    private val held = StringBuilder()
    private val allCaps = OutputStyle.allCaps(app)
    /**
     * The personal dictionary (0.9.0, [PersonalDictionary]), read on the worker at the take's
     * first piece and kept for the whole take. Applied before ALL CAPS, after the seam rules.
     */
    private val dictionary by lazy { runCatching { PersonalDictionary.compile(PersonalDictionary.entries(app)) }.getOrDefault { it } }
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
     * the sum of every decode call (trim + pad + sherpa-onnx decode, context included) and excludes
     * [loadSeconds], the model load a take paid when the model was not in memory yet.
     * [waitSeconds] is Stop to text: what the user actually waited. [contextSeconds] (0.8.2) is the
     * audio decoded a second time as context at the seams, before trimming.
     */
    data class Stats(
        val audioSeconds: Double,
        val decodeSeconds: Double,
        val loadSeconds: Double,
        val waitSeconds: Double,
        val segments: Int,
        val allCaps: Boolean,
        val typeAsYouGo: Boolean,
        val contextSeconds: Double = 0.0,
    )

    private val all = StringBuilder()
    @Volatile private var audioSamples = 0L
    @Volatile private var decodeMs = 0L
    @Volatile private var loadMs = 0L
    @Volatile private var waitMs = 0L
    @Volatile private var contextSamples = 0L

    // Seam state, worker thread only.
    /** The end of the previous segment, when it was cut in a pause; null otherwise. */
    private var context: FloatArray? = null
    /** The previous piece's closing "." was held back. */
    private var stopHeld = false

    /** The whole take's text, including parts already handed to [onText]. Valid once [finish] is done. */
    val text: String get() = synchronized(all) { all.toString() }

    /** Valid once [finish] has called back. */
    fun stats() = Stats(audioSamples / Transcriber.SAMPLE_RATE.toDouble(), decodeMs / 1000.0, loadMs / 1000.0,
        waitMs / 1000.0, segmentsDecoded, allCaps, onText != null, contextSamples / Transcriber.SAMPLE_RATE.toDouble())

    /** Worker thread only: loads the model if needed (timed apart), then decodes (timed). */
    private fun <T> timed(decode: () -> T): T {
        if (!Transcriber.isLoaded(app)) {
            val t = SystemClock.elapsedRealtime()
            Transcriber.load(app)
            loadMs += SystemClock.elapsedRealtime() - t
        }
        val t = SystemClock.elapsedRealtime()
        return decode().also { decodeMs += SystemClock.elapsedRealtime() - t }
    }

    /**
     * Worker thread only. Decodes one piece (with the previous segment's end as context when there
     * is usable context) and returns what to hand over, seam applied and styled; "" for nothing.
     */
    private fun piece(samples: FloatArray, last: Boolean): String {
        val ctx = context?.takeIf { it.size >= Transcriber.SAMPLE_RATE * MIN_CONTEXT_SECONDS && Transcriber.hasSpeech(it) }
        val (decoded, stop) = if (ctx != null) {
            contextSamples += ctx.size
            timed { Transcriber.transcribeAfter(app, samples, ctx) }
        } else timed { Transcriber.transcribe(app, samples) } to null
        // Context for the next piece only after a cut in a pause: a hard cut (28 s without one)
        // can land inside a word, which would then straddle the boundary.
        context = if (!last && (Transcriber.trailingQuietSeconds(samples) ?: 0f) >= PAUSE_CUT_SECONDS)
            samples.copyOfRange((samples.size - Transcriber.SAMPLE_RATE * CONTEXT_SECONDS).coerceAtLeast(0), samples.size)
        else null
        var text = Disfluency.chop(decoded)      // 1.001: fillers out first (../shared/disfluencies.md)
        var lead = ""
        if (text.isNotEmpty() && stopHeld) {
            val seam = afterHeldStop(text, stop)
            text = seam.trimStart('.', ' ')
            lead = if (seam.startsWith(".")) ". " else ""
            stopHeld = false
        } else if (stopHeld && last) {
            stopHeld = false
            return OutputStyle.apply(".", allCaps)
        }
        if (text.isEmpty()) return lead.trimEnd()
        if (!last && holdStop(text)) {
            text = text.dropLast(1)
            stopHeld = true
        }
        return OutputStyle.apply(lead + dictionary(text), allCaps)
    }

    private fun keep(text: String) = synchronized(all) { all.append(join(all, text)) }

    /** Queues one recorded segment. Called from the recorder's capture thread. */
    fun add(samples: FloatArray) {
        if (cancelled) return
        segmentsQueued++
        audioSamples += samples.size
        // runCatching: a cancel racing this call has already shut the worker down.
        runCatching { worker.execute {
            if (cancelled || failure != null) return@execute
            runCatching { piece(samples, last = false) }
                .onSuccess { text ->
                    segmentsDecoded++
                    if (text.isEmpty() || cancelled) return@onSuccess
                    keep(text)
                    if (onText != null) onText.invoke(text) else held.append(join(held, text))
                }
                .onFailure { failure = it }
        } }
    }

    /**
     * Decodes [tail] after every queued segment, then calls [done] with the text not yet handed
     * to [onText]. A tail under [minTail] samples is skipped (a tap on Stop right after a cut),
     * though a held full stop is still put back.
     */
    fun finish(tail: FloatArray, minTail: Int = Transcriber.SAMPLE_RATE / 4, done: (Result<String>) -> Unit) {
        val stopped = SystemClock.elapsedRealtime()
        audioSamples += tail.size
        worker.execute {
            val result = runCatching {
                failure?.let { throw it }
                val last = if (tail.size >= minTail) piece(tail, last = true)
                    else if (stopHeld) { stopHeld = false; OutputStyle.apply(".", allCaps) } else ""
                if (last.isNotEmpty()) keep(last)
                held.toString() + join(held, last)
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

    companion object {
        /** Audio of the previous segment decoded again as context (desktop engine.CONTEXT_S). */
        const val CONTEXT_SECONDS = 3
        /** Less context than this is no context (desktop MIN_TAKE_S). */
        const val MIN_CONTEXT_SECONDS = 0.3f
        /**
         * Quiet at a segment's end that marks a cut in a pause. Recorder cuts after 0.6 s below
         * its own threshold; trim's threshold differs, so this is set a little lower.
         */
        const val PAUSE_CUT_SECONDS = 0.4f

        /** Function words that continue a sentence (desktop engine.CONTINUES). */
        val CONTINUES = """and or but so because since which who whom whose that than then to of for
            with without in on at by from as if when while where whether after before until till unless
            about into onto like plus nor yet although though""".split(Regex("\\s+")).filter { it.isNotEmpty() }.toSet()

        /** Hold back a piece's closing full stop while more may follow (desktop engine.hold_stop). */
        fun holdStop(text: String) = text.endsWith(".") && !text.endsWith("..")

        /**
         * What follows a held-back full stop (desktop engine.after_held_stop): ". " + the text with a
         * capital when the model, hearing the end of the previous piece with this one, ended that
         * piece with a sentence mark; " " + the text in the model's case when it did not. [stop] null
         * (no usable context): lower-case first word or a word in [CONTINUES] continues the
         * sentence, anything else starts a new one.
         */
        fun afterHeldStop(text: String, stop: Boolean?): String {
            if (stop != null) return if (stop) ". " + text.take(1).uppercase() + text.drop(1) else " $text"
            val first = text.substringBefore(' ')
            if (first.take(1).let { it.isNotEmpty() && it[0].isLowerCase() }) return " $text"
            if (first.lowercase().trim(',', ';', ':') in CONTINUES && !(first.length > 1 && first[1].isUpperCase()))
                return " " + text.take(1).lowercase() + text.drop(1)
            return ". $text"
        }

        /**
         * [text] as it goes after [before]: a space between them, unless [before] is empty or ends
         * in whitespace, or [text] starts with a mark that attaches to the word before it (a held
         * full stop handed over as ". Next").
         */
        fun join(before: CharSequence, text: String): String =
            if (before.isEmpty() || before.last().isWhitespace() || text.isEmpty() || text[0] in ".,;:?!") text else " $text"
    }
}
