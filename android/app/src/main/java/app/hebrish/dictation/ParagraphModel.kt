package app.hebrish.dictation

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.io.File
import java.nio.LongBuffer

// No android.* here either: android/scripts/check_paragraphs.sh compiles this file against the
// desktop ONNX Runtime jar (com.microsoft.onnxruntime:onnxruntime), whose Java API (ai.onnxruntime)
// is the one in the Android AAR the app already ships. Not in core/: Hebrish Keyboard compiles
// core without the ORT Java classes.

/**
 * The break classifier: `model_int8.onnx`, `vocab.txt` and the threshold, from one installed
 * version folder. The ORT session is created on first use and kept until [close]. Blocking;
 * call from a worker thread, one call at a time.
 */
class ParagraphModel(
    private val dir: File,
    val threshold: Double,
    private val threads: Int = 2,
    /** The app runs the int8 model; the check script also runs the fp32 `model.onnx` (the strict parity target). */
    private val modelFile: String = "model_int8.onnx",
) : AutoCloseable {
    private var session: OrtSession? = null
    private var tokenizer: WordPiece? = null

    private fun open(): Pair<OrtSession, WordPiece> {
        val tok = tokenizer ?: WordPiece.load(File(dir, "vocab.txt")).also { tokenizer = it }
        val s = session ?: OrtSession.SessionOptions().use { o ->
            o.setIntraOpNumThreads(threads)
            OrtEnvironment.getEnvironment().createSession(File(dir, modelFile).path, o)
        }.also { session = it }
        return s to tok
    }

    /** Word scores for [words] (shared/paragraphs.md steps 2–4). */
    fun probs(words: List<String>): DoubleArray {
        if (words.isEmpty()) return DoubleArray(0)
        val (s, tok) = open()
        val env = OrtEnvironment.getEnvironment()
        val pieces = words.map { tok.word(it) }
        return Paragraphs.probs(pieces) { ids ->
            val shape = longArrayOf(1, ids.size.toLong())
            OnnxTensor.createTensor(env, LongBuffer.wrap(ids), shape).use { input ->
                OnnxTensor.createTensor(env, LongBuffer.wrap(LongArray(ids.size) { 1L }), shape).use { mask ->
                    s.run(mapOf("input_ids" to input, "attention_mask" to mask)).use { r ->
                        val fb = (r.get(0) as OnnxTensor).floatBuffer
                        FloatArray(fb.remaining()).also { fb.get(it) }
                    }
                }
            }
        }
    }

    /**
     * [text] with paragraph breaks. Text with no words comes back unchanged without loading
     * anything; so does any result that is not the same words (it never should be).
     */
    fun apply(text: String): String {
        val words = Paragraphs.words(text)
        if (words.isEmpty()) return text
        val out = Paragraphs.join(words, probs(words), threshold)
        return if (Paragraphs.sameWords(out, text)) out else text
    }

    override fun close() {
        session?.close()
        session = null
        tokenizer = null
    }
}
