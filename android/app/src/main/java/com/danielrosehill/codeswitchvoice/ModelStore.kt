package com.danielrosehill.codeswitchvoice

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * The fine-tune as a sherpa-onnx int8 transducer. Each installed model is a [Manifest]: one HF
 * commit plus the size and SHA-256 of every file at it, so a later push to the model repo never
 * changes what is already on the phone. [BUNDLED] (v3, run r3-en30) is what this APK knows
 * offline; [checkLatest] builds a manifest for whatever `main` holds now.
 */
object ModelStore {
    const val REPO = "danielrosehill/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching"
    private const val SUBDIR = "sherpa-onnx/int8"
    /** Optional label file written next to the weights by the training repo's export_sherpa. */
    private const val VERSION_FILE = "version.json"

    data class ModelFile(val name: String, val size: Long, val sha256: String?)

    data class Manifest(val version: String, val revision: String, val files: List<ModelFile>) {
        val totalBytes: Long get() = files.sumOf { it.size }
        val dirName: String get() = "$version-${revision.take(12)}"

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
                return Manifest(o.getString("version"), o.getString("revision"), files)
            }
        }
    }

    /** Sizes and SHA-256 are the HF tree API's `size` and `lfs.oid` at that revision. */
    val BUNDLED = Manifest(
        "v3", "92679110e821baf9425f620c9deb9920ce9b7539", listOf(
            ModelFile("encoder.int8.onnx", 652282307, "b79474c430250d1dd34a2b0ff2f5f2bf6643faffe8b782519b3b0b5e98f42237"),
            ModelFile("decoder.int8.onnx", 7257753, "bb625f0d27add1342c63e78ea6561331960f3fcef57221cc50c3a7691aa4bd68"),
            ModelFile("joiner.int8.onnx", 1739080, "095c35c6ca595b65e1ec83aa561fd4207e1d3200ffe5a7473431e2a5da3c7fba"),
            // Small files are stored in git, not LFS, so HF gives no hash; size is checked.
            ModelFile("tokens.txt", 9384, null),
        )
    )

    /** The files the recognizer loads; anything else in the HF folder (bpe.vocab) is skipped. */
    private val NAMES = BUNDLED.files.map { it.name }

    /** The model the app loads: the last one fully downloaded, or [BUNDLED] before any update. */
    fun installed(ctx: Context): Manifest = Prefs.installedManifest(ctx)?.let(Manifest::fromJson) ?: BUNDLED

    fun url(m: Manifest, f: ModelFile) = "https://huggingface.co/$REPO/resolve/${m.revision}/$SUBDIR/${f.name}"

    /** Folder name inside a user-chosen location, so other apps can recognise what it holds. */
    const val SHARED_FOLDER = "Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching"

    /**
     * The folder that holds one subfolder per model version. App-private by default; under a
     * user-chosen folder (Prefs.modelRoot) it gets its own subfolder, because pruneOld deletes
     * everything else in it.
     */
    fun base(ctx: Context, root: String? = Prefs.modelRoot(ctx)) =
        if (root == null) File(ctx.filesDir, "models") else File(root, SHARED_FOLDER)

    fun dir(ctx: Context, root: String? = Prefs.modelRoot(ctx), m: Manifest = installed(ctx)) =
        File(base(ctx, root), m.dirName)

    fun file(ctx: Context, name: String) = File(dir(ctx), name)

    fun isReady(ctx: Context, root: String? = Prefs.modelRoot(ctx), m: Manifest = installed(ctx)) =
        m.files.all { File(dir(ctx, root, m), it.name).let { f -> f.exists() && f.length() == it.size } }

    /** Deletes every model folder except the installed one: older versions and abandoned updates. */
    fun pruneOld(ctx: Context) {
        val keep = dir(ctx).name
        base(ctx).listFiles()?.filter { it.name != keep }?.forEach { it.deleteRecursively() }
    }

    /**
     * Asks HF what `main` holds now. Blocking; call from a worker thread. The manifest is pinned
     * to the commit `main` pointed at during the check, so a push mid-download cannot mix files
     * from two versions. The label comes from [VERSION_FILE]; without one it is the short commit.
     */
    fun checkLatest(): Manifest {
        val sha = JSONObject(get("https://huggingface.co/api/models/$REPO/revision/main")).getString("sha")
        val tree = JSONArray(get("https://huggingface.co/api/models/$REPO/tree/$sha/$SUBDIR"))
        val byName = (0 until tree.length()).map { tree.getJSONObject(it) }.associateBy { it.getString("path").substringAfterLast('/') }
        val files = NAMES.map { name ->
            val e = byName[name] ?: throw java.io.IOException("$name missing from $SUBDIR at ${sha.take(12)}")
            ModelFile(name, e.getLong("size"), e.optJSONObject("lfs")?.getString("oid"))
        }
        val version = runCatching {
            JSONObject(get("https://huggingface.co/$REPO/resolve/$sha/$SUBDIR/$VERSION_FILE")).getString("version")
        }.getOrNull() ?: "rev ${sha.take(7)}"
        return Manifest(version, sha, files)
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

    /**
     * Copies a ready model from [from] to [to] (roots as in [base]). A copy, not a rename: app
     * storage and shared storage are different filesystems. The source is deleted only when it
     * was app storage; a copy in a shared folder is left for whatever other app uses it.
     * Blocking; call from a worker thread.
     */
    fun move(ctx: Context, from: String?, to: String?, cancelled: () -> Boolean, progress: (Long) -> Unit) {
        val m = installed(ctx)
        val src = dir(ctx, from, m)
        val dst = dir(ctx, to, m).apply { mkdirs() }
        var done = 0L
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
    fun download(ctx: Context, m: Manifest, cancelled: () -> Boolean, progress: (Long) -> Unit) {
        val dir = dir(ctx, m = m).apply { mkdirs() }
        val need = m.files.sumOf { f -> File(dir, f.name).let { if (it.exists() && it.length() == f.size) 0L else f.size - File(it.path + ".part").length().coerceAtMost(f.size) } }
        if (dir.usableSpace < need + 50_000_000) {
            throw java.io.IOException("Not enough free space: need ${need / 1_000_000} MB, have ${dir.usableSpace / 1_000_000} MB")
        }
        var doneBefore = 0L
        for (f in m.files) {
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
                val conn = URL(url(m, f)).openConnection() as HttpURLConnection
                conn.connectTimeout = 20_000
                conn.readTimeout = 30_000
                conn.instanceFollowRedirects = true
                val have = part.length()
                if (have > 0) conn.setRequestProperty("Range", "bytes=$have-")
                val code = conn.responseCode
                val append = code == HttpURLConnection.HTTP_PARTIAL
                if (code != HttpURLConnection.HTTP_OK && !append) {
                    conn.disconnect()
                    throw java.io.IOException("HTTP $code for ${f.name}")
                }
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
                conn.disconnect()
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
