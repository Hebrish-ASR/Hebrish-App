package app.hebrish.dictation

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDateTime
import java.time.ZoneId

/** [Transcripts] against desktop/tests/test_transcripts.py (B-74, B-78): the same names and file format. */
class TranscriptsTest {
    private val zone = ZoneId.of("Asia/Jerusalem")
    private val whenMs = LocalDateTime.of(2026, 10, 31, 14, 5, 9).atZone(zone).toInstant().toEpochMilli()

    @Test fun layoutAndName() {
        assertEquals(listOf("2026", "10", "31"), Transcripts.day(whenMs, zone))
        assertEquals("14-05-09", Transcripts.stem(whenMs, null, zone) { false })
        assertEquals("notes_on_the_api_v2_14-05-09", Transcripts.stem(whenMs, "Notes on the API, v2!", zone) { false })
    }

    @Test fun slug() {
        assertEquals("ani_holekh_la_makolet", Transcripts.slug("  Ani holekh la-makolet "))
        assertEquals("cafe_deja_vu", Transcripts.slug("Café déjà vu"))
        assertEquals("", Transcripts.slug("!!!"))
        val long = Transcripts.slug("word ".repeat(40))
        assertTrue(long.length <= Transcripts.SLUG_MAX && !long.endsWith("_"))
    }

    @Test fun noOverwrite() {
        val taken = setOf("14-05-09.md", "14-05-09-2.json")
        assertEquals("14-05-09-3", Transcripts.stem(whenMs, null, zone) { it in taken })
    }

    @Test fun withTitle() {
        val meta = linkedMapOf<String, Any?>("generator" to "Hebrish 1.014", "model" to "Sabich v2.3", "audio_seconds" to 12.34, "source" to "recording")
        val files = Transcripts.files("shopping_list_14-05-09", "body text", null, "Shopping list", whenMs, meta, whenMs, zone)
        assertEquals(listOf("shopping_list_14-05-09.md", "shopping_list_14-05-09.json"), files.map { it.first })
        val (fm, rest) = files[0].second.split("\n---\n\n", limit = 2)
        assertTrue(fm.startsWith("---\ntitle: \"Shopping list\"\ndate: 2026-10-31T14:05:09+02:00\nversion: transcript\n"))
        assertTrue("model: \"Sabich v2.3\"" in fm && "audio_seconds: 12.3" in fm)
        assertTrue("versions: \"shopping_list_14-05-09.json\"" in fm)
        assertEquals("# Shopping list\n\n## Saturday 31 October 2026, 14:05\n\n" +
            "*Transcribed by Hebrish 1.014 with Sabich v2.3 on 31 October 2026.*\n\nbody text\n", rest)
    }

    @Test fun untitled() {
        val md = Transcripts.render("x", null, whenMs, zone = zone)
        assertTrue("\n# Transcript\n" in md && "title:" !in md)
        assertTrue(md.endsWith("*Transcribed by Hebrish on 31 October 2026.*\n\nx\n"))
    }

    @Test fun rawVersionAndManifest() {
        val files = Transcripts.files("t_14-05-09", "Edited text.", "edited text", "T", whenMs, emptyMap(), whenMs, zone)
        assertEquals(listOf("t_14-05-09.md", "t_14-05-09.raw.md", "t_14-05-09.json"), files.map { it.first })
        assertTrue(files[1].second.endsWith("*\n\nedited text\n") && "version: raw" in files[1].second)
        val doc = JSONObject(files[2].second)
        assertEquals(1, doc.getInt("schema"))
        assertEquals("raw", doc.getJSONArray("versions").getJSONObject(1).getString("kind"))
        // Whitespace alone is not a different version.
        assertFalse(Transcripts.rawDiffers(" Same ", "Same"))
        assertEquals(2, Transcripts.files("s", "Same", " Same ", null, whenMs, emptyMap(), whenMs, zone).size)
    }

    @Test fun yamlAndQuote() {
        assertEquals("\"a \\\"b\\\" c\"", Transcripts.yaml("a \"b\" c"))
        assertEquals("120.0", Transcripts.yaml(120.0))
        assertEquals("true", Transcripts.yaml(true))
    }
}
