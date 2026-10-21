package app.hebrish.dictation

import android.widget.ImageView
import android.widget.LinearLayout

/**
 * About (0.6.0, Daniel 2026-10-20): what Hebrish is, the lexicon to explore, how to contribute,
 * links, and the version. Every URL comes from [Hebrish].
 */
class AboutActivity : Page() {
    override fun build() {
        column.addView(ImageView(this).apply { setImageResource(R.drawable.ic_hebrish) },
            LinearLayout.LayoutParams(dp(64), dp(64)).apply { topMargin = dp(12) })
        heading(R.string.app_name)
        text(R.string.about_body)

        heading(R.string.about_lexicon_title)
        text(R.string.about_lexicon)
        button(R.string.menu_lexicon) { open(Hebrish.LEXICON) }

        heading(R.string.about_contribute_title)
        text(R.string.about_contribute)
        button(R.string.hebrish_samples) { open(Hebrish.SAMPLES) }
        button(R.string.hebrish_word) { open(Hebrish.WORD) }
        button(R.string.about_support) { open(Hebrish.CONTRIBUTE) }

        heading(R.string.about_links_title)
        val r = row()
        button(R.string.hebrish_site, r) { open(Hebrish.SITE) }
        button(R.string.about_source, r) { open(getString(R.string.url_source)) }
        button(R.string.about_terms, r) { open(getString(R.string.url_terms)) }
        // Google Play wants the privacy policy reachable inside the app, not only in the listing (0.8.0).
        val r2 = row()
        button(R.string.about_privacy, r2) { open(Hebrish.PRIVACY) }
        button(R.string.about_verify, r2) { open(Hebrish.VERIFY) }

        text(versionSummary(), top = 28).apply { gravity = android.view.Gravity.CENTER; alpha = 0.8f }
        small(R.string.about_private).gravity = android.view.Gravity.CENTER
    }
}
