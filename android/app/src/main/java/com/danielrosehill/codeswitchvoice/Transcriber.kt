package com.danielrosehill.codeswitchvoice

import android.content.Context
import com.k2fsa.sherpa.onnx.FeatureConfig
import com.k2fsa.sherpa.onnx.OfflineModelConfig
import com.k2fsa.sherpa.onnx.OfflineRecognizer
import com.k2fsa.sherpa.onnx.OfflineRecognizerConfig
import com.k2fsa.sherpa.onnx.OfflineTransducerModelConfig

/**
 * One process-wide recognizer. Loading the 650 MB encoder takes a few seconds, so it is done
 * once and kept for as long as Android keeps the process alive.
 */
object Transcriber {
    const val SAMPLE_RATE = 16000

    @Volatile private var recognizer: OfflineRecognizer? = null
    private val lock = Any()

    fun isLoaded() = recognizer != null

    /** Frees the loaded model, e.g. after it moved; the next transcription loads it again. */
    fun unload() = synchronized(lock) {
        recognizer?.release()
        recognizer = null
    }

    /** Blocking. Safe to call repeatedly; only the first call loads. */
    fun load(ctx: Context): OfflineRecognizer {
        recognizer?.let { return it }
        synchronized(lock) {
            recognizer?.let { return it }
            val app = ctx.applicationContext
            val config = OfflineRecognizerConfig(
                // sherpa-onnx reads the NeMo feature settings (128 mels) from the model metadata.
                featConfig = FeatureConfig(sampleRate = SAMPLE_RATE, featureDim = 80),
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
            return OfflineRecognizer(assetManager = null, config = config).also { recognizer = it }
        }
    }

    /** Blocking. [samples] are mono floats in [-1, 1] at [SAMPLE_RATE]. */
    fun transcribe(ctx: Context, samples: FloatArray): String {
        val rec = load(ctx)
        val stream = rec.createStream()
        try {
            stream.acceptWaveform(samples, SAMPLE_RATE)
            rec.decode(stream)
            return rec.getResult(stream).text.trim()
        } finally {
            stream.release()
        }
    }
}
