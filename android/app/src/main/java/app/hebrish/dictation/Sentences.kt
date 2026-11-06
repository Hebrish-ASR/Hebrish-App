package app.hebrish.dictation

private val TERMINATORS = charArrayOf('.', '?', '!', '\u2026')

/**
 * How many characters at the end of [before] make up its last sentence: the sentence, what follows
 * it, and the spaces before it, so "One. Two three." leaves "One.". A sentence starts after a
 * terminator followed by whitespace (so "3.5" is not a boundary) or after a line break, and a
 * line break before it stays, so a paragraph break survives. 0 for blank text.
 */
fun lastSentenceLength(before: String): Int {
    val end = before.trimEnd().trimEnd(*TERMINATORS).trimEnd().length
    if (end == 0) return before.length
    var i = end - 1
    while (i >= 0) {
        val c = before[i]
        if (c == '\n') return before.length - (i + 1)
        if (c.isWhitespace() && i > 0 && before[i - 1] in TERMINATORS) return before.length - i
        i--
    }
    return before.length
}
