package app.hebrish.dictation

/**
 * Which build this is (0.8.0): the `fdroid` flavor (GitHub release APK, CDN, fdroid.hebrish.app)
 * or the `play` flavor (Google Play). The play manifest drops the battery exemption and
 * hardware-key filtering; these flags hide the UI that needs them.
 */
object Channel {
    val play = BuildConfig.FLAVOR == "play"
    /** The direct "allow unrestricted" prompt needs REQUEST_IGNORE_BATTERY_OPTIMIZATIONS. */
    val batteryPrompt = !play
    /** Learned keys need flagRequestFilterKeyEvents (res/xml/floating_mic.xml). */
    val hardwareKeys = !play
    /** Play does not allow pointing users at another store, so no F-Droid screen there. */
    val installScreen = !play
}
