package app.hebrish.core

import android.content.Context
import android.os.SystemClock
import android.util.Log
import com.k2fsa.sherpa.onnx.FeatureConfig
import com.k2fsa.sherpa.onnx.OnlineModelConfig
import com.k2fsa.sherpa.onnx.OnlineRecognizer
import com.k2fsa.sherpa.onnx.OnlineRecognizerConfig
import com.k2fsa.sherpa.onnx.OnlineStream
import com.k2fsa.sherpa.onnx.OnlineTransducerModelConfig

/**
 * One loaded sherpa-onnx streaming transducer (`sherpa_online_transducer`). Two of them exist, so
 * neither reloads the other: [StreamingTranscriber] itself (the language model, the Hebrew line's
 * Zipformer2 66M) and [StreamingTranscriber.dictation] (a streaming dictation model the user picked:
 * Shakshuka, B-13, 2026-11-17).
 *
 * [transcribe] decodes one piece whole, as the desktop's `Engine._decode_piece` streaming branch
 * does: one stream, the (trimmed) audio, [StreamingTranscriber.PAD_SECONDS] of silence,
 * `inputFinished`, decode while ready, read the result. [open] starts a [Live] stream instead, fed
 * as the take is recorded (desktop `LiveStream`), for words as you speak.
 *
 * Freed with the same rules as the main model: [unloadIfIdle] from the services' memory and
 * screen-off hooks via [Transcriber], and on the same idle clock.
 */
open class OnlineSlot(private val label: String) {
    @Volatile private var recognizer: OnlineRecognizer? = null
    @Volatile private var loadedDir: String? = null
    @Volatile private var lastUse = 0L
    private val lock = Any()
    private val preloading = java.util.concurrent.atomic.AtomicBoolean(false)

    /** Something is in memory (for [Transcriber]'s free hooks). */
    val loaded: Boolean get() = recognizer != null

    fun isLoaded(ctx: Context, model: Catalogue.Model) =
        recognizer != null && loadedDir == ModelStore.dir(ctx, model = model)?.path

    fun unload() = synchronized(lock) {
        recognizer?.release()
        recognizer = null
        loadedDir = null
    }

    /** Frees the model if unused for [idleMs]; see [Transcriber.unloadIfIdle]. */
    fun unloadIfIdle(idleMs: Long, why: String): Boolean = synchronized(lock) {
        if (recognizer == null || SystemClock.elapsedRealtime() - lastUse < idleMs) return false
        unload()
        Log.i(Transcriber.TAG, "$label freed ($why)")
        true
    }

    /** Loads on a background thread if [model] is downloaded and not loaded yet. One at a time. */
    fun preload(ctx: Context, model: Catalogue.Model) {
        if (isLoaded(ctx, model) || !ModelStore.isReady(ctx, model = model)) return
        if (!preloading.compareAndSet(false, true)) return
        val app = ctx.applicationContext
        Thread { try { runCatching { load(app, model) } } finally { preloading.set(false) } }.start()
    }

    /** Blocking. Safe to call repeatedly; only the first call (per model folder) loads. */
    fun load(ctx: Context, model: Catalogue.Model): OnlineRecognizer {
        val dir = ModelStore.dir(ctx, model = model) ?: throw IllegalStateException("${model.name} is not downloaded")
        synchronized(lock) {
            recognizer?.takeIf { loadedDir == dir.path }?.let { lastUse = SystemClock.elapsedRealtime(); return it }
            recognizer?.release()
            recognizer = null
            val started = SystemClock.elapsedRealtime()
            val config = OnlineRecognizerConfig(
                featConfig = FeatureConfig(sampleRate = Transcriber.SAMPLE_RATE, featureDim = model.featureDim),
                modelConfig = OnlineModelConfig(
                    transducer = OnlineTransducerModelConfig(
                        encoder = java.io.File(dir, "encoder.int8.onnx").path,
                        decoder = java.io.File(dir, "decoder.int8.onnx").path,
                        joiner = java.io.File(dir, "joiner.int8.onnx").path,
                    ),
                    tokens = java.io.File(dir, "tokens.txt").path,
                    numThreads = Transcriber.threads,
                    // "zipformer2" for the Hebrew line; empty for Shakshuka, so sherpa-onnx reads the
                    // encoder metadata (the desktop loads it the same way; the 560 ms chunk is in there too).
                    modelType = model.modelType,
                ),
                // A piece is decoded whole, and a live take is one stream: an endpoint would only split what we read back.
                enableEndpoint = false,
                decodingMethod = "greedy_search",
            )
            val rec = OnlineRecognizer(assetManager = null, config = config)
            recognizer = rec
            loadedDir = dir.path
            lastUse = SystemClock.elapsedRealtime()
            Log.i(Transcriber.TAG, "$label loaded (${model.id}, ${dir.name}, ${SystemClock.elapsedRealtime() - started} ms)")
            return rec
        }
    }

    /** Blocking. [samples]: mono floats at 16 kHz. Returns the text, `<unk>` dropped and trimmed. */
    fun transcribe(ctx: Context, model: Catalogue.Model, samples: FloatArray): String {
        val speech = Transcriber.trim(samples)
        synchronized(lock) {
            val rec = load(ctx, model)
            val stream = rec.createStream()
            try {
                stream.acceptWaveform(speech, Transcriber.SAMPLE_RATE)
                stream.acceptWaveform(FloatArray((Transcriber.SAMPLE_RATE * StreamingTranscriber.PAD_SECONDS).toInt()), Transcriber.SAMPLE_RATE)
                stream.inputFinished()
                while (rec.isReady(stream)) rec.decode(stream)
                return Transcriber.dropUnk(rec.getResult(stream).text).trim()
            } finally {
                stream.release()
                lastUse = SystemClock.elapsedRealtime()
            }
        }
    }

    /** Blocking (loads [model] if needed). One stream for a whole take; see [Live]. */
    fun open(ctx: Context, model: Catalogue.Model): Live = synchronized(lock) {
        val rec = load(ctx, model)
        Live(rec, rec.createStream())
    }

    /**
     * One streaming take (B-13; desktop `LiveStream._decode`): audio goes in as it is recorded and
     * [accept] returns the whole result so far. Greedy decoding of a cache-aware streaming model
     * only appends (desktop, verified 2026-10-22), so the caller can release any prefix of it
     * ([StreamRelease]). Use from one thread. If the recognizer was freed or replaced since [open]
     * (a model update, a delete), [accept] throws instead of touching a released native object.
     */
    inner class Live internal constructor(private val rec: OnlineRecognizer, private val stream: OnlineStream) {
        private var closed = false

        /** [samples] (may be empty), then with [last] the tail pad and `inputFinished`. Returns the result so far. */
        fun accept(samples: FloatArray, last: Boolean): String = synchronized(lock) {
            check(!closed && recognizer === rec) { "$label was unloaded during the take" }
            if (samples.isNotEmpty()) stream.acceptWaveform(samples, Transcriber.SAMPLE_RATE)
            if (last) {
                stream.acceptWaveform(FloatArray((Transcriber.SAMPLE_RATE * StreamingTranscriber.PAD_SECONDS).toInt()), Transcriber.SAMPLE_RATE)
                stream.inputFinished()
            }
            while (rec.isReady(stream)) rec.decode(stream)
            lastUse = SystemClock.elapsedRealtime()
            Transcriber.dropUnk(rec.getResult(stream).text).trimStart()
        }

        fun close() = synchronized(lock) {
            if (!closed) stream.release()
            closed = true
        }
    }
}

/**
 * The language model's recognizer (2026-11-16): today the Hebrew line's Zipformer2 66M (80-dim
 * fbank, 16 kHz, `model_type` "zipformer2"). Separate from [Transcriber], which keeps the dictation
 * model, so switching between English and Hebrew takes doesn't reload either. [dictation] is the
 * second slot, for a streaming dictation model (Shakshuka, B-13), reached through [Transcriber].
 */
object StreamingTranscriber : OnlineSlot("language model") {
    /** Trailing silence for the last chunk (upstream's example and the desktop use ~1.5 s). */
    const val PAD_SECONDS = 1.5f
    const val ENGINE = "sherpa-onnx online transducer int8 greedy_search"

    /** The selected dictation model when it streams (Shakshuka); [Transcriber] delegates to it. */
    val dictation = OnlineSlot("streaming dictation model")
}
