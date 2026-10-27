package app.hebrish.core

import java.util.regex.Pattern

/**
 * Disfluency chop (1.001): hesitation sounds (um, uh, eh, er, hmm) removed from the model's text
 * right after decoding, always, for every model (D-2026-10-24-04); from 1.007 also repeated words
 * and phrases (stutters, false starts) and the ellipses the models write for a trailing-off thought. The rules are shared with
 * desktop: ../shared/disfluencies.md, test set ../shared/disfluency-cases.json
 * (scripts/check_disfluency.sh runs it on the JVM).
 */
object Disfluency {
    private const val NEXT = "[\\p{L}\\p{N}_'’-]"   // a letter, digit, apostrophe or hyphen beside it: part of a longer word
    private val FILLER = Pattern.compile("([ \\t]*)(?<!$NEXT)(u+h+m*|u+m+|e+h+m*|er|e+r+m+|h+m+)(?!$NEXT)([,;]?)",
        Pattern.CASE_INSENSITIVE or Pattern.UNICODE_CASE)
    private val SENTENCE_START = Pattern.compile("(?:^|[.!?])\\s*$")
    private val AFTER_START = Pattern.compile("[,;.…!?]*\\s*")
    private val CAP_NEXT = Regex("\u0000([^\\p{L}\\p{N}_]*?)(\\p{L})")
    private const val CAP = '\u0000'                 // marks "capitalise the next letter" while the text is rebuilt

    /**
     * [text] without its fillers (rules 1-4 of disfluencies.md), repeated words and phrases
     * (rules 5-7) and ellipses (rule 8). [before]: the take's text already out, for a repeat
     * across the seam.
     */
    fun chop(text: String, before: String = ""): String = ellipses(phrases(repeats(fillers(text), before)))

    private fun fillers(text: String): String {
        val out = StringBuilder()
        var pos = 0
        var changed = false
        val m = FILLER.matcher(text)
        while (pos <= text.length && m.find(pos)) {
            val word = m.group(2)!!
            if (word.length > 1 && word == word.uppercase()) {   // ER, UM in capitals: an abbreviation
                out.append(text, pos, m.end())
                pos = m.end()
                continue
            }
            changed = true
            out.append(text, pos, m.start())
            pos = m.end()
            if (SENTENCE_START.matcher(out.toString().replace(CAP.toString(), "")).find()) {   // rule 2
                out.append(m.group(1))
                val after = AFTER_START.matcher(text)
                if (after.find(pos) && after.start() == pos) pos = after.end()
            }
            if (word[0].isUpperCase()) out.append(CAP)                                         // rule 3
        }
        if (!changed) return text
        out.append(text, pos, text.length)
        var result = CAP_NEXT.replace(out) { it.groupValues[1] + it.groupValues[2].uppercase() }
        result = result.replace(CAP.toString(), "")
        result = result.replace(Regex(",\\s*([.!?])"), "$1")                                    // rule 4
        result = result.replace(Regex("[ \\t]+([,.!?;:])"), "$1")
        return if (Regex("[\\p{L}\\p{N}]").containsMatchIn(result)) result else ""
    }

    // Repeated words (1.007, Daniel 2026-10-27). A word said twice on purpose is kept twice when it
    // is one of these; numbers are never cut ("five five five" is a phone number).
    private val KEEP_TWICE = ("really very so no yes yeah bye ha haha much more many far long ever again had that " +
        "is was do did now well there too round around over out on off up down go come knock hey okay ok " +
        "please quick slowly bit little away tov ken lo yalla nu dai kol od").split(" ").toSet()
    private val NUMBERS = "zero oh one two three four five six seven eight nine ten double triple".split(" ").toSet()
    private val WORD = Regex("[\\p{L}\\p{N}]+(?:['’-][\\p{L}\\p{N}]+)*")
    private val SOFT_GAP = Regex("[ \\t]*(?:[,;]|…|\\.{3,})?[ \\t]*")
    private val MARK_GAP = Regex("[ \\t]*[.?!][ \\t]+")
    private val ELLIPSIS = Regex("[ \\t]*(?:…|\\.{3,})([ \\t]*)")

    private fun fold(w: String) = w.lowercase()
    private fun isNumber(w: String) = fold(w) in NUMBERS || w.any { it.isDigit() }
    private fun twiceOk(w: String) = fold(w) in KEEP_TWICE || isNumber(w)
    private fun joins(gap: String, next: String) =
        SOFT_GAP.matches(gap) || (MARK_GAP.matches(gap) && next[0].isLowerCase())

    /** Rules 5-6: a run of one word cut to one (two for KEEP_TWICE); a repeat across the seam dropped. */
    private fun repeats(text: String, before: String): String {
        var words = WORD.findAll(text).toList()
        if (words.isEmpty()) return text
        val cut = mutableListOf<Pair<Int, Int>>()
        if (before.isNotEmpty()) {
            val prev = WORD.findAll(before).lastOrNull()
            if (prev != null && before.substring(prev.range.last + 1).trim(' ', '\t', ',', ';').isEmpty() &&
                fold(prev.value) == fold(words[0].value) && !twiceOk(words[0].value)) {
                cut.add(words[0].range.first to (if (words.size > 1) words[1].range.first else text.length))
                words = words.drop(1)
            }
        }
        var i = 0
        while (i < words.size) {
            var j = i
            while (j + 1 < words.size && fold(words[j].value) == fold(words[j + 1].value) &&
                joins(text.substring(words[j].range.last + 1, words[j + 1].range.first), words[j + 1].value)) j++
            val n = j - i + 1
            val w = words[i].value
            if (n >= 2 && !isNumber(w)) {
                val keep = if (twiceOk(w)) 2 else 1
                if (n > keep) cut.add(words[i + keep - 1].range.last + 1 to words[j].range.last + 1)
            }
            i = j + 1
        }
        if (cut.isEmpty()) return text
        val out = StringBuilder()
        var pos = 0
        for ((a, b) in cut) { out.append(text, pos, a); pos = b }
        out.append(text, pos, text.length)
        return out.toString()
    }

    /** Rule 7: a two- or three-word phrase said again straight away is a false start. */
    private fun phrases(input: String): String {
        var text = input
        for (k in intArrayOf(3, 2)) {
            while (true) {
                val words = WORD.findAll(text).toList()
                var changed = false
                for (i in 0..words.size - 2 * k) {
                    val one = words.subList(i, i + k)
                    val two = words.subList(i + k, i + 2 * k)
                    if (one.map { fold(it.value) } != two.map { fold(it.value) }) continue
                    if (one.all { isNumber(it.value) }) continue
                    if (joins(text.substring(one.last().range.last + 1, two.first().range.first), two.first().value)) {
                        text = text.substring(0, one.last().range.last + 1) + text.substring(two.last().range.last + 1)
                        changed = true
                        break
                    }
                }
                if (!changed) break
            }
        }
        return text
    }

    /** Rule 8: an ellipsis is a thought trailing off: a space before lower case, else a full stop. */
    private fun ellipses(text: String): String {
        if ('…' !in text && "..." !in text) return text
        return ELLIPSIS.replace(text) { m ->
            val next = text.getOrNull(m.range.last + 1)
            when {
                next != null && (next.isLowerCase() || next.isDigit()) -> " "
                next != null && next in ".?!,;:" -> ""
                else -> "." + m.groupValues[1]
            }
        }
    }
}
