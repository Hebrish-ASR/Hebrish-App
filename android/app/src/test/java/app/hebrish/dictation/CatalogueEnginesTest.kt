package app.hebrish.dictation

import app.hebrish.core.Catalogue
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Which catalogue variants this build runs (B-13, 2026-11-17): the streaming engine is supported for
 * dictation models too (Shakshuka), not only for language models (the Hebrew line).
 */
class CatalogueEnginesTest {
    private fun variant(id: String, engine: String, platforms: String = "\"android\"", language: String? = null, status: String = "available") = """
        {"id": "$id", "name": "$id", "engine": "$engine", "status": "$status", "platforms": [$platforms],
         ${if (language != null) "\"language\": \"$language\"," else ""}
         "manifest_url": "https://cdn.example/models/$id/latest.json"}"""

    private fun catalogue(vararg variants: String) = Catalogue.parse("""
        {"schema": 2, "recommended": "sabich",
         "engines": {"sherpa_offline_transducer": {"files": ["encoder.int8.onnx"]}},
         "lines": [{"id": "all", "name": "All", "variants": [${variants.joinToString(",")}]}]}""")!!

    private fun model(data: Catalogue.Data, id: String) = data.lines.flatMap { it.variants }.first { it.id == id }

    @Test fun streamingDictationModelIsSupportedOnAndroid() {
        val data = catalogue(
            variant("sabich", "sherpa_offline_transducer"),
            variant("shakshuka", "sherpa_online_transducer"),
        )
        val shakshuka = model(data, "shakshuka")
        assertTrue(shakshuka.supported)
        assertTrue(shakshuka.streaming)
        assertTrue(shakshuka.available)
        assertTrue(data.models.any { it.id == "shakshuka" })
        assertFalse(model(data, "sabich").streaming)
        assertEquals("sabich", data.recommended)
    }

    @Test fun streamingLanguageModelStaysSupported() {
        val data = catalogue(
            variant("sabich", "sherpa_offline_transducer"),
            variant("hebrew", "sherpa_online_transducer", language = "he"),
        )
        assertTrue(model(data, "hebrew").supported)
        assertTrue(model(data, "hebrew").streaming)
    }

    @Test fun desktopOnlyOrOtherEnginesAreNot() {
        val data = catalogue(
            variant("sabich", "sherpa_offline_transducer"),
            variant("shakshuka", "sherpa_online_transducer", platforms = "\"linux\", \"windows\""),
            variant("qwen", "qwen3_asr"),
        )
        assertFalse(model(data, "shakshuka").supported)
        assertFalse(model(data, "qwen").supported)
        assertEquals(listOf("sabich"), data.models.map { it.id })
    }

    @Test fun aStreamingModelAloneIsAValidCatalogue() {
        // parse needs one available dictation model; a streaming one now counts.
        val data = catalogue(variant("shakshuka", "sherpa_online_transducer"))
        assertEquals("sabich", data.recommended)        // what the catalogue says, even if absent
        assertTrue(data.models.single().streaming)
    }

    /** The shared catalogue (copied into the APK): Shakshuka runs here, Sabich stays recommended. */
    @Test fun sharedCatalogueOffersShakshukaOnAndroid() {
        val f = listOf(File("../../shared/catalogue.json"), File("../shared/catalogue.json")).firstOrNull { it.exists() }
        assertNotNull("shared/catalogue.json not found from ${File(".").absolutePath}", f)
        val data = Catalogue.parse(f!!.readText())!!
        val shakshuka = data.models.first { it.id == "shakshuka" }
        assertTrue(shakshuka.streaming && shakshuka.available && shakshuka.language == null)
        assertTrue(shakshuka.offeredOn == null || Catalogue.PLATFORM in shakshuka.offeredOn!!)
        assertEquals("sabich-rolling", data.recommended)
    }
}
