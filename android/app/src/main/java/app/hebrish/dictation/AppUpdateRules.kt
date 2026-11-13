package app.hebrish.dictation

import org.json.JSONObject

/**
 * B-106: the decisions behind background app updates, kept free of Android calls so the JVM
 * unit test (AppUpdateRulesTest) can run them. [AppUpdates] does the network, files and install.
 *
 * The source is cdn.hebrish.app/downloads/latest.json, key `files.android`:
 * `{url, name, size, sha256, version}`, `version` as "M.NNN" (docs/maintaining.md,
 * "Version and tag"). The APK there is the `fdroid` build, signed with the release key.
 */
object AppUpdateRules {
    data class Release(val url: String, val name: String, val size: Long, val sha256: String, val version: String)

    enum class Verdict { OK, SIZE_MISMATCH, HASH_MISMATCH }

    /**
     * "1.031" → [1, 31]; a leading "v" is allowed, anything after the numbers ("-beta") ignored.
     * Null when it doesn't start with a number.
     */
    fun parts(version: String): List<Int>? {
        val m = Regex("""^v?(\d+(?:\.\d+)*)""").find(version.trim()) ?: return null
        return m.groupValues[1].split('.').map { it.toIntOrNull() ?: return null }
    }

    /** True when [remote] is a later version than [installed], part by part as numbers (1.100 > 1.031 > 1.0). */
    fun isNewer(remote: String, installed: String): Boolean {
        val r = parts(remote) ?: return false
        val i = parts(installed) ?: return false
        for (k in 0 until maxOf(r.size, i.size)) {
            val a = r.getOrElse(k) { 0 }
            val b = i.getOrElse(k) { 0 }
            if (a != b) return a > b
        }
        return false
    }

    /** The Android entry of latest.json, or null if it is missing or anything in it looks wrong. */
    fun parse(json: String): Release? = runCatching {
        val a = JSONObject(json).getJSONObject("files").getJSONObject("android")
        val r = Release(
            url = a.getString("url"),
            name = a.optString("name", "Hebrish.apk"),
            size = a.getLong("size"),
            sha256 = a.getString("sha256").lowercase(),
            version = a.getString("version"),
        )
        r.takeIf {
            it.url.startsWith("https://") && it.size > 0 && SHA256.matches(it.sha256) && parts(it.version) != null
        }
    }.getOrNull()

    /** Whether a downloaded file of [size] bytes with SHA-256 [sha256] (hex) is the published [r]. */
    fun verify(size: Long, sha256: String, r: Release): Verdict = when {
        size != r.size -> Verdict.SIZE_MISMATCH
        !sha256.equals(r.sha256, ignoreCase = true) -> Verdict.HASH_MISMATCH
        else -> Verdict.OK
    }

    /**
     * Background updates are on: the user's explicit choice ([explicit], null = never touched the
     * switch) if any, else on as soon as "Install unknown apps" is allowed. Never without it.
     */
    fun backgroundOn(explicit: Boolean?, permitted: Boolean): Boolean = permitted && (explicit ?: true)

    fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it) }

    private val SHA256 = Regex("^[0-9a-f]{64}$")
}
