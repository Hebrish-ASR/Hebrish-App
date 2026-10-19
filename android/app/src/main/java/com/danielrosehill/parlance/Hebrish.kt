package com.danielrosehill.parlance

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
