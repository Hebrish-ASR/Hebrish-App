package app.hebrish.dictation

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.util.TypedValue
import android.view.MenuItem
import android.view.View
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.FrameLayout
import android.widget.ImageView
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
 * and every screen but home has an Up arrow. Home has the side menu instead (0.6.0, [drawer]).
 */
abstract class Page : Activity() {
    protected lateinit var column: LinearLayout
    /** The side menu (home only): a panel over the content, opened by the ☰ button. */
    private var drawer: View? = null
    private var scrim: View? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(12), dp(20), dp(32))
        }
        val scroll = ScrollView(this).apply { fitsSystemWindows = true; addView(column) }
        if (this is MainActivity) {
            setContentView(FrameLayout(this).apply { addView(scroll); addDrawer(this) })
            actionBar?.setDisplayHomeAsUpEnabled(true)
            actionBar?.setHomeAsUpIndicator(R.drawable.ic_menu)
            actionBar?.setHomeActionContentDescription(R.string.cd_menu)
        } else {
            setContentView(scroll)
            actionBar?.setDisplayHomeAsUpEnabled(true)
        }
        build()
    }

    /** Adds this screen's views to [column]. */
    protected abstract fun build()

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == android.R.id.home) {
            if (drawer != null) toggleDrawer(drawer?.visibility != View.VISIBLE) else finish()
            return true
        }
        return super.onOptionsItemSelected(item)
    }

    /**
     * Back closes the side menu first. Targeting 36 (0.8.0), Android 13+ no longer calls
     * onBackPressed (predictive back), so the menu registers this callback while it is open;
     * onBackPressed stays for Android 9 to 12.
     */
    private val closeDrawer: Any? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
        android.window.OnBackInvokedCallback { toggleDrawer(false) } else null

    @Deprecated("Activity.onBackPressed")
    override fun onBackPressed() {
        if (drawer?.visibility == View.VISIBLE) toggleDrawer(false) else @Suppress("DEPRECATION") super.onBackPressed()
    }

    private fun trackBack(open: Boolean) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        val cb = closeDrawer as android.window.OnBackInvokedCallback
        if (open) onBackInvokedDispatcher.registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, cb)
        else onBackInvokedDispatcher.unregisterOnBackInvokedCallback(cb)
    }

    /**
     * The side menu (Daniel, 2026-10-20: "we need like a sidebar menu"): every screen, the
     * lexicon, contributing, About, and the version at the bottom. Built by hand rather than
     * with androidx DrawerLayout, because the app has no androidx dependency.
     */
    private fun addDrawer(root: FrameLayout) {
        val bg = TypedValue().also { theme.resolveAttribute(android.R.attr.colorBackground, it, true) }.data
        scrim = View(this).apply {
            setBackgroundColor(0x66000000)
            visibility = View.GONE
            setOnClickListener { toggleDrawer(false) }
        }
        root.addView(scrim, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(bg)
            elevation = dp(8).toFloat()
            visibility = View.GONE
            isClickable = true
            fitsSystemWindows = true
        }
        val items = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, dp(8), 0, dp(8)) }
        val head = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(20), dp(20), dp(20), dp(12))
            addView(ImageView(this@Page).apply { setImageResource(R.drawable.ic_hebrish) }, LinearLayout.LayoutParams(dp(36), dp(36)))
            addView(TextView(this@Page).apply {
                text = getString(R.string.app_name)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 20f)
                setTypeface(typeface, android.graphics.Typeface.BOLD)
                setPadding(dp(12), 0, 0, 0)
            })
        }
        items.addView(head)
        fun entry(label: Int, go: () -> Unit) = items.addView(TextView(this).apply {
            setText(label)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            setPadding(dp(20), dp(13), dp(20), dp(13))
            val out = TypedValue()
            theme.resolveAttribute(android.R.attr.selectableItemBackground, out, true)
            setBackgroundResource(out.resourceId)
            setOnClickListener { toggleDrawer(false); go() }
        })
        fun screen(label: Int, target: Class<out Activity>) = entry(label) { startActivity(Intent(this, target)) }
        fun divider() = items.addView(View(this).apply { setBackgroundColor(0x33808080) },
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)).apply { setMargins(dp(20), dp(8), dp(20), dp(8)) })
        screen(R.string.title_setup, SetupActivity::class.java)
        screen(R.string.title_models, ModelsActivity::class.java)
        screen(R.string.title_keyboard, KeyboardActivity::class.java)
        screen(R.string.title_bubble, FloatingMicActivity::class.java)
        screen(R.string.title_dictation, DictationActivity::class.java)
        screen(R.string.title_dictionary, DictionaryActivity::class.java)
        screen(R.string.title_controls, ControlsActivity::class.java)
        if (Channel.installScreen) screen(R.string.title_install, InstallActivity::class.java)
        divider()
        entry(R.string.menu_lexicon) { open(Hebrish.LEXICON) }
        entry(R.string.menu_contribute) { open(Hebrish.CONTRIBUTE) }
        screen(R.string.title_contact, ContactActivity::class.java)
        screen(R.string.title_about, AboutActivity::class.java)
        panel.addView(ScrollView(this).apply { addView(items) }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        panel.addView(TextView(this).apply {
            text = versionSummary()
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            alpha = 0.7f
            setPadding(dp(20), dp(12), dp(20), dp(20))
        })
        root.addView(panel, FrameLayout.LayoutParams(dp(290), ViewGroup.LayoutParams.MATCH_PARENT, Gravity.START))
        drawer = panel
    }

    private fun toggleDrawer(show: Boolean) {
        val d = drawer ?: return
        val s = scrim ?: return
        trackBack(show)
        val w = dp(290).toFloat()
        if (show) {
            d.visibility = View.VISIBLE
            s.visibility = View.VISIBLE
            d.translationX = -w
            s.alpha = 0f
            d.animate().translationX(0f).setDuration(180)
            s.animate().alpha(1f).setDuration(180)
        } else {
            d.animate().translationX(-w).setDuration(160).withEndAction { d.visibility = View.GONE }
            s.animate().alpha(0f).setDuration(160).withEndAction { s.visibility = View.GONE }
        }
    }

    /** "Hebrish 0.6.0 · Jachnun v1.0": the side menu's footer and the bottom of home and About. */
    protected fun versionSummary(): String {
        val model = app.hebrish.core.Catalogue.selected(this)
        val installed = app.hebrish.core.ModelStore.installed(this, model)
        return if (installed != null && app.hebrish.core.ModelStore.isReady(this, model = model))
            getString(R.string.version_summary, versionName(), model.name, installed.label)
        else getString(R.string.version_summary_none, versionName())
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
