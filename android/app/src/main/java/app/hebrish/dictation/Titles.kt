package app.hebrish.dictation

import org.json.JSONException
import org.json.JSONObject

// No android.* here (org.json only): ported line for line from desktop/hebrish/titles.py (B-75)
// so both apps send the title model the same prompt and make the same title of its reply.
// Tests: src/test/.../TitlesTest.kt, the cases of desktop/tests/test_titles.py.

/**
 * Transcript titles (B-75a, Daniel 2026-10-31): the catalogue add-on `title-gemma-270m` (kind
 * `text_title`; gghfez/openwebui-title-generator-270m, a Gemma 3 270M fine-tune trained on Open
 * WebUI's title task), downloaded by [CleanupStore] and run in-process by [CleanupModel] like the
 * clean-up models. Writes a short title for each saved transcript ([Transcripts] puts it in the
 * file name, the front matter and the H1).
 *
 * Prompt: Open WebUI's default title prompt in Gemma's chat template, the first [INPUT_WORDS] words,
 * greedy, at most [N_PREDICT] tokens. Its reply is JSON with an emoji or two; [clean] keeps the
 * title's letters, digits and `& - ' , : + / . #`, strips quotes and a final full stop, and [fit]
 * cuts it at a word end without a dangling "and"/"&"/"the". Never blocks a save: any failure, or
 * nothing left after cleaning, gives null and the transcript is saved by its time alone.
 *
 * One difference from desktop: the phone's context is [CTX] tokens, so a prompt that would not fit
 * (1,200 words of romanized Hebrew can pass 2,000 tokens) is cut by words until it does.
 */
object Titles {
    const val KIND = "text_title"
    const val INPUT_WORDS = 1200
    const val N_PREDICT = 40
    const val TIMEOUT_MS = 60_000L
    const val MAX_CHARS = 60
    const val MIN_CHARS = 16
    const val MAX_CHARS_LIMIT = 120
    const val END = "<end_of_turn>"
    /** The phone's context for the title model: prompt plus [N_PREDICT]. */
    const val CTX = 2048

    const val PROMPT = """### Task:
Generate a concise, 3-5 word title with an emoji summarizing the chat history.
### Guidelines:
- The title should clearly represent the main theme or subject of the conversation.
- Use emojis that enhance understanding of the topic, but avoid quotation marks or special formatting.
- Write the title in the chat's primary language; default to English if multilingual.
- Prioritize accuracy over excessive creativity; keep it clear and simple.
### Output:
JSON format: { "title": "your concise title here" }
### Chat History:
<chat_history>
USER: {text}
</chat_history>"""

    private val WS = Regex("\\s+")

    private fun words(text: String) = text.split(WS).filter { it.isNotEmpty() }

    fun renderPrompt(text: String, maxWords: Int = INPUT_WORDS): String {
        val body = words(text).take(maxWords).joinToString(" ")
        return "<start_of_turn>user\n${PROMPT.replace("{text}", body)}$END\n<start_of_turn>model\n"
    }

    private const val KEEP_PUNCT = "&-'’,:+/.#"

    /** Letters, digits, spaces and a little punctuation; emojis and other symbols go. */
    private fun stripSymbols(s: String): String {
        val out = StringBuilder()
        var i = 0
        while (i < s.length) {
            val cp = s.codePointAt(i)
            i += Character.charCount(cp)
            val type = Character.getType(cp)
            when {
                Character.isLetter(cp) || type == Character.DECIMAL_DIGIT_NUMBER.toInt() ||
                    type == Character.LETTER_NUMBER.toInt() || type == Character.OTHER_NUMBER.toInt() ||
                    (cp < 0x10000 && cp.toChar() in KEEP_PUNCT) -> out.appendCodePoint(cp)
                type == Character.SPACE_SEPARATOR.toInt() || type == Character.LINE_SEPARATOR.toInt() ||
                    type == Character.PARAGRAPH_SEPARATOR.toInt() || cp == '\t'.code || cp == '\n'.code -> out.append(' ')
                // symbols, emojis, zero-width joiners, variation selectors, other punctuation: dropped
            }
        }
        return out.toString()
    }

    private val DANGLING = setOf("&", "and", "-", "or", "of", "the", "a", "for", "with", "to")

    /** [title] cut to at most [maxChars] at a word end, without a dangling joiner. */
    fun fit(title: String, maxChars: Int = MAX_CHARS): String {
        var t = words(title).joinToString(" ")
        if (t.length > maxChars) {
            val cut = t.take(maxChars + 1)
            t = if (' ' in cut) cut.substring(0, cut.lastIndexOf(' ')) else t.take(maxChars)
        }
        val ws = words(t).toMutableList()
        while (ws.isNotEmpty() && (ws.last().lowercase() in DANGLING || ws.last().none { it.isLetterOrDigit() })) ws.removeAt(ws.size - 1)
        return ws.joinToString(" ").trimEnd(',', ':', '-', '/', ' ')
    }

    private val FENCE = Regex("^```(?:json)?|```$")
    private val OBJECT = Regex("\\{.*\\}", RegexOption.DOT_MATCHES_ALL)
    private val TITLE_FIELD = Regex("\"title\"\\s*:\\s*\"([^\"]*)")

    /** The model's reply as a plain title, "" when nothing usable is left. */
    fun clean(reply: String, maxChars: Int = MAX_CHARS): String {
        var raw = reply.replace(END, "").trim()
        raw = raw.replace(FENCE, "").trim()
        var text: String? = null
        val m = OBJECT.find(raw)
        if (m != null) {
            text = try {
                JSONObject(m.value).opt("title") as? String
            } catch (_: JSONException) {
                TITLE_FIELD.find(raw)?.groupValues?.get(1)
            }
        }
        if (text == null && "\"title\"" in raw) text = TITLE_FIELD.find(raw)?.groupValues?.get(1)   // cut off before the closing quote or brace
        if (text == null) text = if (raw.isEmpty()) "" else raw.lines()[0]
        val t = words(stripSymbols(text)).joinToString(" ").trim(' ', '\'', '’', '"', '“', '”').trimEnd('.')
        if (t.none { it.isLetter() }) return ""
        return fit(t, maxChars)
    }

    /** A title limit kept in [MIN_CHARS]..[MAX_CHARS_LIMIT]. */
    fun limit(v: Int): Int = v.coerceIn(MIN_CHARS, MAX_CHARS_LIMIT)

    /**
     * A title for [text] from [client] (a [CleanupModel] on the title file, or a fake). Null on any
     * failure or an empty result. The prompt is cut by words until it fits [ctx] with [N_PREDICT].
     */
    fun make(text: String, client: Cleanup.Client, maxChars: Int = MAX_CHARS, ctx: Int = CTX): String? {
        if (text.isBlank()) return null
        return try {
            var n = INPUT_WORDS
            var prompt = renderPrompt(text, n)
            while (client.count(prompt) + N_PREDICT > ctx && n > 50) {
                n = n * 3 / 4
                prompt = renderPrompt(text, n)
            }
            clean(client.complete(prompt, N_PREDICT, TIMEOUT_MS).first, maxChars).ifEmpty { null }
        } catch (_: Exception) {
            null
        }
    }
}
