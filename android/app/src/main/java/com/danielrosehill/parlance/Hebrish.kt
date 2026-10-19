package com.danielrosehill.parlance

/**
 * hebrish.app, the website for the English-Hebrew code-switching model, and its contact
 * topics. The only place these URLs live; the setup screen's "Hebrish" section is built from
 * [LINKS]. The `topic` values are the ones hebrish.app/contact understands.
 */
object Hebrish {
    const val SITE = "https://hebrish.app"

    /** (button label, URL), in display order. */
    val LINKS = listOf(
        R.string.hebrish_site to SITE,
        R.string.hebrish_bug to "$SITE/contact?topic=bug",
        R.string.hebrish_word to "$SITE/contact?topic=word",
        R.string.hebrish_samples to "$SITE/contact?topic=samples",
        R.string.hebrish_involved to "$SITE/contact?topic=involved",
    )
}
