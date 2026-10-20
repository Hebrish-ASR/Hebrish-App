package app.hebrish.dictation

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.util.TypedValue
import android.view.MenuItem
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast

/**
 * Base of the app's screens: a scrolling column built in code, with helpers for headings, text,
 * buttons, switches and sliders. The setup used to be one long XML screen (activity_main.xml, up
 * to 0.3.0); since 0.4.0 each area has its own screen, reached from the home screen ([MainActivity]),
 * and every screen but home has an Up arrow.
 */
abstract class Page : Activity() {
    protected lateinit var column: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(12), dp(20), dp(32))
        }
        setContentView(ScrollView(this).apply { fitsSystemWindows = true; addView(column) })
        if (this !is MainActivity) actionBar?.setDisplayHomeAsUpEnabled(true)
        build()
    }

    /** Adds this screen's views to [column]. */
    protected abstract fun build()

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == android.R.id.home) { finish(); return true }
        return super.onOptionsItemSelected(item)
    }

    protected fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun <V : View> add(v: V, top: Int = 0, parent: LinearLayout = column): V {
        parent.addView(v, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            .apply { topMargin = dp(top) })
        return v
    }

    protected fun heading(text: CharSequence, parent: LinearLayout = column) = add(TextView(this).apply {
        this.text = text
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
        setTypeface(typeface, android.graphics.Typeface.BOLD)
    }, 22, parent)
    protected fun heading(res: Int, parent: LinearLayout = column) = heading(getString(res), parent)

    protected fun subheading(res: Int, parent: LinearLayout = column) = add(TextView(this).apply {
        setText(res)
        setTypeface(typeface, android.graphics.Typeface.BOLD)
    }, 12, parent)

    protected fun text(text: CharSequence = "", parent: LinearLayout = column, top: Int = 4) =
        add(TextView(this).apply { this.text = text; setTextIsSelectable(false) }, top, parent)
    protected fun text(res: Int, parent: LinearLayout = column, top: Int = 4) = text(getString(res), parent, top)

    protected fun small(res: Int, parent: LinearLayout = column) = add(TextView(this).apply {
        setText(res)
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
        alpha = 0.75f
    }, 2, parent)

    /** A wrap-content button on its own line, or in [parent] (e.g. a [row]). */
    protected fun button(res: Int, parent: LinearLayout = column, onClick: () -> Unit) = Button(this).apply {
        setText(res)
        setOnClickListener { onClick() }
        parent.addView(this, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT))
    }

    /** A horizontal line of buttons. */
    protected fun row(parent: LinearLayout = column) = add(LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }, 0, parent)

    protected fun switch(res: Int, get: () -> Boolean, set: (Boolean) -> Unit, parent: LinearLayout = column) = add(Switch(this).apply {
        setText(res)
        isChecked = get()
        setOnCheckedChangeListener { _, v -> set(v) }
    }, 8, parent)

    /** A slider from [min] to [max]; [label] is redrawn with the value as it moves. */
    protected fun slider(min: Int, max: Int, value: Int, label: TextView, format: (Int) -> String, set: (Int) -> Unit) =
        add(SeekBar(this).apply {
            this.max = max - min
            progress = value - min
            label.text = format(value)
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(bar: SeekBar, p: Int, fromUser: Boolean) {
                    label.text = format(p + min)
                    if (fromUser) set(p + min)
                }
                override fun onStartTrackingTouch(bar: SeekBar) = Unit
                override fun onStopTrackingTouch(bar: SeekBar) = Unit
            })
        })

    /** A tappable two-line entry that opens another screen. */
    protected fun nav(title: Int, summary: TextView.() -> Unit, target: Class<out Activity>): TextView {
        val box = add(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(12), 0, dp(12))
            val out = TypedValue()
            theme.resolveAttribute(android.R.attr.selectableItemBackground, out, true)
            setBackgroundResource(out.resourceId)
            setOnClickListener { startActivity(Intent(this@Page, target)) }
        }, 2)
        box.addView(TextView(this).apply {
            setText(title)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        })
        return TextView(this).apply { alpha = 0.8f; summary() }.also { box.addView(it) }
    }

    /** Opens a web page, or for a `mailto:` link an email with the app and device version appended. */
    protected fun open(url: String) {
        if (!url.startsWith("mailto:")) {
            try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) } catch (_: android.content.ActivityNotFoundException) {
                Toast.makeText(this, url, Toast.LENGTH_LONG).show()
            }
            return
        }
        // Feedback email: the version lines help triage; the user writes above them.
        val version = packageManager.getPackageInfo(packageName, 0).versionName
        val body = "\n\n--\nHebrish $version, Android ${Build.VERSION.RELEASE}, ${Build.MANUFACTURER} ${Build.MODEL}"
        val mail = Intent(Intent.ACTION_SENDTO, Uri.parse("$url&body=" + Uri.encode(body)))
        try { startActivity(mail) } catch (_: android.content.ActivityNotFoundException) {
            Toast.makeText(this, getString(R.string.no_email_app, Hebrish.FEEDBACK), Toast.LENGTH_LONG).show()
        }
    }

    protected fun versionName(): String = packageManager.getPackageInfo(packageName, 0).versionName ?: "?"
}
