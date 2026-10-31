package app.hebrish.dictation

import org.json.JSONArray
import org.json.JSONObject
import java.text.Normalizer
import java.time.Instant
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

// No android.* here (org.json only): the saved-transcript format ported from
// desktop/hebrish/transcripts.py (B-74, B-78) so both apps write the same files. Where the files go
// (a folder the user picked, through the Storage Access Framework) is [TranscriptFolder].
// Tests: src/test/.../TranscriptsTest.kt.

/**
 * Saved transcripts (B-74a, Daniel 2026-10-31). Layout: `<folder>/YYYY/MM/DD/<stem>.md`. Names:
 * `HH-MM-SS` (the transcript's time), or `<title>_HH-MM-SS` with a title, in snake_case ([slug]).
 * A stem already taken (its .md or .json) gets `-2`, `-3`, … so nothing is overwritten.
 *
 * Each file: YAML front matter (title, date, version, generator, model, audio_seconds, source,
 * cleanup_model, versions), `# title` (or `# Transcript`), `## Weekday d Month yyyy, HH:MM`, the
 * credit line "*Transcribed by Hebrish Android 1.031 with Sabich v2.3 on 31 October 2026.*", the
 * text. Versions as on desktop: `<stem>.md` (what was in the box), `<stem>.raw.md` (as transcribed,
 * only when its words differ), linked by `<stem>.json` (schema 1). Android has no Save cleaned copy.
 */
object Transcripts {
    const val SLUG_MAX = 60
    const val MANIFEST_SCHEMA = 1
    const val UNTITLED = "Transcript"
    val SUFFIX = mapOf("transcript" to "", "raw" to ".raw")

    private val WS = Regex("\\s+")
    private val WORD = Regex("[a-z0-9]+")
    private val ISO = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ssxxx", Locale.ROOT)

    /** "Notes on the API, v2!" -> "notes_on_the_api_v2". ASCII only; at most [SLUG_MAX], cut at a word end; "" when nothing is left. */
    fun slug(title: String): String {
        val t = Normalizer.normalize(title, Normalizer.Form.NFKD).filter { it.code < 128 }.lowercase(Locale.ROOT)
        val words = WORD.findAll(t).map { it.value }.toList()
        var out = ""
        for (w in words) {
            val nxt = if (out.isEmpty()) w else "${out}_$w"
            if (nxt.length > SLUG_MAX) break
            out = nxt
        }
        return out.ifEmpty { words.firstOrNull()?.take(SLUG_MAX) ?: "" }
    }

    /** Digits are ASCII whatever the phone's language. */
    private fun fmt(f: String, vararg a: Any) = String.format(Locale.ROOT, f, *a)

    private fun at(whenMs: Long, zone: ZoneId): ZonedDateTime = Instant.ofEpochMilli(whenMs).atZone(zone)

    /** The day folder: ["2026", "10", "31"]. */
    fun day(whenMs: Long, zone: ZoneId = ZoneId.systemDefault()): List<String> {
        val t = at(whenMs, zone)
        return listOf(fmt("%04d", t.year), fmt("%02d", t.monthValue), fmt("%02d", t.dayOfMonth))
    }

    /** The file stem (no extension) for a transcript from [whenMs]: neither `<stem>.md` nor `<stem>.json` [taken]. */
    fun stem(whenMs: Long, title: String?, zone: ZoneId = ZoneId.systemDefault(), taken: (String) -> Boolean): String {
        val t = at(whenMs, zone)
        val stamp = fmt("%02d-%02d-%02d", t.hour, t.minute, t.second)
        val s = if (title != null) slug(title) else ""
        val base = if (s.isEmpty()) stamp else "${s}_$stamp"
        var stem = base
        var n = 2
        while (taken("$stem.md") || taken("$stem.json")) stem = "$base-${n++}"
        return stem
    }

    /** 2026-10-31T14:05:09+02:00 (local time with its offset). */
    fun iso(whenMs: Long, zone: ZoneId = ZoneId.systemDefault()): String = ISO.format(at(whenMs, zone))

    private fun dayText(t: ZonedDateTime) = "${t.dayOfMonth} ${t.month.getDisplayName(java.time.format.TextStyle.FULL, Locale.ENGLISH)} ${t.year}"

    /** A YAML scalar as desktop writes it: booleans and numbers bare (floats to one decimal), strings JSON-quoted. */
    fun yaml(v: Any): String = when (v) {
        is Boolean -> if (v) "true" else "false"
        is Float, is Double -> (Math.round((v as Number).toDouble() * 10) / 10.0).toString()
        is Number -> v.toString()
        else -> quote(v.toString())
    }

    /** A JSON string as Python's json.dumps(ensure_ascii=False) writes it. */
    fun quote(s: String): String {
        val sb = StringBuilder("\"")
        for (c in s) when (c) {
            '"' -> sb.append("\\\"")
            '\\' -> sb.append("\\\\")
            '\n' -> sb.append("\\n")
            '\r' -> sb.append("\\r")
            '\t' -> sb.append("\\t")
            '\b' -> sb.append("\\b")
            '\u000c' -> sb.append("\\f")
            else -> if (c < ' ') sb.append(fmt("\\u%04x", c.code)) else sb.append(c)
        }
        return sb.append('"').toString()
    }

    /**
     * The Markdown file. [meta]: generator ("Hebrish Android 1.031"), model ("Sabich v2.3"),
     * audio_seconds, source, cleanup_model, in that order; empty values are left out.
     */
    fun render(text: String, title: String?, whenMs: Long, meta: Map<String, Any?> = emptyMap(),
               version: String = "transcript", manifest: String? = null, zone: ZoneId = ZoneId.systemDefault()): String {
        val fm = LinkedHashMap<String, Any?>()
        fm["title"] = title ?: ""
        fm["date"] = iso(whenMs, zone)
        fm["version"] = version
        fm.putAll(meta)
        fm["versions"] = manifest ?: ""
        val lines = ArrayList<String>()
        lines += "---"
        for ((k, v) in fm) {
            if (v == null || v == "") continue
            lines += "$k: ${if (k == "date" || k == "version") v.toString() else yaml(v)}"
        }
        lines += listOf("---", "")
        val t = at(whenMs, zone)
        val h1 = title?.trim()?.takeIf { it.isNotEmpty() } ?: UNTITLED
        lines += listOf("# $h1", "",
            "## ${t.dayOfWeek.getDisplayName(java.time.format.TextStyle.FULL, Locale.ENGLISH)} ${dayText(t)}, " + fmt("%02d:%02d", t.hour, t.minute), "")
        val gen = (meta["generator"] as? String)?.takeIf { it.isNotEmpty() } ?: "Hebrish"
        val model = (meta["model"] as? String)?.takeIf { it.isNotEmpty() }
        val credit = "*Transcribed by $gen" + (if (model != null) " with $model" else "") + " on ${dayText(t)}.*"
        lines += listOf(credit, "", "")
        return lines.joinToString("\n") + text.trim() + "\n"
    }

    /** Whether the raw text gets its own version: not blank, and its words differ from the saved text's. */
    fun rawDiffers(raw: String?, text: String): Boolean =
        raw != null && raw.isNotBlank() && words(raw) != words(text)

    private fun words(s: String) = s.split(WS).filter { it.isNotEmpty() }

    /** One manifest entry. */
    fun entry(kind: String, file: String, text: String, nowMs: Long, zone: ZoneId = ZoneId.systemDefault()): JSONObject =
        JSONObject().put("kind", kind).put("file", file).put("written", iso(nowMs, zone)).put("words", words(text).size)

    /** `<stem>.json`: the shared details and one entry per version. */
    fun manifest(title: String?, whenMs: Long, meta: Map<String, Any?>, versions: List<JSONObject>,
                 zone: ZoneId = ZoneId.systemDefault()): String {
        val o = JSONObject().put("schema", MANIFEST_SCHEMA).put("title", title ?: JSONObject.NULL).put("date", iso(whenMs, zone))
        for ((k, v) in meta) if (v != null && v != "") o.put(k, v)
        o.put("versions", JSONArray(versions))
        return o.toString(2) + "\n"
    }

    /** The files of one save: (name, content) in write order, the transcript first. */
    fun files(stem: String, text: String, raw: String?, title: String?, whenMs: Long, meta: Map<String, Any?>,
              nowMs: Long, zone: ZoneId = ZoneId.systemDefault()): List<Pair<String, String>> {
        val man = "$stem.json"
        val md = "$stem.md"
        val out = arrayListOf(md to render(text, title, whenMs, meta, "transcript", man, zone))
        val versions = arrayListOf(entry("transcript", md, text, nowMs, zone))
        if (rawDiffers(raw, text)) {
            val r = "$stem${SUFFIX["raw"]}.md"
            out += r to render(raw!!, title, whenMs, meta, "raw", man, zone)
            versions += entry("raw", r, raw, nowMs, zone)
        }
        out += man to manifest(title, whenMs, meta, versions, zone)
        return out
    }
}
