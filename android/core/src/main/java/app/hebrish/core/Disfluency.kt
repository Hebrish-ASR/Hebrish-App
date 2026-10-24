package app.hebrish.core

import java.util.regex.Pattern

/**
 * Disfluency chop (1.001): hesitation sounds (um, uh, eh, er, hmm) removed from the model's text
 * right after decoding, always, for every model (D-2026-10-24-04). The rules are shared with
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

    /** [text] without its fillers (rules 1-4 of disfluencies.md). */
    fun chop(text: String): String {
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
}
