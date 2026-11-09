package app.hebrish.dictation

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.os.Handler
import android.os.Looper
import app.hebrish.core.Transcriber
import java.util.concurrent.Executors

/**
 * Notes (B-100, 2026-11-09): plain-text notes written by dictation or by hand, kept on the phone
 * only (`databases/notes.db`, app storage; app backup is off, so no cloud copy and no sync, by
 * design for now: cloud sync and desktop parity are backlog I-21). Daniel, 2026-11-09: "a notepad
 * with a message history and you can use the model for dictation. No online sync."
 *
 * One table, `notes`: id, created and updated (unix ms), title, text. Writes go through [io], one
 * background thread for the whole app, so saves stay in order (a new note's insert lands before
 * the next save of it) and never block the screen.
 *
 * Titles (B-101): a note left without a title gets one from the title model ([Titles], the same
 * model Transcription Mode uses), on [titler], a second thread, so a slow title never holds up a
 * save. A title the user typed is never replaced: the model's title is only written while the
 * title is still empty. Screens hear about it through [listeners].
 */
object Notes {
    data class Note(val id: Long, val created: Long, val updated: Long, val title: String, val text: String)

    /** 1: B-100 (never released). 2: `title`. */
    private const val SCHEMA = 2
    /** Fewer words than this and a note is too thin to title. */
    const val TITLE_MIN_WORDS = 5

    private class Db(ctx: Context) : SQLiteOpenHelper(ctx, "notes.db", null, SCHEMA) {
        override fun onCreate(db: SQLiteDatabase) {
            db.execSQL("""CREATE TABLE notes (
                id INTEGER PRIMARY KEY,
                created INTEGER NOT NULL,
                updated INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                text TEXT NOT NULL)""")
            db.execSQL("CREATE INDEX notes_updated ON notes(updated)")
        }
        override fun onUpgrade(db: SQLiteDatabase, old: Int, new: Int) {
            if (old < 2) db.execSQL("ALTER TABLE notes ADD COLUMN title TEXT NOT NULL DEFAULT ''")
        }
    }

    @Volatile private var db: Db? = null
    private fun db(ctx: Context): SQLiteDatabase =
        (db ?: synchronized(this) { db ?: Db(ctx.applicationContext).also { db = it } }).writableDatabase

    /** The single writer thread. Never shut down: a take can finish after its screen has closed. */
    val io = Executors.newSingleThreadExecutor { r -> Thread(r, "notes").apply { isDaemon = true } }
    /** Runs the title model, one note at a time. */
    private val titler = Executors.newSingleThreadExecutor { r -> Thread(r, "notes-title").apply { isDaemon = true } }
    private val main = Handler(Looper.getMainLooper())
    /** Ids queued or being titled (main thread), so leaving a note twice doesn't title it twice. */
    private val titling = mutableSetOf<Long>()

    /** Called on the main thread with a note's id after the model gave it a title. Add in onResume, remove in onPause. */
    val listeners = mutableSetOf<(Long) -> Unit>()

    private const val COLS = "id, created, updated, title, text"
    private fun note(c: android.database.Cursor) = Note(c.getLong(0), c.getLong(1), c.getLong(2), c.getString(3), c.getString(4))

    /** Newest edit first. */
    fun all(ctx: Context): List<Note> =
        db(ctx).rawQuery("SELECT $COLS FROM notes ORDER BY updated DESC", null).use { c ->
            buildList { while (c.moveToNext()) add(note(c)) }
        }

    fun get(ctx: Context, id: Long): Note? =
        db(ctx).rawQuery("SELECT $COLS FROM notes WHERE id = ?", arrayOf(id.toString())).use { c ->
            if (c.moveToFirst()) note(c) else null
        }

    /** Inserts when [id] is 0 (returns the new id), else updates. Call on [io]. */
    fun save(ctx: Context, id: Long, title: String, text: String): Long {
        val now = System.currentTimeMillis()
        val v = ContentValues().apply { put("title", title); put("text", text); put("updated", now) }
        if (id != 0L && db(ctx).update("notes", v, "id = ?", arrayOf(id.toString())) > 0) return id
        v.put("created", now)
        return db(ctx).insert("notes", null, v)
    }

    /** Call on [io]. */
    fun delete(ctx: Context, id: Long) {
        db(ctx).delete("notes", "id = ?", arrayOf(id.toString()))
    }

    /** True when notes would get a title now: the setting is on and the model is downloaded. */
    fun canTitle(ctx: Context) = Prefs.noteTitles(ctx) && CleanupStore.titleFile(ctx) != null

    fun words(text: String) = text.split(Regex("\\s+")).count { it.isNotEmpty() }

    /**
     * Titles note [id] from [text] in the background if it can, and stores the title only if the
     * note's title is still empty then. Main thread. [id] must already be saved (0 is ignored).
     */
    fun titleLater(ctx: Context, id: Long, text: String) {
        if (id == 0L || id in titling || words(text) < TITLE_MIN_WORDS || !canTitle(ctx)) return
        val app = ctx.applicationContext
        val file = CleanupStore.titleFile(app) ?: return
        val max = Prefs.titleMaxChars(app)
        titling += id
        titler.execute {
            // One llama.cpp model at a time in this process's title path; Transcription Mode's Save
            // uses its own worker, so the two can overlap in theory (both are short and user-started).
            val title = runCatching {
                CleanupModel(file, Transcriber.threads, Titles.CTX).use { Titles.make(text, it, max) }
            }.getOrNull()
            io.execute {
                val stored = title != null && db(app).update("notes", ContentValues().apply { put("title", title) },
                    "id = ? AND title = ''", arrayOf(id.toString())) > 0
                main.post {
                    titling -= id
                    if (stored) listeners.toList().forEach { it(id) }
                }
            }
        }
    }
}
