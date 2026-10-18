package com.danielrosehill.codeswitchvoice

import android.content.Context
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * The v3 fine-tune (training run r3-en30) as a sherpa-onnx int8 transducer, pinned to one HF
 * revision so a later push to the model repo can never change what an installed app loads.
 * Sizes and SHA-256 are the HF tree API's `size` and `lfs.oid` at that revision.
 */
object ModelStore {
    const val MODEL_VERSION = "v3"
    const val REPO = "danielrosehill/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching"
    const val REVISION = "92679110e821baf9425f620c9deb9920ce9b7539"

    data class ModelFile(val name: String, val size: Long, val sha256: String?)

    val FILES = listOf(
        ModelFile("encoder.int8.onnx", 652282307, "b79474c430250d1dd34a2b0ff2f5f2bf6643faffe8b782519b3b0b5e98f42237"),
        ModelFile("decoder.int8.onnx", 7257753, "bb625f0d27add1342c63e78ea6561331960f3fcef57221cc50c3a7691aa4bd68"),
        ModelFile("joiner.int8.onnx", 1739080, "095c35c6ca595b65e1ec83aa561fd4207e1d3200ffe5a7473431e2a5da3c7fba"),
        // Small files are stored in git, not LFS, so HF gives no hash; size is checked.
        ModelFile("tokens.txt", 9384, null),
    )

    val totalBytes: Long = FILES.sumOf { it.size }

    fun url(f: ModelFile) = "https://huggingface.co/$REPO/resolve/$REVISION/sherpa-onnx/int8/${f.name}"

    /** Folder name inside a user-chosen location, so other apps can recognise what it holds. */
    const val SHARED_FOLDER = "Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching"

    /**
     * The folder that holds one subfolder per model version. App-private by default; under a
     * user-chosen folder (Prefs.modelRoot) it gets its own subfolder, because pruneOld deletes
     * everything else in it.
     */
    fun base(ctx: Context, root: String? = Prefs.modelRoot(ctx)) =
        if (root == null) File(ctx.filesDir, "models") else File(root, SHARED_FOLDER)

    fun dir(ctx: Context, root: String? = Prefs.modelRoot(ctx)) =
        File(base(ctx, root), "$MODEL_VERSION-${REVISION.take(12)}")

    fun file(ctx: Context, name: String) = File(dir(ctx), name)

    fun isReady(ctx: Context, root: String? = Prefs.modelRoot(ctx)) =
        FILES.all { File(dir(ctx, root), it.name).let { f -> f.exists() && f.length() == it.size } }

    /** Removes models left by earlier app versions that pinned a different revision. */
    fun pruneOld(ctx: Context) {
        val keep = dir(ctx).name
        base(ctx).listFiles()?.filter { it.name != keep }?.forEach { it.deleteRecursively() }
    }

    /**
     * Copies a ready model from [from] to [to] (roots as in [base]). A copy, not a rename: app
     * storage and shared storage are different filesystems. The source is deleted only when it
     * was app storage; a copy in a shared folder is left for whatever other app uses it.
     * Blocking; call from a worker thread.
     */
    fun move(ctx: Context, from: String?, to: String?, cancelled: () -> Boolean, progress: (Long) -> Unit) {
        val src = dir(ctx, from)
        val dst = dir(ctx, to).apply { mkdirs() }
        var done = 0L
        for (f in FILES) {
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
     * Downloads every missing file, resuming partial `.part` files with a Range request, and
     * verifies SHA-256 before renaming into place. Blocking; call from a worker thread.
     * [progress] receives bytes done across all files.
     */
    fun download(ctx: Context, cancelled: () -> Boolean, progress: (Long) -> Unit) {
        dir(ctx).mkdirs()
        var doneBefore = 0L
        for (f in FILES) {
            val target = file(ctx, f.name)
            if (target.exists() && target.length() == f.size) {
                doneBefore += f.size
                progress(doneBefore)
                continue
            }
            val part = File(target.path + ".part")
            if (part.length() > f.size) part.delete()
            while (part.length() < f.size) {
                if (cancelled()) throw InterruptedException("cancelled")
                val conn = URL(url(f)).openConnection() as HttpURLConnection
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
