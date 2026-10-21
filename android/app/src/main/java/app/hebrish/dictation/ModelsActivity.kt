package app.hebrish.dictation

import app.hebrish.core.*
import android.content.Intent
import android.net.Uri
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView

/**
 * Models: download any model whether or not it is the one in use, all of them with one button,
 * choose which one the keyboard and floating mic use, update and delete. Models live in app
 * storage only: the custom location (shared folder, all-files access) was retired in 0.8.0.
 * Downloads run one at a time; the rest wait in ModelDownload's queue.
 */
class ModelsActivity : Page() {
    private lateinit var allBtn: Button
    private lateinit var list: LinearLayout
    private lateinit var checkStatus: TextView
    private lateinit var checkBtn: Button

    override fun build() {
        text(R.string.models_intro)
        allBtn = button(R.string.models_download_all) {
            if (ModelDownload.status is ModelDownload.Status.Running) ModelDownload.cancel() else ModelDownload.downloadAll(this)
        }
        small(R.string.download_terms)
        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        column.addView(list)

        heading(R.string.models_updates)
        checkStatus = text()
        checkBtn = button(R.string.check_update) { ModelDownload.check(this, force = true) }
    }

    override fun onResume() {
        super.onResume()
        ModelDownload.listener = { render() }
        ModelDownload.check(this)
        render()
    }

    override fun onPause() {
        super.onPause()
        ModelDownload.listener = null
    }

    private fun mb(bytes: Long) = bytes / 1_000_000

    /** Expected size of [m] before it is downloaded: its known manifest, else the catalogue's download_mb, else ~660 MB. */
    private fun size(m: Catalogue.Model) =
        (ModelDownload.latest(m.id) ?: ModelStore.installed(this, m))?.totalBytes
            ?: m.downloadMb?.let { it * 1_000_000L }
            ?: ModelStore.BUNDLED.values.first().totalBytes

    private fun render() {
        val s = ModelDownload.status
        val running = s is ModelDownload.Status.Running
        val models = Catalogue.get(this).models
        val missing = models.filter { it.available && !ModelStore.isReady(this, model = it) }
        allBtn.isEnabled = running || missing.isNotEmpty()
        allBtn.text = when {
            running -> getString(R.string.models_cancel_all)
            missing.isEmpty() -> getString(R.string.models_all_downloaded)
            else -> getString(R.string.models_download_all_size, missing.size, mb(missing.sumOf { size(it) }))
        }
        if (running) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        list.removeAllViews()
        val selected = Catalogue.selected(this)
        for (line in Catalogue.get(this).lines) {
            lineHeader(line)
            for (m in line.variants) card(m, m.id == selected.id, s)
        }

        checkBtn.visibility = if (ModelDownload.checking) View.GONE else View.VISIBLE
        checkStatus.text = when {
            ModelDownload.checking -> getString(R.string.update_checking)
            ModelDownload.checkError != null -> getString(R.string.update_check_failed, ModelDownload.checkError)
            else -> getString(R.string.models_updates_hint)
        }

    }

    /** The line's mark: Jachnun and Sabich have one (Hebrish-Mgmt/brand/logo); the others get the app's. */
    private fun mark(line: String) = when (line) {
        "jachnun" -> R.drawable.model_jachnun
        "sabich" -> R.drawable.model_sabich
        "stock" -> R.drawable.model_stock
        else -> R.drawable.ic_hebrish
    }

    /** A line (0.7.0): its mark, name, what it is trained for, and a link to its page. */
    private fun lineHeader(line: Catalogue.Line) {
        val top = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(22), 0, dp(2))
        }
        list.addView(top)
        top.addView(ImageView(this).apply { setImageResource(mark(line.id)) }, LinearLayout.LayoutParams(dp(44), dp(44)))
        val words = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), 0, 0, 0) }
        top.addView(words, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        words.addView(TextView(this).apply {
            text = line.name
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 21f)
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        })
        words.addView(TextView(this).apply { text = line.summary; alpha = 0.85f })
        line.card?.let { url -> words.addView(link(getString(R.string.models_line_about, line.name), url)) }
    }

    private fun link(label: String, url: String) = TextView(this).apply {
        text = android.text.SpannableString(label).apply {
            setSpan(android.text.style.UnderlineSpan(), 0, length, 0)
        }
        setTextColor(0xFF0F6B5C.toInt())
        setPadding(0, dp(4), 0, dp(4))
        setOnClickListener { runCatching { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) } }
    }

    /** "Speed ●●●○○  Accuracy ●●●●○ (estimates)": the speed/accuracy gradient (catalogue tiers). */
    private fun tiers(m: Catalogue.Model): CharSequence {
        fun dots(n: Int, colour: String) = "<font color='$colour'>" + "●".repeat(n.coerceIn(0, 5)) +
            "</font><font color='#BBBBBB'>" + "●".repeat(5 - n.coerceIn(0, 5)) + "</font>"
        return android.text.Html.fromHtml(getString(R.string.models_tiers, dots(m.speed, "#2E7DD1"), dots(m.accuracy, "#0F6B5C")),
            android.text.Html.FROM_HTML_MODE_COMPACT)
    }

    /**
     * One variant as a card (0.6.0; grouped under its line with tiers since 0.7.0): its name and
     * base model, a Recommended / In use badge, who it is for, the speed/accuracy tiers, size and
     * hardware, its state, and the actions that make sense for it now. A variant this build can't
     * run is greyed, says where it runs instead, and links to its card.
     */
    private fun card(m: Catalogue.Model, inUse: Boolean, s: ModelDownload.Status) {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.card_bg)
            setPadding(dp(16), dp(12), dp(16), dp(8))
        }
        list.addView(card, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            .apply { topMargin = dp(10) })
        val words = card
        val nameRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        words.addView(nameRow)
        nameRow.addView(TextView(this).apply {
            text = m.name
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        })
        val badge = when {
            inUse -> getString(R.string.models_badge_in_use)
            m.id == Catalogue.get(this).recommended -> getString(R.string.models_badge_recommended)
            else -> null
        }
        if (badge != null) nameRow.addView(TextView(this).apply {
            text = badge
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 11f)
            setTextColor(0xFFFFFFFF.toInt())
            setBackgroundResource(R.drawable.badge_bg)
            setPadding(dp(8), dp(2), dp(8), dp(2))
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { marginStart = dp(10) })
        if (m.baseModel.isNotEmpty()) words.addView(TextView(this).apply {
            text = m.baseModel
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            alpha = 0.6f
        })
        words.addView(TextView(this).apply { text = m.recommendation.ifEmpty { m.summary }; setPadding(0, dp(4), 0, dp(2)) })
        words.addView(TextView(this).apply { text = tiers(m); setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f) })
        words.addView(TextView(this).apply {
            text = listOfNotNull(m.downloadMb?.let { getString(R.string.models_size_mb, it) }, m.hardware.ifEmpty { null })
                .joinToString(" · ")
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            alpha = 0.75f
        })
        if (!m.supported) {
            card.alpha = 0.6f
            text(getString(R.string.models_runs_on, m.runsOn), card)
            m.card?.let { card.addView(link(getString(R.string.models_card), it)) }
            return
        }
        val list = card
        val ready = ModelStore.isReady(this, model = m)
        val installed = ModelStore.installed(this, m)
        val update = ModelDownload.updateAvailable(this, m)
        val active = s is ModelDownload.Status.Running && !ModelDownload.moving && ModelDownload.target?.first?.id == m.id
        val state = text("", list)
        state.text = when {
            !m.available -> getString(R.string.model_coming_soon_long)
            active -> {
                s as ModelDownload.Status.Running
                getString(R.string.model_downloading_version,
                    listOfNotNull(m.name, ModelDownload.target?.second?.version).joinToString(" "), mb(s.done), mb(s.total))
            }
            ModelDownload.queued(m.id) -> getString(R.string.models_queued)
            s is ModelDownload.Status.Failed && ModelDownload.failedId == m.id -> getString(R.string.model_failed, s.message)
            ready && update != null -> getString(R.string.update_available, update.version, mb(update.totalBytes), installed!!.version)
            ready -> getString(R.string.models_downloaded, installed!!.version, mb(installed.totalBytes))
            else -> getString(R.string.models_not_downloaded, mb(size(m)))
        }
        if (active) {
            s as ModelDownload.Status.Running
            list.addView(ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
                max = 1000
                progress = (s.done * 1000 / s.total.coerceAtLeast(1)).toInt()
            })
        }
        if (!m.available) return
        val r = row(list)
        when {
            active -> button(R.string.cancel, r) { ModelDownload.cancel() }
            ModelDownload.queued(m.id) -> button(R.string.models_unqueue, r) { ModelDownload.unqueue(m) }
            !ready -> button(R.string.download, r) { ModelDownload.download(this, m); render() }
        }
        if (ready && !inUse) button(R.string.models_use, r) { use(m) }
        if (ready && update != null && s !is ModelDownload.Status.Running) button(getString(R.string.update_button, update.version), r) {
            ModelDownload.update(this, m)
        }
        if (ready && !inUse && !active) button(R.string.delete, r) { confirmDelete(m) }
    }

    private fun button(label: String, parent: LinearLayout, onClick: () -> Unit) = Button(this).apply {
        text = label
        setOnClickListener { onClick() }
        parent.addView(this)
    }

    /** Makes [m] the model the keyboard and floating mic use. */
    private fun use(m: Catalogue.Model) {
        ModelPrefs.setSelectedModel(this, m.id)
        Transcriber.unload()
        Transcriber.preload(this)
        ModelDownload.clearFailure()
        ModelDownload.check(this)
        render()
    }

    private fun confirmDelete(m: Catalogue.Model) {
        android.app.AlertDialog.Builder(this)
            .setMessage(getString(R.string.manage_confirm, m.name))
            .setPositiveButton(R.string.delete) { _, _ -> ModelStore.delete(this, m); render() }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }
}
