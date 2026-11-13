package app.hebrish.dictation

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** B-106: AppUpdateRules (version order, latest.json parsing, the download check, the switch default). */
class AppUpdateRulesTest {
    private val sha = "2f085c6ccaf210132fc2f8994b298b8051f50aebdeec62d3bbeaedaef0ca5db5"
    private fun manifest(android: String) = """{"version": "1.033", "files": {"android": $android, "ubuntu": {"version": "1.033"}}}"""
    private val good = """{"url": "https://cdn.hebrish.app/apps/android/Hebrish-latest.apk", "name": "Hebrish-v1.032.apk",
        "size": 17989636, "sha256": "$sha", "version": "1.032"}"""

    @Test fun newerCounter() = assertTrue(AppUpdateRules.isNewer("1.032", "1.031"))
    @Test fun sameIsNotNewer() = assertFalse(AppUpdateRules.isNewer("1.031", "1.031"))
    @Test fun olderIsNotNewer() = assertFalse(AppUpdateRules.isNewer("1.030", "1.031"))
    @Test fun countersCompareAsNumbers() = assertTrue(AppUpdateRules.isNewer("1.100", "1.099"))
    @Test fun majorWins() = assertTrue(AppUpdateRules.isNewer("2.000", "1.999"))
    @Test fun oldThreePartVersions() = assertTrue(AppUpdateRules.isNewer("1.000", "0.10.0"))
    @Test fun leadingV() = assertTrue(AppUpdateRules.isNewer("v1.032", "1.031"))
    @Test fun missingPartsAreZero() = assertFalse(AppUpdateRules.isNewer("1.0", "1.000"))
    @Test fun garbageIsNeverNewer() {
        assertFalse(AppUpdateRules.isNewer("latest", "1.031"))
        assertFalse(AppUpdateRules.isNewer("1.032", ""))
    }

    @Test fun parsesTheAndroidEntry() {
        val r = AppUpdateRules.parse(manifest(good))
        assertNotNull(r)
        assertEquals("1.032", r!!.version)
        assertEquals(17989636L, r.size)
        assertEquals(sha, r.sha256)
    }
    @Test fun uppercaseHashIsAccepted() = assertEquals(sha, AppUpdateRules.parse(manifest(good.replace(sha, sha.uppercase())))!!.sha256)
    @Test fun noAndroidEntry() = assertNull(AppUpdateRules.parse("""{"files": {"ubuntu": {}}}"""))
    @Test fun notJson() = assertNull(AppUpdateRules.parse("<html>"))
    @Test fun plainHttpRefused() = assertNull(AppUpdateRules.parse(manifest(good.replace("https://", "http://"))))
    @Test fun shortHashRefused() = assertNull(AppUpdateRules.parse(manifest(good.replace(sha, sha.drop(2)))))
    @Test fun zeroSizeRefused() = assertNull(AppUpdateRules.parse(manifest(good.replace("17989636", "0"))))
    @Test fun badVersionRefused() = assertNull(AppUpdateRules.parse(manifest(good.replace("\"1.032\"", "\"next\""))))

    @Test fun verify() {
        val r = AppUpdateRules.parse(manifest(good))!!
        assertEquals(AppUpdateRules.Verdict.OK, AppUpdateRules.verify(17989636L, sha.uppercase(), r))
        assertEquals(AppUpdateRules.Verdict.SIZE_MISMATCH, AppUpdateRules.verify(17989635L, sha, r))
        assertEquals(AppUpdateRules.Verdict.HASH_MISMATCH, AppUpdateRules.verify(17989636L, "0".repeat(64), r))
    }

    @Test fun hex() = assertEquals("00ff10", AppUpdateRules.hex(byteArrayOf(0, -1, 16)))

    @Test fun switchDefault() {
        assertFalse(AppUpdateRules.backgroundOn(null, permitted = false))
        assertTrue(AppUpdateRules.backgroundOn(null, permitted = true))
        assertFalse(AppUpdateRules.backgroundOn(false, permitted = true))
        assertFalse(AppUpdateRules.backgroundOn(true, permitted = false))
        assertTrue(AppUpdateRules.backgroundOn(true, permitted = true))
    }
}
