package app.hebrish.core

import android.content.Context
import android.provider.UserDictionary
import android.view.inputmethod.InputMethodManager
import org.json.JSONArray
import org.json.JSONObject
import java.util.regex.Pattern

/**
 * The personal dictionary (0.9.0): words the user wants written a certain way, applied by
 * [TakeDecoder] to the model's text after decoding, before ALL CAPS. The rules are shared with
 * the desktop app: shared/personal-dictionary.md, test set shared/dictionary-cases.json.
 *
 * Entries come from Android's system personal dictionary ([UserDictionary.Words]: word, and its
 * shortcut as a "heard as" phrase) plus the words added in Hebrish ([own]). Android lets only an
 * *enabled* keyboard or spell checker read or write the system list, silently returning nothing
 * to anyone else (AOSP UserDictionaryProvider, read 2026-10-23), so [systemAccess] is "this
 * package is an enabled keyboard", and the last list read is cached for when it isn't.
 * Same SharedPreferences file as [ModelPrefs].
 */
object PersonalDictionary {
    /** [word] as written; [heard] what the model writes instead. [system]: from Android's list. */
    data class Entry(val word: String, val heard: List<String> = emptyList(), val system: Boolean = false)

    private fun sp(ctx: Context) = ctx.getSharedPreferences("prefs", Context.MODE_PRIVATE)

    /** True when Android lets this app read and write the system personal dictionary. */
    fun systemAccess(ctx: Context): Boolean = runCatching {
        (ctx.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager)
            .enabledInputMethodList.any { it.packageName == ctx.packageName }
    }.getOrDefault(false)

    /** Every entry in use: Hebrish's own, then the system list (read now if allowed, else the last copy). */
    fun entries(ctx: Context): List<Entry> = own(ctx) + (readSystem(ctx) ?: cachedSystem(ctx))

    /** The system list, or null without access. Each read refreshes the cached copy. */
    fun readSystem(ctx: Context): List<Entry>? {
        if (!systemAccess(ctx)) return null
        val words = runCatching {
            val cols = arrayOf(UserDictionary.Words.WORD, UserDictionary.Words.SHORTCUT)
            ctx.contentResolver.query(UserDictionary.Words.CONTENT_URI, cols, null, null, null)?.use { c ->
                val list = mutableListOf<Entry>()
                while (c.moveToNext()) {
                    val word = c.getString(0)?.trim().orEmpty()
                    if (word.isEmpty()) continue
                    val shortcut = c.getString(1)?.trim().orEmpty()
                    list += Entry(word, if (shortcut.isEmpty()) emptyList() else listOf(shortcut), system = true)
                }
                list.distinct()
            }
        }.getOrNull() ?: return null
        sp(ctx).edit().putString("dict_system", toJson(words)).putLong("dict_system_read", System.currentTimeMillis()).apply()
        return words
    }

    fun cachedSystem(ctx: Context): List<Entry> = fromJson(sp(ctx).getString("dict_system", null), system = true)

    /** When the system list was last read (ms), or 0. */
    fun systemReadAt(ctx: Context): Long = sp(ctx).getLong("dict_system_read", 0)

    /** Words added in Hebrish. Kept here as well as in the system list, so they work without access. */
    fun own(ctx: Context): List<Entry> = fromJson(sp(ctx).getString("dict_own", null), system = false)

    /**
     * Adds [word] (with an optional [heard] phrase) to Hebrish's list and, with access, to the
     * system list, where the phrase becomes the word's shortcut. Returns true when the system
     * list took it too.
     */
    fun add(ctx: Context, word: String, heard: String?): Boolean {
        val w = word.trim()
        val h = heard?.trim().orEmpty()
        if (w.isEmpty()) return false
        val entry = Entry(w, if (h.isEmpty()) emptyList() else listOf(h))
        sp(ctx).edit().putString("dict_own", toJson(own(ctx).filter { it.word != w } + entry)).apply()
        if (!systemAccess(ctx)) return false
        if (readSystem(ctx)?.any { it.word == w && it.heard == entry.heard } != true)
            runCatching { UserDictionary.Words.addWord(ctx, w, 250, h.ifEmpty { null }, null) }
        return readSystem(ctx)?.any { it.word == w } == true
    }

    /** Removes [word] from Hebrish's list and, with access, from the system list (so from every keyboard). */
    fun remove(ctx: Context, word: String) {
        sp(ctx).edit().putString("dict_own", toJson(own(ctx).filter { it.word != word })).apply()
        if (!systemAccess(ctx)) return
        runCatching { ctx.contentResolver.delete(UserDictionary.Words.CONTENT_URI, "${UserDictionary.Words.WORD}=?", arrayOf(word)) }
        readSystem(ctx)
    }

    private fun toJson(entries: List<Entry>) = JSONArray().also { a ->
        for (e in entries) a.put(JSONObject().put("word", e.word).put("heard", JSONArray(e.heard)))
    }.toString()

    private fun fromJson(s: String?, system: Boolean): List<Entry> = runCatching {
        val a = JSONArray(s ?: return emptyList())
        (0 until a.length()).map { i ->
            val o = a.getJSONObject(i)
            val h = o.optJSONArray("heard") ?: JSONArray()
            Entry(o.getString("word"), (0 until h.length()).map { h.getString(it) }, system)
        }
    }.getOrDefault(emptyList())

    // Matching: shared/personal-dictionary.md, "Matching rules".

    private const val EDGE = "[\\p{L}\\p{N}_]"

    private class Source(val pattern: String, val length: Int, val word: String, val isWord: Boolean)

    /** A function that applies [entries] to a piece of text. Compile once per take. */
    fun compile(entries: List<Entry>): (String) -> String {
        val sources = mutableListOf<Source>()
        for (e in entries) {
            val word = e.word.trim()
            if (word.isEmpty()) continue
            for (h in e.heard.map { it.trim() }.filter { it.isNotEmpty() })
                sources += Source(h.split(Regex("\\s+")).joinToString("\\s+") { Pattern.quote(it) }, h.length, word, false)
            sources += Source(wordPattern(word), word.length, word, true)
        }
        if (sources.isEmpty()) return { it }
        sources.sortByDescending { it.length }
        val regex = Pattern.compile("(?<!$EDGE)(?:" + sources.joinToString("|") { "(${it.pattern})" } + ")(?!$EDGE)",
            Pattern.CASE_INSENSITIVE or Pattern.UNICODE_CASE)
        return fun(text: String): String {
            val m = regex.matcher(text)
            val out = StringBuilder()
            var at = 0
            while (m.find()) {
                val i = (1..sources.size).first { m.group(it) != null }
                out.append(text, at, m.start()).append(replacement(sources[i - 1], m.group()))
                at = m.end()
            }
            return out.append(text, at, text.length).toString()
        }
    }

    /** Rule 4: the word literally; with 4+ letters and digits, one space, hyphen or apostrophe may split any two. */
    private fun wordPattern(word: String): String {
        val split = word.count { it.isLetterOrDigit() } >= 4
        val p = StringBuilder()
        var i = 0
        while (i < word.length) {
            val c = word[i]
            if (c.isWhitespace()) {
                while (i + 1 < word.length && word[i + 1].isWhitespace()) i++
                p.append("\\s+")
            } else {
                p.append(if (c.isLetterOrDigit()) c.toString() else "\\$c")
                if (split && c.isLetterOrDigit() && i + 1 < word.length && word[i + 1].isLetterOrDigit()) p.append("[\\s\\-']?")
            }
            i++
        }
        return p.toString()
    }

    /** Rule 5: a word with capitals as written; an all-lower-case one is a spelling, not a case. */
    private fun replacement(s: Source, matched: String): String {
        if (s.word.any { it.isUpperCase() }) return s.word
        val norm = { t: String -> t.lowercase().replace(Regex("\\s+"), " ") }
        if (s.isWord && norm(matched) == norm(s.word)) return matched
        return if (matched.first().isUpperCase()) s.word.replaceFirstChar { it.uppercaseChar() } else s.word
    }
}
