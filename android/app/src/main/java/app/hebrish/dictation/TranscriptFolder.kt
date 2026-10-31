package app.hebrish.dictation

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.DocumentsContract
import android.provider.DocumentsContract.Document
import java.io.IOException

/**
 * The transcripts folder (B-74a; desktop B-74): a folder the user picks once with the system
 * picker (ACTION_OPEN_DOCUMENT_TREE), kept with a persisted read/write grant. Storage Access
 * Framework only: no all-files permission, which Google Play refuses for an app like this. Any
 * folder the picker offers works (phone storage, an SD card, a cloud provider's folder).
 *
 * [save] writes one transcript's files ([Transcripts.files]) under `YYYY/MM/DD/`, creating the
 * day folders as needed, never overwriting (the stem is chosen against the day folder's listing).
 * Blocking; call from a worker thread.
 */
object TranscriptFolder {
    /** The picker, starting where the user picked last time. */
    fun pickIntent(ctx: Context): Intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION or
            Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION or Intent.FLAG_GRANT_PREFIX_URI_PERMISSION)
        Prefs.transcriptsTree(ctx)?.let { putExtra(DocumentsContract.EXTRA_INITIAL_URI, Uri.parse(it)) }
    }

    /** The picker's answer: keep the grant across restarts and remember the folder; the old grant is released. */
    fun accept(ctx: Context, tree: Uri) {
        val cr = ctx.contentResolver
        val flags = Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
        cr.takePersistableUriPermission(tree, flags)
        Prefs.transcriptsTree(ctx)?.let(Uri::parse)?.takeIf { it != tree }?.let { old ->
            runCatching { cr.releasePersistableUriPermission(old, flags) }
        }
        Prefs.setTranscriptsTree(ctx, tree.toString())
    }

    /** The chosen folder while the app still holds write access to it, else null (never chosen, or the grant was revoked). */
    fun tree(ctx: Context): Uri? {
        val u = Prefs.transcriptsTree(ctx)?.let(Uri::parse) ?: return null
        return u.takeIf { ctx.contentResolver.persistedUriPermissions.any { p -> p.uri == u && p.isWritePermission } }
    }

    /** The folder's name as the provider shows it ("Transcripts"), or null. */
    fun label(ctx: Context): String? {
        val t = tree(ctx) ?: return null
        return runCatching {
            val doc = DocumentsContract.buildDocumentUriUsingTree(t, DocumentsContract.getTreeDocumentId(t))
            ctx.contentResolver.query(doc, arrayOf(Document.COLUMN_DISPLAY_NAME), null, null, null)?.use { c ->
                if (c.moveToFirst()) c.getString(0) else null
            }
        }.getOrNull()
    }

    private data class Child(val id: String, val dir: Boolean)

    private fun children(ctx: Context, tree: Uri, parent: String): Map<String, Child> {
        val out = HashMap<String, Child>()
        val uri = DocumentsContract.buildChildDocumentsUriUsingTree(tree, parent)
        ctx.contentResolver.query(uri, arrayOf(Document.COLUMN_DOCUMENT_ID, Document.COLUMN_DISPLAY_NAME, Document.COLUMN_MIME_TYPE),
            null, null, null)?.use { c ->
            while (c.moveToNext()) out[c.getString(1)] = Child(c.getString(0), c.getString(2) == Document.MIME_TYPE_DIR)
        }
        return out
    }

    private fun dir(ctx: Context, tree: Uri, parent: String, name: String): String {
        children(ctx, tree, parent)[name]?.let { if (it.dir) return it.id else throw IOException("$name is a file, not a folder") }
        val made = DocumentsContract.createDocument(ctx.contentResolver,
            DocumentsContract.buildDocumentUriUsingTree(tree, parent), Document.MIME_TYPE_DIR, name)
            ?: throw IOException("couldn't make the folder $name")
        return DocumentsContract.getDocumentId(made)
    }

    /**
     * Writes one transcript (see [Transcripts.files]) and returns its path inside the folder,
     * "2026/10/31/shopping_list_14-05-09.md". Throws when no folder is chosen or writing fails.
     */
    fun save(ctx: Context, text: String, raw: String?, title: String?, whenMs: Long, meta: Map<String, Any?>): String {
        val tree = tree(ctx) ?: throw IOException("no transcripts folder")
        var parent = DocumentsContract.getTreeDocumentId(tree)
        val day = Transcripts.day(whenMs)
        for (part in day) parent = dir(ctx, tree, parent, part)
        val names = children(ctx, tree, parent).keys
        val stem = Transcripts.stem(whenMs, title) { it in names }
        val files = Transcripts.files(stem, text, raw, title, whenMs, meta, System.currentTimeMillis())
        val parentUri = DocumentsContract.buildDocumentUriUsingTree(tree, parent)
        for ((name, body) in files) {
            // application/octet-stream: providers keep the name as given (a text/* type can get ".txt" added).
            val uri = DocumentsContract.createDocument(ctx.contentResolver, parentUri, "application/octet-stream", name)
                ?: throw IOException("couldn't create $name")
            (ctx.contentResolver.openOutputStream(uri, "w") ?: throw IOException("couldn't write $name")).use {
                it.write(body.toByteArray(Charsets.UTF_8))
            }
        }
        return (day + files.first().first).joinToString("/")
    }
}
