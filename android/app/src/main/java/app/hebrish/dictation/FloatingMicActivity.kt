package app.hebrish.dictation

import android.content.Intent
import android.content.SharedPreferences
import android.provider.Settings
import android.view.View
import android.widget.Button
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.SeekBar
import android.widget.TextView

/**
 * The floating mic: whether it is on (with the step-by-step guide, [FloatingMicGuideActivity]),
 * where it sits and how it looks. Every control writes Prefs; FloatingMicService moves the mic
 * live, and dragging the mic updates these controls while the screen is open.
 */
class FloatingMicActivity : Page(), SharedPreferences.OnSharedPreferenceChangeListener {
    private lateinit var status: TextView
    private lateinit var guideBtn: Button
    private lateinit var side: RadioGroup
    private lateinit var height: SeekBar
    private lateinit var across: SeekBar
    private lateinit var acrossViews: List<View>
    private lateinit var edge: SeekBar
    private lateinit var edgeViews: List<View>
    private lateinit var size: SeekBar
    private lateinit var alpha: SeekBar
    private val sideIds = mutableMapOf<String, Int>()

    override fun build() {
        status = text()
        guideBtn = button(R.string.bubble_guide) { startActivity(Intent(this, FloatingMicGuideActivity::class.java)) }
        button(R.string.bubble_enable) { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }

        heading(R.string.bubble_how_title)
        text(R.string.bubble_body)

        heading(R.string.bubble_position)
        side = RadioGroup(this).apply { orientation = RadioGroup.HORIZONTAL }
        for ((key, label) in listOf(Prefs.SIDE_LEFT to R.string.bubble_left, Prefs.SIDE_RIGHT to R.string.bubble_right,
                Prefs.SIDE_FREE to R.string.bubble_free)) {
            val id = View.generateViewId()
            sideIds[key] = id
            side.addView(RadioButton(this).apply { this.id = id; setText(label); setPadding(0, 0, dp(12), 0) })
        }
        column.addView(side)
        side.setOnCheckedChangeListener { _, id ->
            sideIds.entries.firstOrNull { it.value == id }?.key?.let { if (it != Prefs.bubbleSide(this)) Prefs.setBubbleSide(this, it) }
        }
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

        val sizeLabel = text(top = 12)
        size = slider(Prefs.SIZE_MIN, Prefs.SIZE_MAX, Prefs.bubbleSize(this), sizeLabel,
            { getString(R.string.bubble_size_dp, it) }) { Prefs.setBubbleSize(this, it) }

        val alphaLabel = text(top = 12)
        alpha = slider(Prefs.ALPHA_MIN, 100, Prefs.bubbleAlpha(this), alphaLabel,
            { getString(R.string.bubble_alpha, it) }) { Prefs.setBubbleAlpha(this, it) }

        heading(R.string.step_options)
        switch(R.string.bubble_only_typing, { Prefs.bubbleOnlyTyping(this) }, { Prefs.setBubbleOnlyTyping(this, it) })
        text(R.string.bubble_options_hint)
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
        val free = s == Prefs.SIDE_FREE
        for (v in acrossViews) v.visibility = if (free) View.VISIBLE else View.GONE
        for (v in edgeViews) v.visibility = if (free) View.GONE else View.VISIBLE
        height.progress = (Prefs.bubbleY(this) * 1000).toInt()
        across.progress = (Prefs.bubbleX(this) * 1000).toInt()
        edge.progress = Prefs.bubbleEdge(this)
        size.progress = Prefs.bubbleSize(this) - Prefs.SIZE_MIN
        alpha.progress = Prefs.bubbleAlpha(this) - Prefs.ALPHA_MIN
    }

    private companion object {
        /** One tap on a nudge button: half a percent of the screen. */
        const val NUDGE = 0.005f
    }
}
