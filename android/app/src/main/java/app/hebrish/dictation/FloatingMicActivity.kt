package app.hebrish.dictation

import android.content.Intent
import android.content.SharedPreferences
import android.graphics.drawable.GradientDrawable
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.SeekBar
import android.widget.TextView

/**
 * The floating mic: whether it is on (with the step-by-step guide, [FloatingMicGuideActivity]),
 * where it sits and how it looks (icon, size, opacity, mic colour), and the bar shown while you talk (direction, size,
 * opacity, clear). Every control writes Prefs; FloatingMicService moves the mic live, and dragging the mic updates these
 * controls while the screen is open. Sliders have − / + buttons for one step at a time (0.11.0, Daniel: "so that you can
 * really dial in exactly what you're looking for").
 */
class FloatingMicActivity : Page(), SharedPreferences.OnSharedPreferenceChangeListener {
    private lateinit var status: TextView
    private lateinit var guideBtn: Button
    private lateinit var side: RadioGroup
    private lateinit var iconChoice: RadioGroup
    private lateinit var direction: RadioGroup
    private lateinit var barScale: SeekBar
    private lateinit var height: SeekBar
    private lateinit var across: SeekBar
    private lateinit var acrossViews: List<View>
    private lateinit var edge: SeekBar
    private lateinit var edgeViews: List<View>
    private lateinit var size: SeekBar
    private lateinit var alpha: SeekBar
    private lateinit var barAlpha: SeekBar
    /** Colour swatches, by ARGB value; the chosen one has a ring. */
    private val swatches = mutableMapOf<Int, GradientDrawable>()
    private val sideIds = mutableMapOf<String, Int>()
    private val iconIds = mutableMapOf<String, Int>()
    private val directionIds = mutableMapOf<String, Int>()

    override fun build() {
        status = text()
        guideBtn = button(R.string.bubble_guide) { startActivity(Intent(this, FloatingMicGuideActivity::class.java)) }
        button(R.string.bubble_enable) { FloatingMicConsentActivity.openSettings(this) }

        heading(R.string.bubble_how_title)
        text(R.string.bubble_body)

        heading(R.string.bubble_position)
        side = choice(listOf(Prefs.SIDE_LEFT to R.string.bubble_left, Prefs.SIDE_RIGHT to R.string.bubble_right,
            Prefs.SIDE_FREE to R.string.bubble_free), sideIds, { Prefs.bubbleSide(this) }) { Prefs.setBubbleSide(this, it) }
        small(R.string.bubble_drag_hint)

        val heightLabel = text(top = 12)
        height = slider(0, 1000, (Prefs.bubbleY(this) * 1000).toInt(), heightLabel,
            { getString(R.string.bubble_height_fine, it / 10f) }) { Prefs.setBubbleY(this, it / 1000f) }
        row().also { r ->
            button(R.string.bubble_up, r) { Prefs.setBubbleY(this, Prefs.bubbleY(this) - NUDGE) }
            button(R.string.bubble_down, r) { Prefs.setBubbleY(this, Prefs.bubbleY(this) + NUDGE) }
        }

        val acrossLabel = text(top = 12)
        across = slider(0, 1000, (Prefs.bubbleX(this) * 1000).toInt(), acrossLabel,
            { getString(R.string.bubble_across, it / 10f) }) { Prefs.setBubbleX(this, it / 1000f) }
        val acrossRow = row().also { r ->
            button(R.string.bubble_leftward, r) { Prefs.setBubbleX(this, Prefs.bubbleX(this) - NUDGE) }
            button(R.string.bubble_rightward, r) { Prefs.setBubbleX(this, Prefs.bubbleX(this) + NUDGE) }
        }
        acrossViews = listOf(acrossLabel, across, acrossRow)

        val edgeLabel = text(top = 12)
        edge = slider(0, Prefs.EDGE_MAX, Prefs.bubbleEdge(this), edgeLabel,
            { getString(R.string.bubble_edge, it) }) { Prefs.setBubbleEdge(this, it) }
        edgeViews = listOf(edgeLabel, edge)

        text(R.string.bubble_icon, top = 12)
        iconChoice = choice(listOf(Prefs.ICON_MIC to R.string.bubble_icon_mic, Prefs.ICON_LOGO to R.string.bubble_icon_logo,
            Prefs.ICON_AYIN to R.string.bubble_icon_ayin), iconIds, { Prefs.bubbleIcon(this) }) { Prefs.setBubbleIcon(this, it) }
        small(R.string.bubble_icon_hint)

        size = stepped(Prefs.SIZE_MIN, Prefs.SIZE_MAX, { Prefs.bubbleSize(this) }, { Prefs.setBubbleSize(this, it) }) {
            getString(R.string.bubble_size_dp, it)
        }
        alpha = stepped(Prefs.ALPHA_MIN, 100, { Prefs.bubbleAlpha(this) }, { Prefs.setBubbleAlpha(this, it) }) {
            getString(R.string.bubble_alpha, it)
        }

        text(R.string.bubble_colour, top = 12)
        val colours = row()
        for ((i, c) in Prefs.BUBBLE_COLORS.withIndex()) {
            val d = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(c) }
            swatches[c] = d
            colours.addView(View(this).apply {
                background = d
                contentDescription = getString(R.string.bubble_colour_cd, i + 1)
                setOnClickListener { Prefs.setBubbleColor(this@FloatingMicActivity, c) }
            }, LinearLayout.LayoutParams(dp(40), dp(40)).apply { setMargins(0, dp(6), dp(10), dp(6)) })
        }
        small(R.string.bubble_colour_hint)

        heading(R.string.bubble_bar)
        text(R.string.bubble_bar_body)
        direction = choice(listOf(Prefs.BAR_ALONG to R.string.bubble_bar_along, Prefs.BAR_ACROSS to R.string.bubble_bar_across),
            directionIds, { Prefs.bubbleBarDirection(this) }) { Prefs.setBubbleBarDirection(this, it) }
        small(R.string.bubble_bar_direction_hint)
        barScale = stepped(Prefs.BAR_SCALE_MIN, 100, { Prefs.bubbleBarScale(this) }, { Prefs.setBubbleBarScale(this, it) }) {
            getString(R.string.bubble_bar_scale, it)
        }
        barAlpha = stepped(Prefs.BAR_ALPHA_MIN, 100, { Prefs.bubbleBarAlpha(this) }, { Prefs.setBubbleBarAlpha(this, it) }) {
            getString(R.string.bubble_bar_alpha, it)
        }
        switch(R.string.bubble_bar_clear, { Prefs.bubbleBarClear(this) }, { Prefs.setBubbleBarClear(this, it) })

        heading(R.string.step_options)
        switch(R.string.bubble_only_typing, { Prefs.bubbleOnlyTyping(this) }, { Prefs.setBubbleOnlyTyping(this, it) })
        switch(R.string.bubble_clear_placeholder, { Prefs.clearPlaceholder(this) }, { Prefs.setClearPlaceholder(this, it) })
        small(R.string.bubble_clear_placeholder_hint)
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
            text(R.string.bubble_clipboard_notice, top = 12)
            button(R.string.bubble_clipboard_settings) {
                runCatching { startActivity(Intent(android.provider.Settings.ACTION_PRIVACY_SETTINGS)) }
                    .onFailure { startActivity(Intent(android.provider.Settings.ACTION_SETTINGS)) }
            }
        }
        text(R.string.bubble_options_hint)
    }

    /** A row of radio buttons for [options] (pref value to label); the ids go in [ids] for render(). */
    private fun choice(options: List<Pair<String, Int>>, ids: MutableMap<String, Int>, get: () -> String, set: (String) -> Unit): RadioGroup {
        val g = RadioGroup(this).apply { orientation = RadioGroup.HORIZONTAL }
        for ((key, label) in options) {
            val id = View.generateViewId()
            ids[key] = id
            g.addView(RadioButton(this).apply { this.id = id; setText(label); setPadding(0, 0, dp(12), 0) })
        }
        column.addView(g)
        g.setOnCheckedChangeListener { _, id -> ids.entries.firstOrNull { it.value == id }?.key?.let { if (it != get()) set(it) } }
        return g
    }

    /** A labelled slider with − and + buttons beside the label that move it one step. */
    private fun stepped(min: Int, max: Int, get: () -> Int, set: (Int) -> Unit, format: (Int) -> String): SeekBar {
        val line = row().apply { gravity = android.view.Gravity.CENTER_VERTICAL; setPadding(0, dp(12), 0, 0) }
        val label = TextView(this).apply { textSize = 15f }
        line.addView(label, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        val minus = button(R.string.bubble_minus, line) { set((get() - 1).coerceIn(min, max)) }
        val plus = button(R.string.bubble_plus, line) { set((get() + 1).coerceIn(min, max)) }
        // The buttons' spoken names follow the value ("Less: Size: 44 dp").
        return slider(min, max, get(), label, { v ->
            format(v).also {
                minus.contentDescription = getString(R.string.bubble_minus_cd, it)
                plus.contentDescription = getString(R.string.bubble_plus_cd, it)
            }
        }, set)
    }

    override fun onResume() {
        super.onResume()
        Prefs.listen(this, this)
        render()
    }

    override fun onPause() {
        super.onPause()
        Prefs.unlisten(this, this)
    }

    override fun onSharedPreferenceChanged(sp: SharedPreferences?, key: String?) {
        if (key?.startsWith("bubble_") == true) render()
    }

    /** Reads every control back from Prefs: dragging the mic changes side, height and place. */
    private fun render() {
        val on = Setup.bubbleOn(this)
        status.text = getString(if (on) R.string.bubble_on else R.string.bubble_off) +
            if (!Setup.hasMic(this)) "\n" + getString(R.string.bubble_needs_mic) else ""
        guideBtn.setText(if (on) R.string.bubble_guide else R.string.bubble_guide_first)
        val s = Prefs.bubbleSide(this)
        sideIds[s]?.let { if (side.checkedRadioButtonId != it) side.check(it) }
        iconIds[Prefs.bubbleIcon(this)]?.let { if (iconChoice.checkedRadioButtonId != it) iconChoice.check(it) }
        directionIds[Prefs.bubbleBarDirection(this)]?.let { if (direction.checkedRadioButtonId != it) direction.check(it) }
        val free = s == Prefs.SIDE_FREE
        for (v in acrossViews) v.visibility = if (free) View.VISIBLE else View.GONE
        for (v in edgeViews) v.visibility = if (free) View.GONE else View.VISIBLE
        height.progress = (Prefs.bubbleY(this) * 1000).toInt()
        across.progress = (Prefs.bubbleX(this) * 1000).toInt()
        edge.progress = Prefs.bubbleEdge(this)
        size.progress = Prefs.bubbleSize(this) - Prefs.SIZE_MIN
        alpha.progress = Prefs.bubbleAlpha(this) - Prefs.ALPHA_MIN
        barAlpha.progress = Prefs.bubbleBarAlpha(this) - Prefs.BAR_ALPHA_MIN
        barScale.progress = Prefs.bubbleBarScale(this) - Prefs.BAR_SCALE_MIN
        val chosen = Prefs.bubbleColor(this)
        for ((c, d) in swatches) d.setStroke(if (c == chosen) dp(3) else 0, getColor(android.R.color.darker_gray))
    }

    private companion object {
        /** One tap on a nudge button: half a percent of the screen. */
        const val NUDGE = 0.005f
    }
}
