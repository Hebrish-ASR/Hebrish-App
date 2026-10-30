package app.hebrish.dictation

import app.hebrish.core.ModelStore
import android.content.Context
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * Transcription Mode's Paragraphs setting (B-44a, D-2026-10-24-09; spec `shared/paragraphs.md`,
 * "Where it runs"): None, Time-based or Paragraph model. One setting, remembered.
 */
enum class ParagraphMode(val key: String) {
    NONE("none"), TIME("time"), MODEL("model");

    companion object {
        /**
         * The chosen mode; with nothing chosen yet, Paragraph model when its files are installed,
         * else Time-based (the spec's default).
         */
        fun get(ctx: Context): ParagraphMode =
            values().firstOrNull { it.key == Prefs.tmParagraphs(ctx) }
                ?: if (ParagraphStore.isReady(ctx)) MODEL else TIME
    }
}

/**
 * The paragraph-break model's files (`model_int8.onnx`, `vocab.txt`, `config.json`): downloaded
 * on demand from the CDN manifest into app storage, `models/paragraph-breaks/<version>/`, with the
 * speech models' resumable, SHA-256-checked loop ([ModelStore.downloadFiles]). The installed
 * manifest is remembered only once every file has verified; older version folders are then
 * deleted. Not a speech model: it is in no catalogue and never in the model picker.
 */
object ParagraphStore {
    const val MANIFEST_URL = "https://cdn.hebrish.app/models/paragraph-breaks/latest.json"
    val FILES = listOf("model_int8.onnx", "vocab.txt", "config.json")
    /** The spec's threshold, used only if neither the manifest nor config.json gives one. */
    private const val DEFAULT_THRESHOLD = 0.26

    data class Installed(val version: String, val threshold: Double, val files: List<ModelStore.ModelFile>, val baseUrl: String) {
        val totalBytes get() = files.sumOf { it.size }
        fun toJson(): String = JSONObject().apply {
            put("version", version)
            put("threshold", threshold)
            put("base_url", baseUrl)
            put("files", JSONObject().apply {
                for (f in files) put(f.name, JSONObject().put("size", f.size).put("sha256", f.sha256 ?: JSONObject.NULL))
            })
        }.toString()

        companion object {
            /** A CDN manifest (`latest.json`, shared/update-protocol.md shape plus `threshold`) or a stored one. */
            fun fromJson(s: String): Installed {
                val o = JSONObject(s)
                val fs = o.getJSONObject("files")
                val files = FILES.map { name ->
                    val f = fs.optJSONObject(name) ?: throw java.io.IOException("$name missing from the paragraph model manifest")
                    ModelStore.ModelFile(name, f.getLong("size"), if (f.isNull("sha256")) null else f.getString("sha256"))
                }
                val base = o.getString("base_url").let { if (it.endsWith("/")) it else "$it/" }
                return Installed(o.getString("version"), o.optDouble("threshold", Double.NaN), files, base)
            }
        }
    }

    sealed class Status {
        object Idle : Status()
        data class Running(val done: Long, val total: Long) : Status()
        object Done : Status()
        data class Failed(val message: String) : Status()
    }

    private val main = Handler(Looper.getMainLooper())
    @Volatile var status: Status = Status.Idle
        private set
    @Volatile private var cancel = false
    /** Main thread. */
    var listener: ((Status) -> Unit)? = null

    fun base(ctx: Context) = File(File(ctx.filesDir, "models"), "paragraph-breaks")

    fun installed(ctx: Context): Installed? =
        Prefs.paragraphModel(ctx)?.let { runCatching { Installed.fromJson(it) }.getOrNull() }

    fun dir(ctx: Context, m: Installed) = File(base(ctx), m.version)

    fun isReady(ctx: Context): Boolean {
        val m = installed(ctx) ?: return false
        val d = dir(ctx, m)
        return m.files.all { File(d, it.name).let { f -> f.exists() && f.length() == it.size } }
    }

    /** The threshold: the manifest's, else `paragraph_threshold` in config.json, else the spec's 0.26. */
    fun threshold(ctx: Context, m: Installed): Double =
        m.threshold.takeIf { !it.isNaN() }
            ?: runCatching { JSONObject(File(dir(ctx, m), "config.json").readText()).getDouble("paragraph_threshold") }.getOrNull()
            ?: DEFAULT_THRESHOLD

    /** Downloads the newest version unless one is installed or a download is running. */
    fun download(ctx: Context) {
        if (status is Status.Running || isReady(ctx)) return
        val app = ctx.applicationContext
        cancel = false
        publish(Status.Running(0, 0))
        Thread {
            try {
                val m = Installed.fromJson(get(MANIFEST_URL))
                var last = 0L
                ModelStore.downloadFiles(dir(app, m), m.files, { m.baseUrl + it }, { cancel }) { done ->
                    if (done - last > 500_000 || done == m.totalBytes) {
                        last = done
                        publish(Status.Running(done, m.totalBytes))
                    }
                }
                // Every file verified: switch over, then drop any other version.
                Prefs.setParagraphModel(app, m.toJson())
                base(app).listFiles()?.filter { it.name != m.version }?.forEach { it.deleteRecursively() }
                publish(Status.Done)
            } catch (e: InterruptedException) {
                publish(Status.Idle)
            } catch (e: Exception) {
                publish(Status.Failed(e.message ?: e.javaClass.simpleName))
            }
        }.start()
    }

    fun cancel() { cancel = true }

    /** Deletes the model's files (the Paragraphs setting then falls back to time-based). */
    fun remove(ctx: Context) {
        Prefs.setParagraphModel(ctx, null)
        base(ctx).deleteRecursively()
        publish(Status.Idle)
    }

    private fun get(url: String): String {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 15_000
        conn.readTimeout = 15_000
        try {
            if (conn.responseCode != HttpURLConnection.HTTP_OK) throw java.io.IOException("HTTP ${conn.responseCode} for $url")
            return conn.inputStream.bufferedReader().use { it.readText() }
        } finally {
            conn.disconnect()
        }
    }

    private fun publish(s: Status) {
        status = s
        main.post { listener?.invoke(s) }
    }
}
