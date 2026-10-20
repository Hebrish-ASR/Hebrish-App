package app.hebrish.dictation

import app.hebrish.core.Catalogue

/** Help and contact: hebrish.app, feedback by email, the contact form topics, source and terms. */
class ContactActivity : Page() {
    override fun build() {
        text(R.string.hebrish_body)
        // Built from Hebrish.LINKS, so adding or retiring a link touches only Hebrish.kt and its label.
        for ((label, url) in Hebrish.LINKS) button(label) { open(url) }

        heading(R.string.links)
        val r = row()
        button(R.string.open_model, r) {
            val m = Catalogue.selected(this)
            open(m.card ?: "https://huggingface.co/${m.repo}")
        }
        button(R.string.open_source, r) { open(getString(R.string.url_source)) }

        heading(R.string.terms_title)
        text(R.string.terms_body)
        button(R.string.open_terms) { open(getString(R.string.url_terms)) }
    }
}
