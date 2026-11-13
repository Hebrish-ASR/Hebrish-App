package app.hebrish.dictation

import android.content.Context
import android.os.Handler
import app.hebrish.core.Disfluency
import app.hebrish.core.OutputStyle
import app.hebrish.core.PersonalDictionary
import app.hebrish.core.Recorder
import app.hebrish.core.Transcriber
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Live draft for one voice keyboard take (I-4, D-2026-11-13-01): about every [INTERVAL_MS] the open
 * phrase (the [Recorder]'s audio since its last cut, [Recorder.openSegment]) is decoded again by the
 * same offline model, and [show] puts the result on screen as composing text, which replaces the
 * previous draft. The phrase is committed by the take's own [app.hebrish.core.TakeDecoder] when the
 * recorder cuts it at a pause (or at the phrase cap) and at Stop; this class never commits anything.
 *
 * - One pass at a time: a tick while the previous pass is still decoding is skipped, never queued.
 * - [canRun] (main thread) is asked at every tick; the keyboard says no while paused, while earlier
 *   takes are still landing, and while a cut phrase is still being decoded for real, so the real
 *   decode never waits behind a draft.
 * - The model is shared with the take's decoder; [Transcriber.transcribe] holds its lock, so the two
 *   never use the recognizer at once. A pass never loads the model: until the take's decoder has
 *   loaded it, there is no draft.
 * - [show] gets the phrase index ([Recorder.OpenSegment.cut]) with the text, on the main thread, so
 *   the keyboard can drop a draft that a cut has overtaken.
 *
 * Desktop has no twin yet. Not run on a device (2026-11-13): see android/docs/maintaining.md, "Live draft".
 */
class LiveDraft(
    ctx: Context,
    private val recorder: Recorder,
    private val main: Handler,
    private val canRun: () -> Boolean,
    private val show: (cut: Int, text: String) -> Unit,
) {
    private val app = ctx.applicationContext
    private val worker = Executors.newSingleThreadExecutor { r -> Thread(r, "live-draft").apply { isDaemon = true } }
    private val busy = AtomicBoolean(false)
    @Volatile private var stopped = false
    private val allCaps = OutputStyle.allCaps(app)
    /** As in TakeDecoder: read on the worker at the first pass, kept for the take. */
    private val dictionary by lazy { runCatching { PersonalDictionary.compile(PersonalDictionary.entries(app)) }.getOrDefault { it } }

    private val tick = object : Runnable {
        override fun run() {
            if (stopped) return
            if (canRun() && busy.compareAndSet(false, true)) {
                try {
                    worker.execute { pass() }
                } catch (_: java.util.concurrent.RejectedExecutionException) {
                    busy.set(false)
                }
            }
            main.postDelayed(this, INTERVAL_MS)
        }
    }

    fun start() {
        main.postDelayed(tick, INTERVAL_MS)
    }

    /** No more passes; a pass already decoding finishes, but its result is dropped. */
    fun stop() {
        stopped = true
        main.removeCallbacks(tick)
        worker.shutdown()
    }

    /** Worker thread. */
    private fun pass() {
        try {
            if (stopped || !Transcriber.isLoaded(app)) return
            val open = recorder.openSegment()
            val text = if (open.samples.size < Transcriber.SAMPLE_RATE * MIN_SECONDS || !Transcriber.hasSpeech(open.samples)) ""
                else draftText(OutputStyle.apply(dictionary(Disfluency.chop(Transcriber.transcribe(app, open.samples))), allCaps))
            if (!stopped) main.post { if (!stopped) show(open.cut, text) }
        } catch (_: Throwable) {
            // A failed draft pass is only a missing draft; the take's own decode reports real errors.
        } finally {
            busy.set(false)
        }
    }

    companion object {
        /** Time between passes (D-2026-11-13-01: 300 to 500 ms, to be confirmed by timing a pass on a phone). */
        const val INTERVAL_MS = 500L
        /**
         * Hard cut of the open phrase when nobody pauses (D-2026-11-13-01: about 15 to 20 s), given to
         * the Recorder as its segment cap, because every pass re-decodes the whole phrase.
         */
        const val PHRASE_CAP_SECONDS = 20f
        /** Less open audio than this gets no draft yet. */
        const val MIN_SECONDS = 0.5f

        /**
         * What the draft shows for a decoded phrase: the model's final punctuation (. ? !, after
         * trailing whitespace) is left out, because it is only decided when the phrase is committed.
         */
        fun draftText(text: String): String = text.trimEnd().trimEnd('.', '?', '!').trimEnd()
    }
}
