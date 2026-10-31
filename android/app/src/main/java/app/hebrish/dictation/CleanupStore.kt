package app.hebrish.dictation

import app.hebrish.core.Catalogue
import app.hebrish.core.ModelPrefs
import app.hebrish.core.ModelStore
import android.content.Context
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.io.File

/**
 * The clean-up models (B-40a): the catalogue's `addons` of kind `text_cleanup` that have an
 * `android` block (a smaller quantisation than desktop's). Two since 2026-10-30 (Daniel): stock
 * S1-mini by Superwhisper, the default, and S1-ASR-Cleanup, Daniel's fine-tune of it, marked
 * experimental until it is shown to beat stock. One is chosen ([chosen]); each downloads on demand
 * from Hugging Face at its pinned tag into app storage, `models/<id>/<version>/`, with the speech
 * models' resumable, SHA-256-checked loop ([ModelStore.downloadFiles]). A download is remembered
 * only once the file has verified; that model's older versions are then deleted. Not speech
 * models: never in the model picker. The runtime is built into the APK ([CleanupModel]).
 *
 * The title model (B-75a, kind `text_title`, [Titles]) uses the same path: [entries] with
 * [Titles.KIND], [title], [titleFile]. One download runs at a time, whichever kind.
 */
object CleanupStore {
    private const val HF = "https://huggingface.co"
    const val CLEANUP = "text_cleanup"

    /**
     * One catalogue add-on, its Android download. [name] follows the licence's naming term:
     * "S1-mini" by "Superwhisper", exact capitalisation.
     */
    data class Entry(val id: String, val name: String, val version: String, val repo: String, val revision: String,
                     val file: ModelStore.ModelFile, val ramMb: Int, val isDefault: Boolean, val experimental: Boolean,
                     val kind: String = CLEANUP) {
        val url get() = "$HF/$repo/resolve/$revision/${file.name}"
        val downloadMb get() = (file.size / 1_000_000).toInt()
    }

    data class Installed(val version: String, val file: ModelStore.ModelFile) {
        fun toJson(): String = JSONObject().put("version", version).put("file", file.name)
            .put("size", file.size).put("sha256", file.sha256 ?: JSONObject.NULL).toString()

        companion object {
            fun fromJson(s: String): Installed {
                val o = JSONObject(s)
                return Installed(o.getString("version"),
                    ModelStore.ModelFile(o.getString("file"), o.getLong("size"), if (o.isNull("sha256")) null else o.getString("sha256")))
            }
        }
    }

    sealed class Status {
        object Idle : Status()
        data class Running(val id: String, val done: Long, val total: Long) : Status()
        data class Done(val id: String) : Status()
        data class Failed(val message: String, val id: String = "") : Status()
    }

    private val main = Handler(Looper.getMainLooper())
    @Volatile var status: Status = Status.Idle
        private set
    @Volatile private var cancel = false
    /** Main thread. */
    var listener: ((Status) -> Unit)? = null

    /**
     * The Android add-ons of [kind] (clean-up by default) from the cached catalogue, else the
     * bundled one (a cached catalogue from before they had Android builds lists none); empty when
     * neither does. Decided per kind, so a cache with clean-up models but no Android title model
     * still finds the title model in the bundled copy.
     */
    fun entries(ctx: Context, kind: String = CLEANUP): List<Entry> {
        val app = ctx.applicationContext
        val cached = runCatching { ModelPrefs.catalogueJson(app)?.let { parse(it, kind) } }.getOrNull()
        if (!cached.isNullOrEmpty()) return cached
        return runCatching { parse(app.assets.open(Catalogue.ASSET).bufferedReader().use { it.readText() }, kind) }.getOrDefault(emptyList())
    }

    private fun parse(doc: String, kind: String): List<Entry> {
        val addons = JSONObject(doc).optJSONArray("addons") ?: return emptyList()
        val out = ArrayList<Entry>()
        for (i in 0 until addons.length()) {
            val a = addons.getJSONObject(i)
            if (a.optString("kind") != kind) continue
            val android = a.optJSONObject("android") ?: continue
            // An entry not yet published (placeholders, null size) is skipped, not the whole list.
            runCatching {
                val f = ModelStore.ModelFile(android.getString("file"), android.getLong("size"), android.getString("sha256"))
                // `android.revision`: a file added to the repo after the entry's tag is pinned by commit.
                Entry(a.getString("id"), a.optString("short_name", a.getString("name")), a.getString("version"),
                    a.getString("repo"), android.optString("revision", a.getString("revision")), f, android.optInt("ram_mb", 0),
                    a.optBoolean("default"), a.optBoolean("experimental"), kind)
            }.getOrNull()?.takeIf { e -> "TODO" !in listOf(e.version, e.repo, e.revision, e.file.name) }?.let(out::add)
        }
        return out
    }

    /** Offered on this phone: the catalogue has an Android build and the CPU can run it. */
    fun available(ctx: Context) = CleanupModel.supported() && entries(ctx).isNotEmpty()

    /** The user's choice if still offered, else the catalogue's default, else the first. */
    fun chosen(ctx: Context): Entry? {
        val all = entries(ctx)
        return all.firstOrNull { it.id == Prefs.cleanupChoice(ctx) } ?: all.firstOrNull { it.isDefault } ?: all.firstOrNull()
    }

    fun base(ctx: Context, id: String) = File(File(ctx.filesDir, "models"), id)

    fun installed(ctx: Context, id: String): Installed? =
        Prefs.cleanupModel(ctx, id)?.let { runCatching { Installed.fromJson(it) }.getOrNull() }

    fun file(ctx: Context, id: String, m: Installed) = File(File(base(ctx, id), m.version), m.file.name)

    fun isReady(ctx: Context, e: Entry): Boolean {
        val m = installed(ctx, e.id) ?: return false
        return file(ctx, e.id, m).let { it.exists() && it.length() == m.file.size }
    }

    /** The chosen model's file when it is downloaded, else null. */
    fun readyFile(ctx: Context): File? {
        val e = chosen(ctx) ?: return null
        val m = installed(ctx, e.id) ?: return null
        return file(ctx, e.id, m).takeIf { it.exists() && it.length() == m.file.size }
    }

    /** The title model (B-75a) when this phone can run it and the catalogue has an Android build, else null. */
    fun title(ctx: Context): Entry? = if (CleanupModel.supported()) entries(ctx, Titles.KIND).firstOrNull() else null

    /** The title model's file when it is downloaded, else null. */
    fun titleFile(ctx: Context): File? {
        val e = title(ctx) ?: return null
        val m = installed(ctx, e.id) ?: return null
        return file(ctx, e.id, m).takeIf { it.exists() && it.length() == m.file.size }
    }

    /** Downloads [e] unless it is installed or a download is running. */
    fun download(ctx: Context, e: Entry) {
        if (status is Status.Running) return
        val app = ctx.applicationContext
        if (isReady(app, e) && installed(app, e.id)?.version == e.version) return
        cancel = false
        publish(Status.Running(e.id, 0, e.file.size))
        Thread {
            try {
                var last = 0L
                ModelStore.downloadFiles(File(base(app, e.id), e.version), listOf(e.file), { e.url }, { cancel }) { done ->
                    if (done - last > 2_000_000 || done == e.file.size) {
                        last = done
                        publish(Status.Running(e.id, done, e.file.size))
                    }
                }
                Prefs.setCleanupModel(app, e.id, Installed(e.version, e.file).toJson())
                base(app, e.id).listFiles()?.filter { it.name != e.version }?.forEach { it.deleteRecursively() }
                publish(Status.Done(e.id))
            } catch (x: InterruptedException) {
                publish(Status.Idle)
            } catch (x: Exception) {
                publish(Status.Failed(x.message ?: x.javaClass.simpleName, e.id))
            }
        }.start()
    }

    fun cancel() { cancel = true }

    /** Deletes one model's files. */
    fun remove(ctx: Context, id: String) {
        Prefs.setCleanupModel(ctx, id, null)
        base(ctx, id).deleteRecursively()
        publish(Status.Idle)
    }

    private fun publish(s: Status) {
        status = s
        main.post { listener?.invoke(s) }
    }
}
