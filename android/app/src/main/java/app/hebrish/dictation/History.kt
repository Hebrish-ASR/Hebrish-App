package app.hebrish.dictation

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.os.Build
import app.hebrish.core.Catalogue
import app.hebrish.core.ModelStore
import app.hebrish.core.TakeDecoder
import app.hebrish.core.Transcriber
import org.json.JSONObject
import java.io.OutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

/**
 * Transcription history (0.8.1): one row per take, kept on the phone in app storage
 * (`databases/history.db`; app backup is off, so it is never copied to a cloud backup), and
 * exported as CSV through the system file picker (DictationActivity), so it can be saved to
 * Google Drive. Daniel, 2026-10-23: "export transcription history on Android so that I can
 * export a CSV to Google Drive, and we can then also see how the Android inference is doing".
 *
 * The table follows the desktop's `dictations` (desktop/hebrish/history.py, schema 2) so the two
 * can be compared and later merged: uid, at (unix seconds), text, words, seconds, model,
 * source, original, model_rev, decode (JSON). `original` stays NULL: Android types into other
 * apps and never sees the user's edits. The decode JSON holds the per-take timings
 * ([TakeDecoder.Stats]) and what produced them (app version, engine, threads, device).
 *
 * This is the storage half of backlog B-19; the History screen (search, counts, correct) is not
 * built yet. Rows start with 0.8.1: takes before the update were never stored.
 */
object History {
    private const val SCHEMA = 1

    private class Db(ctx: Context) : SQLiteOpenHelper(ctx, "history.db", null, SCHEMA) {
        override fun onCreate(db: SQLiteDatabase) {
            db.execSQL("""CREATE TABLE dictations (
                id INTEGER PRIMARY KEY,
                uid TEXT NOT NULL UNIQUE,
                at REAL NOT NULL,
                text TEXT NOT NULL,
                words INTEGER NOT NULL,
                seconds REAL,
                model TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'keyboard',
                original TEXT,
                model_rev TEXT,
                decode TEXT)""")
            db.execSQL("CREATE INDEX dictations_at ON dictations(at)")
        }
        override fun onUpgrade(db: SQLiteDatabase, old: Int, new: Int) = Unit
    }

    @Volatile private var db: Db? = null
    private fun db(ctx: Context): SQLiteDatabase =
        (db ?: synchronized(this) { db ?: Db(ctx.applicationContext).also { db = it } }).writableDatabase

    /** Where a take came from: the voice keyboard, the floating mic, the Try it screen, or Transcription Mode (as on desktop). */
    const val KEYBOARD = "keyboard"
    const val FLOATING = "floating"
    const val TRY = "try"
    const val RECORD = "record"

    /**
     * Stores one finished take unless history is off or the take produced no text. Runs on a
     * background thread; safe to call from the main thread.
     */
    fun record(ctx: Context, text: String, stats: TakeDecoder.Stats, source: String) {
        if (text.isBlank() || !Prefs.keepHistory(ctx)) return
        val app = ctx.applicationContext
        val at = System.currentTimeMillis() / 1000.0
        val model = Catalogue.selected(app)
        val installed = ModelStore.installed(app, model)
        val decode = JSONObject().apply {
            put("app", "android " + app.packageManager.getPackageInfo(app.packageName, 0).versionName)
            put("engine", "${Transcriber.ENGINE}, sherpa-onnx ${BuildConfig.SHERPA_VERSION}")
            put("threads", Transcriber.threads)
            put("cores", Runtime.getRuntime().availableProcessors())
            put("device", "${Build.MANUFACTURER} ${Build.MODEL}")
            put("android", Build.VERSION.RELEASE)
            put("soc", if (Build.VERSION.SDK_INT >= 31) "${Build.SOC_MANUFACTURER} ${Build.SOC_MODEL}" else Build.HARDWARE)
            put("decode_s", round3(stats.decodeSeconds))
            put("load_s", round3(stats.loadSeconds))
            put("wait_s", round3(stats.waitSeconds))
            put("segments", stats.segments)
            put("context_s", round3(stats.contextSeconds))
            put("type_as_you_go", stats.typeAsYouGo)
            put("all_caps", stats.allCaps)
        }
        Thread {
            runCatching {
                db(app).insert("dictations", null, ContentValues().apply {
                    put("uid", UUID.randomUUID().toString())
                    put("at", at)
                    put("text", text)
                    put("words", text.split(Regex("\\s+")).count { it.isNotEmpty() })
                    put("seconds", stats.audioSeconds)
                    put("model", listOfNotNull(model.id, installed?.label?.ifEmpty { null } ?: installed?.version).joinToString(" "))
                    put("source", source)
                    put("model_rev", installed?.revision)
                    put("decode", decode.toString())
                })
            }
        }.start()
    }

    fun count(ctx: Context): Int = runCatching {
        db(ctx).rawQuery("SELECT COUNT(*) FROM dictations", null).use { it.moveToFirst(); it.getInt(0) }
    }.getOrDefault(0)

    fun clear(ctx: Context) {
        db(ctx).delete("dictations", null, null)
    }

    /**
     * The export's columns. The first six match the desktop's history; then the exact weights
     * and the inference diagnostics, flattened out of `decode` so a spreadsheet can chart them.
     * `rtf` is decode_s / seconds (under 1 = faster than real time); `wait_s` is Stop to text;
     * `context_s` (0.8.2) is audio decoded again as context at the seams (empty for 0.8.1 rows).
     */
    val CSV_COLUMNS = listOf(
        "at", "text", "words", "seconds", "model", "source",
        "model_rev", "decode_s", "rtf", "wait_s", "load_s", "segments", "context_s", "type_as_you_go", "all_caps",
        "engine", "threads", "cores", "device", "soc", "android", "app", "uid",
    )

    /** Writes every row, oldest first, as RFC 4180 CSV in UTF-8 with a BOM (so spreadsheets read it as UTF-8). Returns the row count. */
    fun writeCsv(ctx: Context, out: OutputStream): Int {
        val iso = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US)
        var n = 0
        out.bufferedWriter(Charsets.UTF_8).use { w ->
            w.write("﻿")
            w.write(CSV_COLUMNS.joinToString(",") + "\r\n")
            db(ctx).rawQuery("SELECT uid, at, text, words, seconds, model, source, model_rev, decode FROM dictations ORDER BY at", null).use { c ->
                while (c.moveToNext()) {
                    val d = runCatching { JSONObject(c.getString(8) ?: "{}") }.getOrDefault(JSONObject())
                    val seconds = if (c.isNull(4)) null else c.getDouble(4)
                    val decodeS = d.optDouble("decode_s", Double.NaN)
                    val rtf = if (seconds != null && seconds > 0 && !decodeS.isNaN()) round3(decodeS / seconds).toString() else ""
                    fun opt(k: String) = if (d.has(k)) d.get(k).toString() else ""
                    val row = listOf(
                        iso.format(Date((c.getDouble(1) * 1000).toLong())), c.getString(2), c.getInt(3).toString(),
                        seconds?.let { "%.2f".format(Locale.US, it) } ?: "", c.getString(5), c.getString(6),
                        c.getString(7) ?: "", opt("decode_s"), rtf, opt("wait_s"), opt("load_s"), opt("segments"), opt("context_s"),
                        opt("type_as_you_go"), opt("all_caps"), opt("engine"), opt("threads"), opt("cores"),
                        opt("device"), opt("soc"), opt("android"), opt("app"), c.getString(0),
                    )
                    w.write(row.joinToString(",") { csv(it) } + "\r\n")
                    n++
                }
            }
        }
        return n
    }

    /** RFC 4180: quote a field with a comma, quote, CR or LF, doubling quotes inside. */
    fun csv(v: String): String =
        if (v.any { it == ',' || it == '"' || it == '\n' || it == '\r' }) "\"" + v.replace("\"", "\"\"") + "\"" else v

    private fun round3(v: Double) = Math.round(v * 1000) / 1000.0
}
