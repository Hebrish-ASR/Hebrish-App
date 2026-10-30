package app.hebrish.core

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * The models of [Catalogue], each a sherpa-onnx int8 transducer. Each installed model is a
 * [Manifest]: one HF commit plus the size and SHA-256 of every file at it, so a later push to a
 * model repo never changes what is already on the phone. [BUNDLED] holds the manifests this APK
 * knows offline; [checkLatest] builds one for whatever a model repo's `main` holds now.
 *
 * Every function takes the model it acts on and defaults to [Catalogue.selected].
 */
object ModelStore {
    /** Optional label file written next to the weights by a training repo's export_sherpa. */
    const val VERSION_FILE = "version.json"

    data class ModelFile(val name: String, val size: Long, val sha256: String?)

    /** [baseUrl]: CDN folder the files download from (ends in '/'); null = Hugging Face `resolve`. */
    data class Manifest(val version: String, val revision: String, val files: List<ModelFile>, val baseUrl: String? = null) {
        val totalBytes: Long get() = files.sumOf { it.size }
        val dirName: String get() = "$version-${revision.take(12)}"

        /**
         * What the UI shows: just the version, "v2.0". A CDN manifest's version may repeat the
         * model name ("Sabich v2.0"), and a "rev abc1234" fallback (no version.json) shows
         * nothing: no commits in the UI (Daniel, 2026-10-22).
         */
        val label: String get() = version.substringAfterLast(' ').takeUnless { version.startsWith("rev ") } ?: ""

        /**
         * Same weights, whatever the commit. Model-card and eval commits move `main` without
         * touching the files, so comparing revisions would offer a pointless 660 MB update.
         */
        fun sameWeights(other: Manifest) =
            files.map { it.name to (it.sha256 ?: it.size.toString()) }.toSet() ==
                other.files.map { it.name to (it.sha256 ?: it.size.toString()) }.toSet()

        fun toJson(): String = JSONObject().apply {
            put("version", version)
            put("revision", revision)
            if (baseUrl != null) put("base_url", baseUrl)
            put("files", JSONArray(files.map { f ->
                JSONObject().put("name", f.name).put("size", f.size).put("sha256", f.sha256 ?: JSONObject.NULL)
            }))
        }.toString()

        companion object {
            fun fromJson(s: String): Manifest {
                val o = JSONObject(s)
                val arr = o.getJSONArray("files")
                val files = (0 until arr.length()).map { i ->
                    val f = arr.getJSONObject(i)
                    ModelFile(f.getString("name"), f.getLong("size"), if (f.isNull("sha256")) null else f.getString("sha256"))
                }
                return Manifest(o.getString("version"), o.getString("revision"), files,
                    o.optString("base_url").ifEmpty { null })
            }
        }
    }

    /**
     * What this APK can download without asking HF first, per model id. Sizes and SHA-256 are the
     * HF tree API's `size` and `lfs.oid` at that revision. Small files are stored in git, not
     * LFS, so HF gives no hash for tokens.txt; its size is checked. A model missing here (one
     * added to the catalogue later) is resolved with [checkLatest] before its first download.
     */
    val BUNDLED: Map<String, Manifest> = mapOf(
        // csukuangfj's export of NVIDIA's release; it has no version.json, hence the fixed label.
        "stock" to Manifest(
            "v2", "1ab9323565ddb038682214b292f588070a538ce2", listOf(
                ModelFile("encoder.int8.onnx", 652184296, "a32b12d17bbbc309d0686fbbcc2987b5e9b8333a7da83fa6b089f0a2acd651ab"),
                ModelFile("decoder.int8.onnx", 7257753, "b6bb64963457237b900e496ee9994b59294526439fbcc1fecf705b31a15c6b4e"),
                ModelFile("joiner.int8.onnx", 1739080, "7946164367946e7f9f29a122407c3252b680dbae9a51343eb2488d057c3c43d2"),
                ModelFile("tokens.txt", 9384, null),
            )
        ),
        // v1.0, run r6-en30, on the Hebrish CDN (same files as Hebrish/...-sherpa-onnx-int8 at
        // commit bb137e50, whose sha is kept as the revision so existing installs match).
        "codeswitch" to Manifest(
            "v1.0", "bb137e504b9733fc582e03936477fe190dd4a464", listOf(
                ModelFile("encoder.int8.onnx", 652282307, "aff69ffe1187d1c52a1c98ec2a4674a5cd9a1ea42af26c7576f4fbde0f877bb5"),
                ModelFile("decoder.int8.onnx", 7257753, "682b2b4b99c4391fcb067199e5a39094cf69b83d3a3c26a6f6ac9f837148ec3c"),
                ModelFile("joiner.int8.onnx", 1739080, "2afe3966a97ad97488b1e6a1ee32e73b1008e8adedfae10adae4a9c9fad1074a"),
                ModelFile("tokens.txt", 9384, null),
            ),
            "https://cdn.hebrish.app/models/parakeet-codeswitch/v1.0/sherpa-onnx-int8/"
        ),
    )

    private fun sel(ctx: Context) = Catalogue.selected(ctx)

    /** The model's last fully downloaded manifest, else its [BUNDLED] one; null if neither exists. */
    fun installed(ctx: Context, model: Catalogue.Model = sel(ctx)): Manifest? =
        ModelPrefs.installedManifest(ctx, model.id)?.let(Manifest::fromJson) ?: BUNDLED[model.id]

    /** `a/b/c` from the non-empty parts: the stock model's files sit at the repo root (empty subdir). */
    private fun path(vararg parts: String) = parts.filter { it.isNotEmpty() }.joinToString("/")

    fun url(model: Catalogue.Model, m: Manifest, name: String) =
        m.baseUrl?.let { it + name }
            ?: ("https://huggingface.co/" + path(model.repo!!, "resolve", m.revision, model.subdir, name))

    /** Folder name inside a user-chosen location, so other apps can recognise what it holds. */
    fun sharedFolder(model: Catalogue.Model) = model.repo?.substringAfterLast('/') ?: model.id

    /**
     * The folder that holds one subfolder per version of [model]. App-private by default; under a
     * user-chosen folder (ModelPrefs.modelRoot) it gets its own subfolder, because pruneOld deletes
     * everything else in it.
     */
    fun base(ctx: Context, root: String? = ModelPrefs.modelRoot(ctx), model: Catalogue.Model = sel(ctx)) =
        if (root == null) File(File(ctx.filesDir, "models"), model.id) else File(root, sharedFolder(model))

    fun dir(ctx: Context, root: String? = ModelPrefs.modelRoot(ctx), model: Catalogue.Model = sel(ctx),
            m: Manifest? = installed(ctx, model)): File? =
        m?.let { File(base(ctx, root, model), it.dirName) }

    /** A file of the selected model; only meaningful once [isReady]. */
    fun file(ctx: Context, name: String) = File(dir(ctx) ?: throw IllegalStateException("no model"), name)

    fun isReady(ctx: Context, root: String? = ModelPrefs.modelRoot(ctx), model: Catalogue.Model = sel(ctx),
                m: Manifest? = installed(ctx, model)): Boolean {
        val d = dir(ctx, root, model, m) ?: return false
        return m!!.files.all { File(d, it.name).let { f -> f.exists() && f.length() == it.size } }
    }

    /** Deletes every folder of [model] except its installed version: older versions and abandoned updates. */
    fun pruneOld(ctx: Context, model: Catalogue.Model = sel(ctx)) {
        val keep = dir(ctx, model = model)?.name
        base(ctx, model = model).listFiles()?.filter { it.name != keep }?.forEach { it.deleteRecursively() }
    }

    /**
     * Deletes [model]'s downloaded files and forgets its manifest. In a shared folder the files
     * may be another app's too, so only the version this app installed is removed there.
     */
    fun delete(ctx: Context, model: Catalogue.Model) {
        if (ModelPrefs.modelRoot(ctx) == null) base(ctx, null, model).deleteRecursively()
        else dir(ctx, model = model)?.deleteRecursively()
        ModelPrefs.setInstalledManifest(ctx, model.id, null)
    }

    /**
     * Asks HF what [model]'s `main` holds now. Blocking; call from a worker thread. The manifest is
     * pinned to the commit `main` pointed at during the check, so a push mid-download cannot mix
     * files from two versions. The label comes from [VERSION_FILE]; without one it is the
     * catalogue's `version_label` (the stock export has no version.json), else the short commit.
     */
    fun checkLatest(ctx: Context, model: Catalogue.Model = sel(ctx)): Manifest {
        val names = Catalogue.get(ctx).files
        model.manifestUrl?.let { return fromCdn(it, names) }
        val repo = model.repo ?: throw java.io.IOException("${model.name} is not published yet")
        val sha = JSONObject(get("https://huggingface.co/api/models/$repo/revision/main")).getString("sha")
        val tree = JSONArray(get("https://huggingface.co/" + path("api/models", repo, "tree", sha, model.subdir)))
        val byName = (0 until tree.length()).map { tree.getJSONObject(it) }.associateBy { it.getString("path").substringAfterLast('/') }
        val files = names.map { name ->
            val e = byName[name] ?: throw java.io.IOException("$name missing from $repo/${model.subdir} at ${sha.take(12)}")
            ModelFile(name, e.getLong("size"), e.optJSONObject("lfs")?.getString("oid"))
        }
        val labelled = runCatching {
            JSONObject(get("https://huggingface.co/" + path(repo, "resolve", sha, model.subdir, Catalogue.get(ctx).versionFile)))
                .getString("version")
        }.getOrNull()
        val version = labelled ?: model.versionLabel ?: "rev ${sha.take(7)}"
        return Manifest(version, sha, files)
    }

    /** One GET of the CDN manifest: {"version", "revision", "base_url", "files": {name: {size, sha256}}}. */
    private fun fromCdn(manifestUrl: String, names: List<String>): Manifest {
        val o = JSONObject(get(manifestUrl))
        val fs = o.getJSONObject("files")
        val files = names.map { name ->
            val f = fs.optJSONObject(name) ?: throw java.io.IOException("$name missing from $manifestUrl")
            ModelFile(name, f.getLong("size"), if (f.isNull("sha256")) null else f.getString("sha256"))
        }
        val base = o.getString("base_url").let { if (it.endsWith("/")) it else "$it/" }
        return Manifest(o.getString("version"), o.getString("revision"), files, base)
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

    /** Models whose installed version is complete under [root], in catalogue order. */
    fun readyModels(ctx: Context, root: String? = ModelPrefs.modelRoot(ctx)) =
        Catalogue.get(ctx).models.filter { it.available && isReady(ctx, root, it) }

    /**
     * Copies a ready model from [from] to [to] (roots as in [base]). A copy, not a rename: app
     * storage and shared storage are different filesystems. The source is deleted only when it
     * was app storage; a copy in a shared folder is left for whatever other app uses it.
     * Blocking; call from a worker thread. [progress] starts counting at [offset].
     */
    fun move(ctx: Context, model: Catalogue.Model, from: String?, to: String?, offset: Long,
             cancelled: () -> Boolean, progress: (Long) -> Unit) {
        val m = installed(ctx, model)!!
        val src = dir(ctx, from, model, m)!!
        val dst = dir(ctx, to, model, m)!!.apply { mkdirs() }
        var done = offset
        for (f in m.files) {
            val target = File(dst, f.name)
            if (!(target.exists() && target.length() == f.size)) {
                val part = File(target.path + ".part")
                var written = 0L
                File(src, f.name).inputStream().use { input ->
                    FileOutputStream(part).use { out ->
                        val buf = ByteArray(1 shl 16)
                        while (true) {
                            if (cancelled()) throw InterruptedException("cancelled")
                            val n = input.read(buf)
                            if (n < 0) break
                            out.write(buf, 0, n)
                            written += n
                            progress(done + written)
                        }
                    }
                }
                if (part.length() != f.size || !part.renameTo(target)) {
                    part.delete()
                    throw java.io.IOException("Could not copy ${f.name}")
                }
            }
            done += f.size
            progress(done)
        }
        if (from == null) src.deleteRecursively()
    }

    /**
     * Downloads every missing file of [m] into its own folder, resuming partial `.part` files
     * with a Range request, and verifies SHA-256 before renaming into place. Does not touch the
     * installed model. Blocking; call from a worker thread. [progress] receives bytes done
     * across all files.
     */
    fun download(ctx: Context, model: Catalogue.Model, m: Manifest, cancelled: () -> Boolean, progress: (Long) -> Unit) =
        downloadFiles(dir(ctx, model = model, m = m)!!, m.files, { url(model, m, it) }, cancelled, progress)

    /**
     * [download]'s loop for any set of files: each missing file of [files] into [dir] from
     * [urlOf] (by file name), resumable `.part`, size and SHA-256 checked before it is renamed into
     * place. Also used for the paragraph-break model (the app's ParagraphStore, B-44a), which is
     * not a catalogue model. Blocking; call from a worker thread.
     */
    fun downloadFiles(dir: File, files: List<ModelFile>, urlOf: (String) -> String, cancelled: () -> Boolean, progress: (Long) -> Unit) {
        dir.mkdirs()
        val need = files.sumOf { f -> File(dir, f.name).let { if (it.exists() && it.length() == f.size) 0L else f.size - File(it.path + ".part").length().coerceAtMost(f.size) } }
        if (dir.usableSpace < need + 50_000_000) {
            throw java.io.IOException("Not enough free space: need ${need / 1_000_000} MB, have ${dir.usableSpace / 1_000_000} MB")
        }
        var doneBefore = 0L
        for (f in files) {
            val target = File(dir, f.name)
            if (target.exists() && target.length() == f.size) {
                doneBefore += f.size
                progress(doneBefore)
                continue
            }
            val part = File(target.path + ".part")
            if (part.length() > f.size) part.delete()
            while (part.length() < f.size) {
                if (cancelled()) throw InterruptedException("cancelled")
                val conn = URL(urlOf(f.name)).openConnection() as HttpURLConnection
                conn.connectTimeout = 20_000
                conn.readTimeout = 30_000
                conn.instanceFollowRedirects = true
                val have = part.length()
                if (have > 0) conn.setRequestProperty("Range", "bytes=$have-")
                // finally: a cancel, a timeout or a read error mid-file used to skip disconnect.
                try {
                    val code = conn.responseCode
                    val append = code == HttpURLConnection.HTTP_PARTIAL
                    if (code != HttpURLConnection.HTTP_OK && !append) throw java.io.IOException("HTTP $code for ${f.name}")
                    // A server that ignores Range sends the whole file with 200: start over.
                    var written = if (append) have else 0L
                    conn.inputStream.use { input ->
                        FileOutputStream(part, append).use { out ->
                            val buf = ByteArray(1 shl 16)
                            while (true) {
                                if (cancelled()) throw InterruptedException("cancelled")
                                val n = input.read(buf)
                                if (n < 0) break
                                out.write(buf, 0, n)
                                written += n
                                progress(doneBefore + written)
                            }
                        }
                    }
                } finally {
                    conn.disconnect()
                }
            }
            if (f.sha256 != null && sha256(part) != f.sha256) {
                part.delete()
                throw java.io.IOException("Checksum mismatch for ${f.name}; deleted, try again")
            }
            if (!part.renameTo(target)) throw java.io.IOException("Could not move ${f.name} into place")
            doneBefore += f.size
            progress(doneBefore)
        }
    }

    private fun sha256(f: File): String {
        val md = MessageDigest.getInstance("SHA-256")
        f.inputStream().use { input ->
            val buf = ByteArray(1 shl 16)
            while (true) {
                val n = input.read(buf)
                if (n < 0) break
                md.update(buf, 0, n)
            }
        }
        return md.digest().joinToString("") { "%02x".format(it) }
    }
}
