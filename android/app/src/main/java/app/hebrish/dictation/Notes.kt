package app.hebrish.dictation

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.util.concurrent.Executors

/**
 * Notes (2026-11-09): plain-text notes written by dictation or by hand, kept on the phone only
 * (`databases/notes.db`, app storage; app backup is off, so no cloud copy and no sync, by design).
 * Daniel, 2026-11-09: "a notepad with a message history and you can use the model for dictation.
 * No online sync."
 *
 * One table, `notes`: id, created and updated (unix ms), text. Writes go through [io], one
 * background thread for the whole app, so saves stay in order (a new note's insert lands before
 * the next save of it) and never block the screen.
 */
object Notes {
    data class Note(val id: Long, val created: Long, val updated: Long, val text: String)

    private const val SCHEMA = 1

    private class Db(ctx: Context) : SQLiteOpenHelper(ctx, "notes.db", null, SCHEMA) {
        override fun onCreate(db: SQLiteDatabase) {
            db.execSQL("""CREATE TABLE notes (
                id INTEGER PRIMARY KEY,
                created INTEGER NOT NULL,
                updated INTEGER NOT NULL,
                text TEXT NOT NULL)""")
            db.execSQL("CREATE INDEX notes_updated ON notes(updated)")
        }
        override fun onUpgrade(db: SQLiteDatabase, old: Int, new: Int) = Unit
    }

    @Volatile private var db: Db? = null
    private fun db(ctx: Context): SQLiteDatabase =
        (db ?: synchronized(this) { db ?: Db(ctx.applicationContext).also { db = it } }).writableDatabase

    /** The single writer thread. Never shut down: a take can finish after its screen has closed. */
    val io = Executors.newSingleThreadExecutor { r -> Thread(r, "notes").apply { isDaemon = true } }

    /** Newest edit first. */
    fun all(ctx: Context): List<Note> =
        db(ctx).rawQuery("SELECT id, created, updated, text FROM notes ORDER BY updated DESC", null).use { c ->
            buildList { while (c.moveToNext()) add(Note(c.getLong(0), c.getLong(1), c.getLong(2), c.getString(3))) }
        }

    fun get(ctx: Context, id: Long): Note? =
        db(ctx).rawQuery("SELECT id, created, updated, text FROM notes WHERE id = ?", arrayOf(id.toString())).use { c ->
            if (c.moveToFirst()) Note(c.getLong(0), c.getLong(1), c.getLong(2), c.getString(3)) else null
        }

    /** Inserts when [id] is 0 (returns the new id), else updates. Call on [io]. */
    fun save(ctx: Context, id: Long, text: String): Long {
        val now = System.currentTimeMillis()
        val v = ContentValues().apply { put("text", text); put("updated", now) }
        if (id != 0L && db(ctx).update("notes", v, "id = ?", arrayOf(id.toString())) > 0) return id
        v.put("created", now)
        return db(ctx).insert("notes", null, v)
    }

    /** Call on [io]. */
    fun delete(ctx: Context, id: Long) {
        db(ctx).delete("notes", "id = ?", arrayOf(id.toString()))
    }
}
