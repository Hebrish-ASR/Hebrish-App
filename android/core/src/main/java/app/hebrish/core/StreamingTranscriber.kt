package app.hebrish.core

import android.content.Context
import android.os.SystemClock
import android.util.Log
import com.k2fsa.sherpa.onnx.FeatureConfig
import com.k2fsa.sherpa.onnx.OnlineModelConfig
import com.k2fsa.sherpa.onnx.OnlineRecognizer
import com.k2fsa.sherpa.onnx.OnlineRecognizerConfig
import com.k2fsa.sherpa.onnx.OnlineTransducerModelConfig

/**
 * The language model's recognizer (2026-11-16): a sherpa-onnx streaming transducer
 * (`sherpa_online_transducer`), today only the Hebrew line's Zipformer2 66M (80-dim fbank, 16 kHz,
 * `model_type` "zipformer2"). Separate from [Transcriber], which keeps the dictation model, so
 * switching between English and Hebrew takes doesn't reload either.
 *
 * Each piece the take's [TakeDecoder] hands over is decoded whole, as the desktop's
 * `Engine._decode_piece` streaming branch does: one stream, the (trimmed) audio, [PAD_SECONDS] of
 * silence, `inputFinished`, decode while ready, read the result. No live partials yet.
 *
 * Small (72 MB), so it is freed with the same rules as the main model: [unloadIfIdle] from the
 * services' memory and screen-off hooks via [Transcriber], and on the same idle clock.
 */
object StreamingTranscriber {
    /** Trailing silence for the last chunk (upstream's example and the desktop use ~1.5 s). */
    const val PAD_SECONDS = 1.5f
    const val ENGINE = "sherpa-onnx online transducer int8 greedy_search"

    @Volatile private var recognizer: OnlineRecognizer? = null
    @Volatile private var loadedDir: String? = null
    @Volatile private var lastUse = 0L
    private val lock = Any()

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
        Log.i(Transcriber.TAG, "language model freed ($why)")
        true
    }

    /** Loads on a background thread if [model] is downloaded and not loaded yet. */
    fun preload(ctx: Context, model: Catalogue.Model) {
        if (isLoaded(ctx, model) || !ModelStore.isReady(ctx, model = model)) return
        val app = ctx.applicationContext
        Thread { runCatching { load(app, model) } }.start()
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
                    modelType = model.modelType,
                ),
                // A piece is decoded whole: an endpoint mid-piece would only split what we read back.
                enableEndpoint = false,
                decodingMethod = "greedy_search",
            )
            val rec = OnlineRecognizer(assetManager = null, config = config)
            recognizer = rec
            loadedDir = dir.path
            lastUse = SystemClock.elapsedRealtime()
            Log.i(Transcriber.TAG, "language model loaded (${model.id}, ${dir.name}, ${SystemClock.elapsedRealtime() - started} ms)")
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
                stream.acceptWaveform(FloatArray((Transcriber.SAMPLE_RATE * PAD_SECONDS).toInt()), Transcriber.SAMPLE_RATE)
                stream.inputFinished()
                while (rec.isReady(stream)) rec.decode(stream)
                return Transcriber.dropUnk(rec.getResult(stream).text).trim()
            } finally {
                stream.release()
                lastUse = SystemClock.elapsedRealtime()
            }
        }
    }
}
