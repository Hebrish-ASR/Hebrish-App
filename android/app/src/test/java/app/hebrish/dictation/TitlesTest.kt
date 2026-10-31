package app.hebrish.dictation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** [Titles] against the cases of desktop/tests/test_titles.py (B-75), so both apps make the same title. */
class TitlesTest {
    @Test fun cleanJsonAndEmojis() {
        assertEquals("Milk & Shufersal Order", Titles.clean("{\"title\": \"🥛 Milk & Shufersal Order\"}"))
        assertEquals("Vaad Bayit Elevator Repair", Titles.clean("{\"title\": \"Vaad Bayit Elevator Repair 🛠️\"}"))
        assertEquals("Podcast Development & AI", Titles.clean("```json\n{ \"title\": \"🎙️ Podcast Development & AI\" }\n```"))
    }

    @Test fun cleanPlainAndBroken() {
        assertEquals("Hebrish release notes", Titles.clean("\"Hebrish release notes.\""))
        assertEquals("Half a tit", Titles.clean("{\"title\": \"Half a tit"))
        assertEquals("", Titles.clean("{\"title\": \"🤖🤖\"}"))
        assertEquals("", Titles.clean(""))
    }

    @Test fun fit() {
        val t = Titles.fit("Notes on the Hebrish release and the Android floating mic", 30)
        assertTrue(t.length <= 30)
        assertEquals("Notes on the Hebrish release", t)
        assertEquals("Elevator repairs", Titles.fit("Elevator repairs & arnona", 20))
        assertEquals(Titles.MIN_CHARS, Titles.limit(3))
        assertEquals(120, Titles.limit(500))
    }

    private class Fake(val reply: String? = null, val fail: Boolean = false, val tokens: (String) -> Int = { 0 }) : Cleanup.Client {
        var prompt: String? = null
        override fun count(text: String) = tokens(text)
        override fun complete(prompt: String, nPredict: Int, timeoutMs: Long): Pair<String, Boolean> {
            this.prompt = prompt
            if (fail) throw java.io.IOException("slow")
            return reply!! to false
        }
    }

    private fun promptWords(p: String) = p.split("USER: ")[1].split("\n")[0].split(" ").size

    @Test fun make() {
        val f = Fake("{\"title\": \"🛒 Makolet Shopping List\"}")
        assertEquals("Makolet Shopping List", Titles.make("word ".repeat(5000), f, 60))
        val p = f.prompt!!
        assertTrue(p.startsWith("<start_of_turn>user\n### Task:") && p.endsWith("<start_of_turn>model\n"))
        assertEquals(Titles.INPUT_WORDS, promptWords(p))
        assertNull(Titles.make("text", Fake(fail = true)))
        assertNull(Titles.make("text", Fake("{\"title\": \"✨\"}")))
        assertNull(Titles.make("  ", Fake("x")))
    }

    /** Android only: a prompt too long for the phone's context is cut by words until it fits. */
    @Test fun makeFitsTheContext() {
        val f = Fake("{\"title\": \"Long Note\"}", tokens = { it.split(" ").size * 2 })
        assertEquals("Long Note", Titles.make("word ".repeat(5000), f, 60))
        val n = promptWords(f.prompt!!)
        assertTrue(n < Titles.INPUT_WORDS && f.prompt!!.split(" ").size * 2 + Titles.N_PREDICT <= Titles.CTX)
    }
}
