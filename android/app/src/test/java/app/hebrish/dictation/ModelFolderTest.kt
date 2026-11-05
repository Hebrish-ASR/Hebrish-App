package app.hebrish.dictation

import app.hebrish.core.ModelStore
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

/** manifest.json, the contract other on-device apps read (android/docs/maintaining.md, "Model location"). */
class ModelFolderTest {
    @get:Rule val tmp = TemporaryFolder()

    private fun manifest(version: String = "Sabich (Rolling) v2.9", rev: String = "cf99019b305499526c0f88ce2153a7fda87f1086") =
        ModelStore.Manifest(version, rev, listOf(
            ModelStore.ModelFile("encoder.int8.onnx", 5, "abc"),
            ModelStore.ModelFile("tokens.txt", 3, null),
        ), "https://cdn.example/models/sabich/")

    /** A version folder under [base] as the app leaves it. */
    private fun install(base: File, m: ModelStore.Manifest, id: String = "sabich", withManifest: Boolean = true) =
        File(base, m.dirName).apply {
            mkdirs()
            m.files.forEach { File(this, it.name).writeBytes(ByteArray(it.size.toInt())) }
            if (withManifest) assertTrue(ModelStore.writeFolderManifest(this, m, id, "Sabich"))
        }

    @Test fun manifestRoundTrip() {
        val m = manifest()
        val dir = install(tmp.root, m)
        val read = ModelStore.readFolder(dir)!!
        assertEquals("sabich", read.modelId)
        assertEquals(m, read.manifest)
        assertFalse(File(dir, "${ModelStore.MANIFEST_FILE}.tmp").exists())
    }

    @Test fun contractFields() {
        val o = JSONObject(ModelStore.folderJson(manifest(), "sabich", "Sabich"))
        assertEquals("sabich", o.getString("model"))
        assertEquals("Sabich", o.getString("name"))
        assertEquals("Sabich (Rolling) v2.9", o.getString("version"))
        assertEquals("cf99019b305499526c0f88ce2153a7fda87f1086", o.getString("revision"))
        val f = o.getJSONArray("files")
        assertEquals("encoder.int8.onnx", f.getJSONObject(0).getString("name"))
        assertEquals(5L, f.getJSONObject(0).getLong("size"))
        assertEquals("abc", f.getJSONObject(0).getString("sha256"))
        assertTrue(f.getJSONObject(1).isNull("sha256"))
    }

    @Test fun readFolderIgnoresMissingAndBroken() {
        assertNull(ModelStore.readFolder(tmp.root))
        File(tmp.root, ModelStore.MANIFEST_FILE).writeText("{not json")
        assertNull(ModelStore.readFolder(tmp.root))
    }

    @Test fun adoptsCompleteFolder() {
        val m = manifest()
        install(tmp.root, m)
        assertEquals(m, ModelStore.findComplete(tmp.root, "sabich")?.manifest)
    }

    @Test fun skipsWrongSizeMissingFileOtherModelAndRenamedFolder() {
        val m = manifest()
        val dir = install(tmp.root, m)
        File(dir, "tokens.txt").writeBytes(ByteArray(1))
        assertNull(ModelStore.findComplete(tmp.root, "sabich"))
        File(dir, "tokens.txt").delete()
        assertNull(ModelStore.findComplete(tmp.root, "sabich"))
        File(dir, "tokens.txt").writeBytes(ByteArray(3))
        assertNotNull(ModelStore.findComplete(tmp.root, "sabich"))
        assertNull(ModelStore.findComplete(tmp.root, "shakshuka"))
        assertTrue(dir.renameTo(File(tmp.root, "renamed")))
        assertNull(ModelStore.findComplete(tmp.root, "sabich"))
    }

    @Test fun folderWithoutManifestIsNotAdopted() {
        install(tmp.root, manifest(), withManifest = false)
        assertNull(ModelStore.findComplete(tmp.root, "sabich"))
    }

    @Test fun newestManifestWins() {
        val old = manifest("v2.8", "a".repeat(40))
        val new = manifest("v2.9", "b".repeat(40))
        File(install(tmp.root, old), ModelStore.MANIFEST_FILE).setLastModified(1_000_000)
        File(install(tmp.root, new), ModelStore.MANIFEST_FILE).setLastModified(2_000_000)
        assertEquals(new, ModelStore.findComplete(tmp.root, "sabich")?.manifest)
    }

    @Test fun pruneKeepsInstalledAndOtherModels() {
        val keep = install(tmp.root, manifest("v2.9", "b".repeat(40)))
        val old = install(tmp.root, manifest("v2.8", "a".repeat(40)))
        val partial = install(tmp.root, manifest("v3.0", "c".repeat(40)), withManifest = false)
        val other = install(tmp.root, manifest("v1.0", "d".repeat(40)), id = "shakshuka")
        val gone = ModelStore.prunable(tmp.root, keep.name, "sabich").toSet()
        assertEquals(setOf(old, partial), gone)
        assertFalse(other in gone)
    }

    @Test fun missingBaseIsEmpty() {
        val none = File(tmp.root, "none")
        assertNull(ModelStore.findComplete(none, "sabich"))
        assertTrue(ModelStore.prunable(none, null, "sabich").isEmpty())
    }
}
