package app.hebrish.dictation

import java.io.File
import java.text.Normalizer

/**
 * Paragraph breaks for Transcription Mode's *Paragraph model* setting (B-44a, D-2026-10-24-09).
 * The one spec, shared with desktop B-44: `shared/paragraphs.md`; test file
 * `shared/paragraph-cases.json`, checked on the JVM by `android/scripts/check_paragraphs.sh`.
 *
 * Plain JVM code on purpose (no `android.*`, no ONNX Runtime), so the check script compiles this
 * file as it is. The model runs in [ParagraphModel] (`ParagraphModel.kt`).
 *
 * The output only ever differs from the input in whitespace: the words joined by a space, or by a
 * blank line before a word the model scores at or above the threshold.
 */
object Paragraphs {
    /** Content tokens per window ([CLS] and [SEP] come on top) and the step between windows. */
    const val MAX_TOKENS = 510
    const val STRIDE = 256

    /**
     * Python's `str.split()`: runs of characters for which `str.isspace()` is true (bidi class
     * WS/B/S or category Zs). Not Java's `Character.isWhitespace`, which leaves out no-break spaces.
     */
    fun isSpace(cp: Int): Boolean = when (cp) {
        in 0x09..0x0D, in 0x1C..0x20, 0x85, 0xA0, 0x1680, in 0x2000..0x200A,
        0x2028, 0x2029, 0x202F, 0x205F, 0x3000 -> true
        else -> false
    }

    fun words(text: String): List<String> {
        val out = ArrayList<String>()
        var i = 0
        var start = -1
        while (i < text.length) {
            val cp = text.codePointAt(i)
            if (isSpace(cp)) {
                if (start >= 0) { out.add(text.substring(start, i)); start = -1 }
            } else if (start < 0) start = i
            i += Character.charCount(cp)
        }
        if (start >= 0) out.add(text.substring(start))
        return out
    }

    /**
     * `(first_word, end_word)` spans of at most [MAX_TOKENS] tokens, cut at word boundaries, the
     * next starting [STRIDE] tokens on (`windows()` in the reference `paragraphs.py`).
     */
    fun windows(pieces: List<IntArray>): List<IntArray> {
        val n = pieces.size
        if (n == 0) return emptyList()
        val starts = IntArray(n + 1)
        for (i in 0 until n) starts[i + 1] = starts[i] + pieces[i].size
        val out = ArrayList<IntArray>()
        var w0 = 0
        while (true) {
            var w1 = w0
            while (w1 < n && starts[w1 + 1] - starts[w0] <= MAX_TOKENS) w1++
            w1 = maxOf(w1, w0 + 1)
            out.add(intArrayOf(w0, w1))
            if (w1 >= n) return out
            var nxt = w0 + 1
            while (nxt < n && starts[nxt] < starts[w0] + STRIDE) nxt++
            w0 = maxOf(w0 + 1, minOf(nxt, w1))
        }
    }

    /**
     * P(a paragraph starts at word i) for every word; word 0 is always 0. [logits] runs one window
     * (`[CLS] pieces… [SEP]`) and returns its logits flattened, `[seq, 2]`. A word covered by
     * several windows takes the window where its first sub-token is closest to the middle; on a
     * tie, the earlier window.
     */
    fun probs(pieces: List<IntArray>, logits: (LongArray) -> FloatArray): DoubleArray {
        val n = pieces.size
        val best = DoubleArray(n)
        val centre = DoubleArray(n) { Double.NEGATIVE_INFINITY }
        for (w in windows(pieces)) {
            val len = 2 + (w[0] until w[1]).sumOf { pieces[it].size }
            val ids = LongArray(len)
            val pos = IntArray(w[1] - w[0])
            ids[0] = WordPiece.CLS.toLong()
            var k = 1
            for (j in w[0] until w[1]) {
                pos[j - w[0]] = k
                for (id in pieces[j]) ids[k++] = id.toLong()
            }
            ids[k] = WordPiece.SEP.toLong()
            val l = logits(ids)
            require(l.size == len * 2) { "logits: ${l.size} values for $len tokens" }
            val mid = (len - 1) / 2.0
            for (j in w[0] until w[1]) {
                val p = pos[j - w[0]]
                val c = -Math.abs(p - mid)
                if (c > centre[j]) {
                    centre[j] = c
                    val a = l[2 * p].toDouble()
                    val b = l[2 * p + 1].toDouble()
                    val m = maxOf(a, b)
                    val ea = Math.exp(a - m)
                    val eb = Math.exp(b - m)
                    best[j] = eb / (ea + eb)
                }
            }
        }
        if (n > 0) best[0] = 0.0
        return best
    }

    /** The words joined: "\n\n" before every word after the first whose score is >= [threshold], else " ". */
    fun join(words: List<String>, probs: DoubleArray, threshold: Double): String {
        val sb = StringBuilder()
        for ((i, w) in words.withIndex()) {
            if (i > 0) sb.append(if (probs[i] >= threshold) "\n\n" else " ")
            sb.append(w)
        }
        return sb.toString()
    }

    /** True when [a] and [b] hold the same words in the same order (they differ only in whitespace). */
    fun sameWords(a: String, b: String) = words(a) == words(b)
}

/**
 * BERT uncased WordPiece, the model's `tokenizer.json` (`BertNormalizer{clean_text,
 * handle_chinese_chars, lowercase}` + `BertPreTokenizer` + `WordPiece{"##", 100, [UNK]}`) as the
 * HF `tokenizers` library runs it, one whitespace word at a time, no special tokens added.
 * `vocab.txt`: line n (from 0) is id n.
 */
class WordPiece(private val vocab: Map<String, Int>) {
    /** The word's ids; [UNK] alone when it gives none (it was only control characters). */
    fun word(w: String): IntArray {
        val ids = ArrayList<Int>()
        // Added (special) tokens are matched in the raw text before normalisation, as HF does.
        var i = 0
        var from = 0
        while (i < w.length) {
            val tok = SPECIAL.firstOrNull { w.startsWith(it, i) }
            if (tok != null) {
                segment(w.substring(from, i), ids)
                ids.add(vocab[tok] ?: UNK)
                i += tok.length
                from = i
            } else i++
        }
        segment(w.substring(from), ids)
        return if (ids.isEmpty()) intArrayOf(UNK) else ids.toIntArray()
    }

    private fun segment(s: String, out: MutableList<Int>) {
        if (s.isEmpty()) return
        for (piece in preTokenize(normalize(s))) out.addAll(wordPiece(piece))
    }

    private fun wordPiece(piece: String): List<Int> {
        val cps = piece.codePoints().toArray()
        if (cps.size > MAX_CHARS) return listOf(UNK)
        val out = ArrayList<Int>()
        var start = 0
        while (start < cps.size) {
            var end = cps.size
            var found: Int? = null
            while (start < end) {
                val sub = String(cps, start, end - start)
                val id = vocab[if (start > 0) "##$sub" else sub]
                if (id != null) { found = id; break }
                end--
            }
            if (found == null) return listOf(UNK)
            out.add(found)
            start = end
        }
        return out
    }

    companion object {
        const val PAD = 0
        const val UNK = 100
        const val CLS = 101
        const val SEP = 102
        const val MAX_CHARS = 100
        private val SPECIAL = listOf("[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]")

        fun load(f: File): WordPiece {
            val m = HashMap<String, Int>(40_000)
            f.bufferedReader(Charsets.UTF_8).useLines { lines -> lines.forEachIndexed { i, l -> m.putIfAbsent(l.trimEnd('\r'), i) } }
            return WordPiece(m)
        }

        /** Rust `char::is_whitespace` (White_Space), plus tab, LF and CR. */
        private fun isWs(cp: Int) = when (cp) {
            in 0x09..0x0D, 0x20, 0x85, 0xA0, 0x1680, in 0x2000..0x200A, 0x2028, 0x2029, 0x202F, 0x205F, 0x3000 -> true
            else -> false
        }

        /**
         * HF's `is_control`: categories Cc, Cf, Co and Cs, except tab, LF and CR. Unassigned code
         * points (Cn) are kept, as `tokenizers` keeps them (checked: U+0378 gives [UNK]).
         */
        private fun isControl(cp: Int): Boolean {
            if (cp == 0x09 || cp == 0x0A || cp == 0x0D) return false
            return when (Character.getType(cp).toByte()) {
                Character.CONTROL, Character.FORMAT, Character.PRIVATE_USE, Character.SURROGATE -> true
                else -> false
            }
        }

        /** BERT's `_is_chinese_char` ranges. */
        private fun isCjk(cp: Int) = cp in 0x4E00..0x9FFF || cp in 0x3400..0x4DBF || cp in 0x20000..0x2A6DF ||
            cp in 0x2A700..0x2B73F || cp in 0x2B740..0x2B81F || cp in 0x2B920..0x2CEAF ||
            cp in 0xF900..0xFAFF || cp in 0x2F800..0x2FA1F

        /** ASCII 33–47, 58–64, 91–96, 123–126, or Unicode P*. Symbols (₪, €, emoji) are not punctuation. */
        fun isPunct(cp: Int): Boolean {
            if (cp in 33..47 || cp in 58..64 || cp in 91..96 || cp in 123..126) return true
            return when (Character.getType(cp).toByte()) {
                Character.CONNECTOR_PUNCTUATION, Character.DASH_PUNCTUATION, Character.START_PUNCTUATION,
                Character.END_PUNCTUATION, Character.INITIAL_QUOTE_PUNCTUATION, Character.FINAL_QUOTE_PUNCTUATION,
                Character.OTHER_PUNCTUATION -> true
                else -> false
            }
        }

        /**
         * BertNormalizer in HF's order: clean (drop NUL, U+FFFD, controls; whitespace to a space),
         * space out CJK ideographs, strip accents (NFD, drop Mn), lower-case per character.
         */
        fun normalize(s: String): String {
            val a = StringBuilder(s.length + 8)
            var i = 0
            while (i < s.length) {
                val cp = s.codePointAt(i)
                i += Character.charCount(cp)
                if (cp == 0 || cp == 0xFFFD || isControl(cp)) continue
                when {
                    isWs(cp) -> a.append(' ')
                    isCjk(cp) -> a.append(' ').appendCodePoint(cp).append(' ')
                    else -> a.appendCodePoint(cp)
                }
            }
            val nfd = Normalizer.normalize(a, Normalizer.Form.NFD)
            val b = StringBuilder(nfd.length)
            i = 0
            while (i < nfd.length) {
                val cp = nfd.codePointAt(i)
                i += Character.charCount(cp)
                if (Character.getType(cp).toByte() == Character.NON_SPACING_MARK) continue
                b.appendCodePoint(Character.toLowerCase(cp))
            }
            return b.toString()
        }

        /** BertPreTokenizer: split on whitespace, every punctuation character its own piece. */
        fun preTokenize(s: String): List<String> {
            val out = ArrayList<String>()
            val cur = StringBuilder()
            var i = 0
            while (i < s.length) {
                val cp = s.codePointAt(i)
                i += Character.charCount(cp)
                when {
                    isWs(cp) -> if (cur.isNotEmpty()) { out.add(cur.toString()); cur.setLength(0) }
                    isPunct(cp) -> {
                        if (cur.isNotEmpty()) { out.add(cur.toString()); cur.setLength(0) }
                        out.add(String(Character.toChars(cp)))
                    }
                    else -> cur.appendCodePoint(cp)
                }
            }
            if (cur.isNotEmpty()) out.add(cur.toString())
            return out
        }
    }
}
