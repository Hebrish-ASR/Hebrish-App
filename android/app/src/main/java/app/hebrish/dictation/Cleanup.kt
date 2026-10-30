package app.hebrish.dictation

// No android.* here: the clean-up logic, ported line for line from desktop/hebrish/cleanup.py
// (B-40) so both apps send the model the same prompt and keep the same text when it fails.
// The model itself is [CleanupModel]; its files are [CleanupStore].

/**
 * Dictation clean-up (B-40a): S1-ASR-Cleanup, a fine-tune of S1-mini by Superwhisper, run once on
 * a finished Transcription Mode take when the user has downloaded it and turned it on.
 *
 * The licence (Apache 2.0 plus a naming term) requires that wherever the app names or describes
 * the model it is identified as "S1-mini" by "Superwhisper", exact capitalisation.
 *
 * Prompt: exactly as the model was trained (ASR-Post-Processor-Model training/s1mini_lora.py,
 * `render_prompt(text, "1,2")`). Greedy, n_predict = 1.3 x input tokens + 32. Never loses text: a
 * chunk whose output is empty, cut off, timed out, failed, or dropped a personal-dictionary word
 * keeps its raw text ([accept]).
 *
 * One difference from desktop: chunks are at most [MAX_INPUT_TOKENS] = 600 tokens, not 900, so
 * the whole exchange fits [CTX] = 1,536 and the KV cache stays near 170 MB on a phone (desktop:
 * 4,096, about 470 MB). Chunks are cut at sentence ends either way.
 */
object Cleanup {
    const val SYSTEM_PROMPT =
        "You are a text normalizer for speech-to-text transcripts. The input begins " +
        "with a control line specifying the styling, structure, and context settings; " +
        "clean the transcript to match those settings and output only the cleaned text."
    const val CONTROL_LINE = "[Styling: semi-formal] [Structure: prose] [Context: general] [Layers: 1,2]"
    const val ASSISTANT_PREFIX = "<|im_start|>assistant\n<think>\n\n</think>\n\n"
    const val END_OF_TURN = "<|im_end|>"

    const val MAX_INPUT_TOKENS = 600
    const val CTX = 1536

    /** What the app's model needs: token count, and a greedy completion returning (content, cut off at n_predict). */
    interface Client {
        fun count(text: String): Int
        fun complete(prompt: String, nPredict: Int, timeoutMs: Long): Pair<String, Boolean>
    }

    data class Result(val text: String, val chunks: Int, val keptRaw: Int, val error: String = "") {
        /** At least one chunk was cleaned. */
        val cleaned get() = chunks > keptRaw
    }

    /** The full prompt up to and including the assistant prefix, byte-identical to s1mini_lora.render_prompt(transcript, "1,2"). */
    fun renderPrompt(transcript: String) =
        "<|im_start|>system\n$SYSTEM_PROMPT$END_OF_TURN\n" +
        "<|im_start|>user\n$CONTROL_LINE\n$transcript$END_OF_TURN\n" +
        ASSISTANT_PREFIX

    /** The output ceiling the S1-mini card recommends: 1.3 x input tokens + 32. */
    fun maxTokens(inputTokens: Int) = (1.3 * inputTokens).toInt() + 32

    /** Milliseconds one chunk may take: generous for a slow phone (~5 tokens/s), then give up. */
    fun timeoutFor(nPredict: Int): Long = 45_000L + nPredict * 200L

    private val SENTENCE = Regex("(?<=[.!?…])\\s+|\\n\\s*\\n")

    fun sentences(text: String) = text.split(SENTENCE).map { it.trim() }.filter { it.isNotEmpty() }

    /** [text] as chunks of whole sentences of at most [limit] tokens each; a single longer sentence is a chunk of its own. */
    fun splitChunks(text: String, count: (String) -> Int, limit: Int = MAX_INPUT_TOKENS): List<String> {
        val t = text.trim()
        if (t.isEmpty()) return emptyList()
        if (count(t) <= limit) return listOf(t)
        val out = ArrayList<String>()
        val cur = ArrayList<String>()
        var have = 0
        for (s in sentences(t)) {
            val n = count(s) + 1
            if (cur.isNotEmpty() && have + n > limit) {
                out.add(cur.joinToString(" "))
                cur.clear()
                have = 0
            }
            cur.add(s)
            have += n
        }
        if (cur.isNotEmpty()) out.add(cur.joinToString(" "))
        return out
    }

    /** [word] in [text] as a whole word: exact case for a word with a capital, any case otherwise. */
    fun has(text: String, word: String): Boolean {
        val pat = word.trim().split(Regex("\\s+")).joinToString("\\s+") { Regex.escape(it) }
        val opts = if (word != word.lowercase()) emptySet() else setOf(RegexOption.IGNORE_CASE)
        return Regex("(?U)(?<!\\w)$pat(?!\\w)", opts).containsMatchIn(text)
    }

    /** Whether [out] may replace [raw]: not empty, not cut off, and every [keep] word in [raw] still in [out]. */
    fun accept(raw: String, out: String, cutOff: Boolean, keep: List<String> = emptyList()): Boolean {
        if (out.isBlank() && raw.isNotBlank()) return false
        if (cutOff) return false
        return keep.filter { has(raw, it) }.all { has(out, it) }
    }

    /** The model's reply as text: end-of-turn and any think block removed, paragraphs one blank line apart. */
    fun tidy(out: String): String {
        val s = out.replace(END_OF_TURN, "").replace(Regex("<think>.*?</think>", RegexOption.DOT_MATCHES_ALL), "")
        return s.split(Regex("\\n\\s*\\n"))
            .map { it.split(Regex("\\s+")).filter { w -> w.isNotEmpty() }.joinToString(" ") }
            .filter { it.isNotEmpty() }
            .joinToString("\n\n")
    }

    /** Cleans [text] with [client], chunk by chunk, joined with a paragraph break; any failure keeps that chunk's raw text. */
    fun clean(text: String, client: Client, keep: List<String> = emptyList()): Result {
        val raw = text.trim()
        if (raw.isEmpty()) return Result(text, 0, 0)
        val chunks = try {
            splitChunks(raw, client::count)
        } catch (e: Exception) {
            return Result(text, 1, 1, e.message ?: e.javaClass.simpleName)
        }
        val out = ArrayList<String>()
        var kept = 0
        var first = ""
        for (chunk in chunks) {
            val why = try {
                val n = maxTokens(client.count(chunk))
                val (content, cutOff) = client.complete(renderPrompt(chunk), n, timeoutFor(n))
                val got = tidy(content)
                if (accept(chunk, got, cutOff, keep)) { out.add(got); continue }
                if (cutOff) "cut off" else if (got.isEmpty()) "empty reply" else "changed a dictionary word"
            } catch (e: Exception) {
                e.message ?: e.javaClass.simpleName
            }
            kept++
            if (first.isEmpty()) first = why
            out.add(chunk)
        }
        return Result(out.joinToString("\n\n"), chunks.size, kept, first)
    }
}
