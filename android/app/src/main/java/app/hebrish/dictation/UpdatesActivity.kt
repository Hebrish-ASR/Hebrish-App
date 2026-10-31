package app.hebrish.dictation

import android.util.TypedValue
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONObject

/**
 * What's new (2026-10-25, Daniel: "bake in the short updates according to the build time"): the
 * project's recent changes, newest first, read from the APK's assets/updates.json. That file is
 * shared/updates-android.json, baked from hebrish.app/changelog by scripts/bake_updates.py before
 * each release and copied in by the gradle copyCatalogue task, so the list is offline and fixed at
 * build time. It holds only the entries filed under Android (including model updates the app
 * offers; 2026-10-31). Reached from home (More), the side menu and About.
 */
class UpdatesActivity : Page() {
    override fun build() {
        val doc = runCatching { JSONObject(assets.open(ASSET).bufferedReader().use { it.readText() }) }.getOrNull()
        val entries = doc?.optJSONArray("entries")
        if (doc == null || entries == null || entries.length() == 0) {
            text(R.string.updates_none, top = 12)
        } else {
            text(getString(R.string.updates_intro, doc.optString("built")), top = 12)
            for (i in 0 until entries.length()) entry(entries.getJSONObject(i))
        }
        button(R.string.updates_full) { open(Hebrish.CHANGELOG) }.apply {
            (layoutParams as LinearLayout.LayoutParams).topMargin = dp(24)
        }
    }

    /** One entry as a card: date and tag, the title, a sentence or two. */
    private fun entry(e: JSONObject) {
        val card = group()
        card.setPadding(dp(16), dp(12), dp(16), dp(14))
        card.addView(TextView(this).apply {
            text = listOf(e.optString("date"), e.optString("tag")).filter { it.isNotEmpty() }.joinToString(" · ")
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            setTextColor(getColor(R.color.brand_muted))
        })
        card.addView(TextView(this).apply {
            text = e.optString("title")
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            typeface = android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL)
            setTextColor(getColor(R.color.brand_ink))
            setPadding(0, dp(2), 0, dp(2))
        })
        text(e.optString("summary"), card, top = 2)
    }

    companion object {
        const val ASSET = "updates.json"
    }
}
