package app.hebrish.core

/**
 * How much of a streaming take's text goes out at a time (B-13; a port of the desktop's
 * `LiveStream._ready` / `_release` with its default `stream_release` rule, "phrase", engine.py).
 *
 * The streaming result only grows, in BPE pieces ("ask Av", "ask Avi for"), so any prefix can be
 * released and the next release continues it. Releases end on a word or a mark, never inside a word:
 * - everything up to the last sentence mark (. ? !) at once;
 * - up to a clause mark (, ; :) once that makes at least [Rule.minWords] words;
 * - everything once the text has not grown for [Rule.pauseMs] (the speaker paused);
 * - whole words once the oldest held word is [Rule.holdMs] old, keeping the last two back so a
 *   sentence's last word doesn't follow on its own a moment later;
 * - with `last` (Stop), the rest.
 * Daniel on desktop, 2026-10-22: a paste every word or two "is very jarring"; too long a wait and
 * "you're there wondering if it's actually working". Pure logic: unit-tested in StreamReleaseTest.
 */
class StreamRelease(private val rule: Rule = PHRASE) {
    data class Rule(val stops: String, val clauses: String, val minWords: Int, val pauseMs: Long, val holdMs: Long)

    /** Everything released so far (the raw model text, before any styling). */
    var sent = ""
        private set
    private var text = ""
    private var grewAt = 0L
    private var heldAt: Long? = null

    /**
     * The newly released part of [result] (the whole streaming result so far) at [now] (ms, any
     * monotonic clock), or "". Each release after the first starts with the space before its first word.
     * A [result] that no longer starts with what was released (not seen with greedy decoding)
     * releases nothing more, rather than contradict text already typed.
     */
    fun next(result: String, last: Boolean, now: Long): String {
        val ready = ready(result, last, now)
        if (ready.length <= sent.length || !ready.startsWith(sent)) return ""
        val new = ready.substring(sent.length)
        sent = ready
        heldAt = if (result.substring(ready.length).isBlank()) null else now
        return new
    }

    private fun ready(result: String, last: Boolean, now: Long): String {
        if (result != text) { text = result; grewAt = now }
        if (!result.startsWith(sent)) return sent
        if (last) return result
        val pending = result.substring(sent.length)
        if (pending.isBlank()) return sent
        if (heldAt == null) heldAt = now
        if (now - grewAt >= rule.pauseMs) return result.trimEnd()
        var cut = 0
        Regex("[${esc(rule.stops)}]$MARK_END").findAll(pending).forEach { cut = it.range.last + 1 }
        if (rule.clauses.isNotEmpty()) {
            Regex("[${esc(rule.clauses)}]$MARK_END").findAll(pending).forEach {
                val end = it.range.last + 1
                if (end > cut && words(pending.substring(0, end)) >= rule.minWords) cut = end
            }
        }
        if (now - (heldAt ?: now) >= rule.holdMs) {
            val spaces = Regex(" ").findAll(pending.trimEnd()).map { it.range.first }.toList()
            cut = maxOf(cut, if (spaces.size >= 3) spaces[spaces.size - 2] else 0)
        }
        return if (cut > 0) sent + pending.substring(0, cut) else sent
    }

    private fun esc(marks: String) = marks.map { "\\$it" }.joinToString("")

    private fun words(s: String) = s.split(Regex("\\s+")).count { it.isNotEmpty() }

    companion object {
        /** A mark counts when a space (or nothing yet) follows it. */
        private const val MARK_END = "(?=\\s|$)"
        /** Desktop `STREAM_RELEASE["phrase"]`: (".?!", ",;:", 4, 0.8 s, 2.5 s). */
        val PHRASE = Rule(".?!", ",;:", 4, 800L, 2_500L)
    }
}
