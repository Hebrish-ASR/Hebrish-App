package app.hebrish.core

import android.content.Context
import com.k2fsa.sherpa.onnx.FeatureConfig
import com.k2fsa.sherpa.onnx.OfflineModelConfig
import com.k2fsa.sherpa.onnx.OfflineRecognizer
import com.k2fsa.sherpa.onnx.OfflineRecognizerConfig
import com.k2fsa.sherpa.onnx.OfflineTransducerModelConfig

/**
 * One process-wide recognizer. Loading the 650 MB encoder takes a few seconds, so it is done
 * once and kept for as long as Android keeps the process alive.
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

    fun isLoaded(ctx: Context) = recognizer != null && loadedDir == ModelStore.dir(ctx)?.path

    /** Frees the loaded model, e.g. after it moved; the next transcription loads it again. */
    fun unload() = synchronized(lock) {
        recognizer?.release()
        recognizer = null
        loadedDir = null
    }

    /** Loads on a background thread if needed. Cheap to call often (e.g. on every field focus). */
    fun preload(ctx: Context) {
        if (isLoaded(ctx) || !ModelStore.isReady(ctx)) return
        val app = ctx.applicationContext
        Thread { runCatching { load(app) } }.start()
    }

    /** Blocking. Safe to call repeatedly; only the first call loads. */
    fun load(ctx: Context): OfflineRecognizer {
        val want = ModelStore.dir(ctx)?.path
        recognizer?.takeIf { loadedDir == want }?.let { return it }
        synchronized(lock) {
            recognizer?.takeIf { loadedDir == want }?.let { return it }
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
                    numThreads = Runtime.getRuntime().availableProcessors().coerceIn(2, 4),
                ),
                decodingMethod = "greedy_search",
            )
            val rec = OfflineRecognizer(assetManager = null, config = config)
            // Warm-up: the first decode allocates ONNX Runtime's buffers; do it now, not on the user's take.
            runCatching { decode(rec, FloatArray(SAMPLE_RATE / 2)) }
            recognizer = rec
            loadedDir = want
            return rec
        }
    }

    /** Blocking. [samples] are mono floats in [-1, 1] at [SAMPLE_RATE]. */
    fun transcribe(ctx: Context, samples: FloatArray): String {
        val rec = load(ctx)
        val speech = trim(samples)
        return decode(rec, speech + FloatArray((SAMPLE_RATE * PAD_SECONDS).toInt()))
    }

    private fun decode(rec: OfflineRecognizer, audio: FloatArray): String {
        val stream = rec.createStream()
        try {
            stream.acceptWaveform(audio, SAMPLE_RATE)
            rec.decode(stream)
            return rec.getResult(stream).text.trim()
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
        val frames = samples.size / frame
        if (frames < 10) return samples
        val rms = FloatArray(frames) { f ->
            var sum = 0.0
            for (i in f * frame until (f + 1) * frame) sum += samples[i].toDouble() * samples[i]
            kotlin.math.sqrt(sum / frame).toFloat()
        }
        val sorted = rms.sortedArray()
        val noise = sorted[frames / 10]
        val loud = sorted[frames * 95 / 100]
        if (loud < 0.01f || loud < noise * 3) return samples
        val threshold = maxOf(0.003f, noise + (loud - noise) * 0.1f)
        val first = rms.indexOfFirst { it > threshold }
        val last = rms.indexOfLast { it > threshold }
        val margin = (SAMPLE_RATE * MARGIN_SECONDS).toInt()
        val from = (first * frame - margin).coerceAtLeast(0)
        val to = ((last + 1) * frame + margin).coerceAtMost(samples.size)
        return if (from == 0 && to == samples.size) samples else samples.copyOfRange(from, to)
    }
}
