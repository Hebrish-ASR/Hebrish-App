package app.hebrish.core

import android.content.Context
import android.os.SystemClock
import android.util.Log
import com.k2fsa.sherpa.onnx.FeatureConfig
import com.k2fsa.sherpa.onnx.OfflineModelConfig
import com.k2fsa.sherpa.onnx.OfflineRecognizer
import com.k2fsa.sherpa.onnx.OfflineRecognizerConfig
import com.k2fsa.sherpa.onnx.OfflineTransducerModelConfig

/**
 * One process-wide recognizer. Loading the 650 MB encoder takes a few seconds, so it is loaded
 * ahead of a take ([preload] on field focus and on Start) and kept while it is in use. Since 1.010
 * it is freed after [IDLE_UNLOAD_MS] without use, and on memory pressure ([unloadIfIdle] from the
 * services' onTrimMemory): up to 1.009 it stayed resident (~700 MB of native heap) for as long as
 * the always-on accessibility service kept the process alive, and on a 12 GB Pixel 11 that pushed
 * lmkd into killing background apps (2026-10-31; android/docs/maintaining.md, "Model memory").
 *
 * Speed (docs/maintaining.md, "Inference speed"): the encoder's cost grows with the audio it is
 * given, so [transcribe] trims silence off both ends ([trim]) and pads only the tail the model
 * needs. [load] runs one tiny decode so the first real one doesn't pay ONNX Runtime's first-run
 * setup. Long takes are decoded segment by segment while they are recorded ([TakeDecoder]).
 */
object Transcriber {
    const val SAMPLE_RATE = 16000

    /**
     * Zeros appended after the (trimmed) audio. The model drops the end of audio that has under
     * ~0.6 s of trailing silence (measured on desktop, 2026-10-18; see shared/update-protocol.md),
     * and [trim] keeps [MARGIN_SECONDS] of real audio after the last speech as well.
     */
    const val PAD_SECONDS = 0.8f
    /** Audio kept on each side of the speech when trimming. */
    const val MARGIN_SECONDS = 0.35f

    @Volatile private var recognizer: OfflineRecognizer? = null
    /** Folder the loaded recognizer came from; a different selected model means reload. */
    @Volatile private var loadedDir: String? = null
    private val lock = Any()

    /** ONNX Runtime threads for the decode: the phone's cores, 2 to 4. Recorded per take in the history. */
    val threads: Int get() = Runtime.getRuntime().availableProcessors().coerceIn(2, 4)
    /** How the model is run, for the history export's `engine` column. */
    const val ENGINE = "sherpa-onnx nemo_transducer int8 greedy_search"

    /** Logcat tag for model load and free (1.011): `adb logcat -s HebrishModel`. */
    const val TAG = "HebrishModel"

    /** Free the model after this long without a load or decode (1.010). */
    const val IDLE_UNLOAD_MS = 5 * 60_000L

    @Volatile private var lastUse = 0L
    private val idleTimer = java.util.concurrent.Executors.newSingleThreadScheduledExecutor { r ->
        Thread(r, "transcriber-idle").apply { isDaemon = true }
    }
    @Volatile private var idleCheck: java.util.concurrent.ScheduledFuture<*>? = null

    /** Marks the model as used now and (re)arms the idle unload. */
    private fun touch() {
        lastUse = SystemClock.elapsedRealtime()
        idleCheck?.cancel(false)
        idleCheck = idleTimer.schedule({ unloadIfIdle(IDLE_UNLOAD_MS, "idle timer") }, IDLE_UNLOAD_MS, java.util.concurrent.TimeUnit.MILLISECONDS)
    }

    /**
     * The timer above counts on System.nanoTime, which stops while the phone sleeps, so on a dozing
     * phone it can run for hours past its 5 minutes (seen on 1.010, Pixel 11, 2026-10-31). These
     * two make the free independent of it (1.011):
     * - [checkIdle], from every accessibility event: frees the model if [IDLE_UNLOAD_MS] has passed
     *   on the elapsedRealtime clock (which counts sleep). Cheap when nothing is due.
     * - [onScreenOff], from the services' ACTION_SCREEN_OFF receivers: frees it unless a take is
     *   open (a decode still running finishes first: the free waits for its lock).
     */
    fun checkIdle() {
        if (recognizer != null && SystemClock.elapsedRealtime() - lastUse >= IDLE_UNLOAD_MS) freeInBackground(IDLE_UNLOAD_MS, "idle")
    }

    fun onScreenOff(takeOpen: Boolean) {
        if (!takeOpen && recognizer != null) freeInBackground(0L, "screen off")
    }

    private val freeing = java.util.concurrent.atomic.AtomicBoolean(false)

    /** Off the caller's thread (it may wait for a decode); one at a time. */
    private fun freeInBackground(idleMs: Long, why: String) {
        if (!freeing.compareAndSet(false, true)) return
        Thread { try { unloadIfIdle(idleMs, why) } finally { freeing.set(false) } }.start()
    }

    /**
     * Frees the model if it has not been used for [idleMs]. Waits for a decode in progress (it
     * holds [lock]). The next take loads it again. Returns whether it freed anything.
     */
    fun unloadIfIdle(idleMs: Long, why: String = "idle"): Boolean = synchronized(lock) {
        if (recognizer == null || SystemClock.elapsedRealtime() - lastUse < idleMs) return false
        unload()
        Log.i(TAG, "model freed ($why, unused ${(SystemClock.elapsedRealtime() - lastUse) / 1000} s)")
        true
    }

    /**
     * For a service's onTrimMemory (1.010). Android 14+ sends only UI_HIDDEN (20, which the IME
     * gets every time the keyboard hides, so it is ignored) and BACKGROUND (40) and up; older
     * versions also send RUNNING_LOW / RUNNING_CRITICAL (10, 15) to a running process. Frees the
     * model, off the main thread, unless a take is open or it was used in the last 30 s.
     */
    fun onTrimMemory(level: Int, takeOpen: Boolean) {
        val pressure = level in 10..15 || level >= 40
        if (pressure && !takeOpen && recognizer != null) freeInBackground(30_000L, "memory pressure, level $level")
    }

    fun isLoaded(ctx: Context) = recognizer != null && loadedDir == ModelStore.dir(ctx)?.path

    /** Frees the loaded model, e.g. after it moved; the next transcription loads it again. */
    fun unload() = synchronized(lock) {
        recognizer?.release()
        recognizer = null
        loadedDir = null
    }

    /** Loads on a background thread if needed. Cheap to call often (e.g. on every field focus). */
    fun preload(ctx: Context) {
        if (isLoaded(ctx)) { touch(); return }
        if (!ModelStore.isReady(ctx)) return
        // One at a time: it is called on every field focus, and up to 1.008 each call started a
        // thread that then queued on [lock] behind the load already running.
        if (!preloading.compareAndSet(false, true)) return
        val app = ctx.applicationContext
        Thread { try { runCatching { load(app) } } finally { preloading.set(false) } }.start()
    }
    private val preloading = java.util.concurrent.atomic.AtomicBoolean(false)

    /** Blocking. Safe to call repeatedly; only the first call loads. */
    fun load(ctx: Context): OfflineRecognizer {
        val want = ModelStore.dir(ctx)?.path
        recognizer?.takeIf { loadedDir == want }?.let { touch(); return it }
        synchronized(lock) {
            recognizer?.takeIf { loadedDir == want }?.let { touch(); return it }
            recognizer?.release()
            recognizer = null
            val app = ctx.applicationContext
            val config = OfflineRecognizerConfig(
                // From the catalogue (128 for the 0.6B models, 80 for Sabich-Parakeet-110M).
                // sherpa-onnx also reads it from the NeMo encoder metadata, which wins (desktop check, 2026-10-21).
                featConfig = FeatureConfig(sampleRate = SAMPLE_RATE, featureDim = Catalogue.selected(app).featureDim),
                modelConfig = OfflineModelConfig(
                    transducer = OfflineTransducerModelConfig(
                        encoder = ModelStore.file(app, "encoder.int8.onnx").path,
                        decoder = ModelStore.file(app, "decoder.int8.onnx").path,
                        joiner = ModelStore.file(app, "joiner.int8.onnx").path,
                    ),
                    tokens = ModelStore.file(app, "tokens.txt").path,
                    modelType = "nemo_transducer",
                    numThreads = threads,
                ),
                decodingMethod = "greedy_search",
            )
            val started = SystemClock.elapsedRealtime()
            val rec = OfflineRecognizer(assetManager = null, config = config)
            // Warm-up: the first decode allocates ONNX Runtime's buffers; do it now, not on the user's take.
            runCatching { decode(rec, FloatArray(SAMPLE_RATE / 2)) }
            recognizer = rec
            loadedDir = want
            touch()
            Log.i(TAG, "model loaded (${java.io.File(want ?: "").name}, ${SystemClock.elapsedRealtime() - started} ms)")
            return rec
        }
    }

    /**
     * Blocking. [samples] are mono floats in [-1, 1] at [SAMPLE_RATE]. Holds [lock] for the decode:
     * [load] of another model (a preload after the selection changed) or [unload] releases the
     * native recognizer, and up to 0.7.0 that could happen under a decode still using it.
     */
    fun transcribe(ctx: Context, samples: FloatArray): String {
        val speech = trim(samples)
        synchronized(lock) {
            return decode(load(ctx), speech + FloatArray((SAMPLE_RATE * PAD_SECONDS).toInt())).also { touch() }
        }
    }

    /**
     * Blocking. [samples] decoded after [context], the audio just before it (0.8.2, the desktop
     * 0.7.6 seam fix; docs/maintaining.md, "Context at the seams"). Both are trimmed apart, then
     * decoded once as [context, samples, pad]; only the tokens timed at or after the end of the
     * context are kept, so the model writes the first word in its mid-sentence case. Returns that
     * text and whether the model ended the context with a sentence mark (. ? !), or null when the
     * context gave it nothing to say (no tokens before the boundary).
     */
    fun transcribeAfter(ctx: Context, samples: FloatArray, context: FloatArray): Pair<String, Boolean?> {
        val before = trim(context)
        val speech = trim(samples)
        val at = before.size / SAMPLE_RATE.toFloat()
        val audio = FloatArray(before.size + speech.size + (SAMPLE_RATE * PAD_SECONDS).toInt())
        before.copyInto(audio)
        speech.copyInto(audio, before.size)
        val r = synchronized(lock) { result(load(ctx), audio).also { touch() } }
        val tokens = r.tokens
        val times = r.timestamps
        val k = seamSplit(tokens, times, at)
        // Tokens carry their own leading spaces (as on desktop): join, then trim.
        val heard = dropUnk(tokens.copyOfRange(0, k).joinToString("")).trim()
        val text = dropUnk(tokens.copyOfRange(k, tokens.size).joinToString("")).trim()
        return text to if (heard.isEmpty()) null else heard.last() in ".?!"
    }

    /**
     * Index of the first token of a piece decoded after context ([transcribeAfter]): the first token
     * timed at or after [at], moved back to the start of its word. Timestamps are encoder frames
     * (80 ms), so the first pieces of the piece's first word can be timed just before [at]; split
     * there, they went with the context and the word came out clipped ("ividual", "chnically":
     * Android export 2026-10-27, desktop/docs/maintaining.md "Clipped words at the seams"). No
     * context word reaches [at] (cuts are in a pause), so a token without a leading space at the
     * split continues the piece's first word. Desktop twin: `engine.seam_split`.
     */
    fun seamSplit(tokens: Array<String>, times: FloatArray, at: Float): Int {
        var k = tokens.size
        for (i in tokens.indices) if (i < times.size && times[i] >= at) { k = i; break }
        while (k in 1 until tokens.size && tokens[k].firstOrNull().let { it != null && (it.isLetterOrDigit() || it == '\'' || it == '’') }) k--
        return k
    }

    /**
     * True when [samples] hold clear speech by [trim]'s measure (a 20 ms frame well above the
     * background); the Android counterpart of the desktop's `has_speech`.
     */
    fun hasSpeech(samples: FloatArray): Boolean = speechFrames(samples) != null

    /** Seconds of quiet after the last speech frame, or null without clear speech. */
    fun trailingQuietSeconds(samples: FloatArray): Float? =
        speechFrames(samples)?.let { (samples.size - (it.last + 1) * (SAMPLE_RATE / 50)) / SAMPLE_RATE.toFloat() }

    private fun decode(rec: OfflineRecognizer, audio: FloatArray): String = dropUnk(result(rec, audio).text).trim()

    private val UNK = Regex(" *<unk> *")

    /**
     * The model's text without `<unk>` (token 0 of the BPE vocabulary), which it writes at a clause
     * break where its training text had a mark the vocabulary lacks (em/en dash, semicolon, double
     * quote). A space takes its place. Desktop twin: `engine.drop_unk` (2026-10-25).
     */
    fun dropUnk(text: String): String = if ("<unk>" in text) text.replace(UNK, " ") else text

    private fun result(rec: OfflineRecognizer, audio: FloatArray): com.k2fsa.sherpa.onnx.OfflineRecognizerResult {
        val stream = rec.createStream()
        try {
            stream.acceptWaveform(audio, SAMPLE_RATE)
            rec.decode(stream)
            return rec.getResult(stream)
        } finally {
            stream.release()
        }
    }

    /**
     * Drops the silence before the first and after the last speech, keeping [MARGIN_SECONDS] on
     * each side. A take usually starts with the pause before you speak and ends with the reach
     * for Stop: often a second or two the encoder would otherwise process. Speech is a 20 ms frame
     * well above the take's own background level; audio with no clear speech is returned whole.
     */
    fun trim(samples: FloatArray): FloatArray {
        val frame = SAMPLE_RATE / 50
        val speech = speechFrames(samples) ?: return samples
        val margin = (SAMPLE_RATE * MARGIN_SECONDS).toInt()
        val from = (speech.first * frame - margin).coerceAtLeast(0)
        val to = ((speech.last + 1) * frame + margin).coerceAtMost(samples.size)
        return if (from == 0 && to == samples.size) samples else samples.copyOfRange(from, to)
    }

    /** First and last 20 ms frame of clear speech, or null (too short, or no clear speech). */
    private fun speechFrames(samples: FloatArray): IntRange? {
        val frame = SAMPLE_RATE / 50
        val frames = samples.size / frame
        if (frames < 10) return null
        val rms = FloatArray(frames) { f ->
            var sum = 0.0
            for (i in f * frame until (f + 1) * frame) sum += samples[i].toDouble() * samples[i]
            kotlin.math.sqrt(sum / frame).toFloat()
        }
        val sorted = rms.sortedArray()
        val noise = sorted[frames / 10]
        val loud = sorted[frames * 95 / 100]
        if (loud < 0.01f || loud < noise * 3) return null
        val threshold = maxOf(0.003f, noise + (loud - noise) * 0.1f)
        return rms.indexOfFirst { it > threshold }..rms.indexOfLast { it > threshold }
    }
}
