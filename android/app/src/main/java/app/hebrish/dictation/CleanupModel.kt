package app.hebrish.dictation

import android.os.Build
import java.io.File

/**
 * The clean-up model in-process (B-40a): libhebrish-llama-jni.so (llama.cpp b11982, built from
 * the submodule; src/main/cpp/s1_cleanup_jni.cpp) with one GGUF loaded and a [Cleanup.CTX]
 * context. Loading maps the file and takes a few seconds; the model is kept until [close]. Blocking;
 * call from a worker thread, one call at a time.
 */
class CleanupModel(gguf: File, threads: Int) : Cleanup.Client, AutoCloseable {
    private var handle: Long

    init {
        System.loadLibrary("hebrish-llama-jni")
        handle = nativeLoad(gguf.path, Cleanup.CTX, threads)
    }

    override fun count(text: String): Int = nativeCount(live(), text.toByteArray())

    override fun complete(prompt: String, nPredict: Int, timeoutMs: Long): Pair<String, Boolean> {
        val limit = BooleanArray(1)
        val out = nativeComplete(live(), prompt.toByteArray(), nPredict, timeoutMs, limit)
        return String(out, Charsets.UTF_8) to limit[0]
    }

    private fun live(): Long = handle.takeIf { it != 0L } ?: throw IllegalStateException("clean-up model closed")

    override fun close() {
        val h = handle
        handle = 0
        if (h != 0L) nativeFree(h)
    }

    companion object {
        /**
         * Whether this phone can run it: 64-bit ARM with the dot-product instructions the library is
         * built for (armv8.2-a+dotprod; Cortex-A55/A75 and later). Older cores would crash on load.
         */
        fun supported(): Boolean = SUPPORTED

        private val SUPPORTED by lazy {
            if ("arm64-v8a" !in Build.SUPPORTED_ABIS) return@lazy false
            val flags = runCatching { File("/proc/cpuinfo").readLines() }.getOrDefault(emptyList())
                .filter { it.startsWith("Features") }
            flags.isNotEmpty() && flags.all { line -> "asimddp" in line.substringAfter(':').trim().split(Regex("\\s+")) }
        }

        @JvmStatic private external fun nativeLoad(path: String, nCtx: Int, threads: Int): Long
        @JvmStatic private external fun nativeCount(handle: Long, text: ByteArray): Int
        @JvmStatic private external fun nativeComplete(handle: Long, prompt: ByteArray, nPredict: Int, timeoutMs: Long, limit: BooleanArray): ByteArray
        @JvmStatic private external fun nativeFree(handle: Long)
    }
}
