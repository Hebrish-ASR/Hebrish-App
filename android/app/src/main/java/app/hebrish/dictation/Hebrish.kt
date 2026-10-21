package app.hebrish.dictation

import android.net.Uri

/**
 * hebrish.app, the website for the English-Hebrew code-switching model, its contact topics,
 * and the feedback address. The only place these URLs live; the setup screen's "Hebrish"
 * section is built from [LINKS]. The `topic` values are the ones hebrish.app/contact
 * understands. `mailto:` entries are opened as an email (ACTION_SENDTO) with the app and
 * device version appended to the body by MainActivity.
 */
object Hebrish {
    const val SITE = "https://hebrish.app"
    const val FEEDBACK = "feedback@hebrish.app"
    /** Always the newest APK (follows cdn.hebrish.app/downloads/latest.json). */
    const val APK = "$SITE/get/android"
    const val DOWNLOAD_PAGE = "$SITE/download#fdroid"
    /** The setup guide; steps have ids `step-mic`, `step-model`, … matching SetupActivity's order. */
    const val SETUP_GUIDE = "$SITE/setup"
    const val PRIVACY = "$SITE/privacy"
    const val LEXICON = "$SITE/lexicon"
    /** Ways to help: recordings, words, donations (side menu "Contribute"). */
    const val CONTRIBUTE = "$SITE/support"
    const val SAMPLES = "$SITE/contact?topic=samples"
    const val WORD = "$SITE/contact?topic=word"

    // The Hebrish F-Droid repository (Hebrish-ASR/Hebrish-FDroid). The fingerprint is the repo
    // signing key's SHA-256; it never changes (every user who added the repo pinned it).
    const val FDROID_APP = "https://f-droid.org/"
    const val FDROID_REPO = "https://fdroid.hebrish.app/repo"
    const val FDROID_FINGERPRINT = "EF8C2D63D994A10CD489A978585510B47E47452EC09248591CB2C0F39C2BC1FA"

    private fun mail(subject: String) = "mailto:$FEEDBACK?subject=" + Uri.encode("$subject (Hebrish for Android)")

    /** (button label, URL), in display order. */
    val LINKS = listOf(
        R.string.hebrish_site to SITE,
        R.string.hebrish_bug to mail("Bug report"),
        R.string.hebrish_feature to mail("Feature request"),
        R.string.hebrish_feedback to mail("Feedback"),
        R.string.hebrish_word to "$SITE/contact?topic=word",
        R.string.hebrish_samples to "$SITE/contact?topic=samples",
        R.string.hebrish_involved to "$SITE/contact?topic=involved",
    )
}
