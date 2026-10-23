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
            setPadding(dp(20), dp(8), dp(20), dp(40))
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
        val items = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, 0, 0, dp(8)) }
        // Header (0.10.0): the mark and the name in the brand's display face on the brand band.
        items.addView(brandHeader(markSize = 44, nameSize = 24f).apply {
            setBackgroundColor(getColor(R.color.brand_band))
            setPadding(dp(20), dp(28), dp(20), dp(20))
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(8) })
        fun entry(label: Int, go: () -> Unit) = items.addView(TextView(this).apply {
            setText(label)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
            setTextColor(getColor(R.color.brand_ink))
            typeface = android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL)
            setPadding(dp(24), dp(14), dp(20), dp(14))
            val out = TypedValue()
            theme.resolveAttribute(android.R.attr.selectableItemBackground, out, true)
            setBackgroundResource(out.resourceId)
            setOnClickListener { toggleDrawer(false); go() }
        })
        fun screen(label: Int, target: Class<out Activity>) = entry(label) { startActivity(Intent(this, target)) }
        fun divider() = items.addView(View(this).apply { setBackgroundColor(getColor(R.color.brand_line)) },
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)).apply { setMargins(dp(24), dp(8), dp(24), dp(8)) })
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
            setTextColor(getColor(R.color.brand_muted))
            setPadding(dp(24), dp(12), dp(20), dp(20))
        })
        panel.setBackgroundColor(getColor(R.color.brand_bg))
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

    /** Section heading, in the brand's display face (Fraunces, as on hebrish.app; 0.10.0). */
    protected fun heading(text: CharSequence, parent: LinearLayout = column) = add(TextView(this).apply {
        this.text = text
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 21f)
        typeface = display(this@Page)
        setTextColor(getColor(R.color.brand_ink))
    }, 28, parent)
    protected fun heading(res: Int, parent: LinearLayout = column) = heading(getString(res), parent)

    protected fun subheading(res: Int, parent: LinearLayout = column) = add(TextView(this).apply {
        setText(res)
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
        typeface = android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL)
        setTextColor(getColor(R.color.brand_ink))
    }, 14, parent)

    protected fun text(text: CharSequence = "", parent: LinearLayout = column, top: Int = 4) =
        add(TextView(this).apply {
            this.text = text
            setTextIsSelectable(false)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
            setLineSpacing(dp(3).toFloat(), 1f)
        }, top, parent)
    protected fun text(res: Int, parent: LinearLayout = column, top: Int = 4) = text(getString(res), parent, top)

    protected fun small(res: Int, parent: LinearLayout = column) = add(TextView(this).apply {
        setText(res)
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
        setTextColor(getColor(R.color.brand_muted))
    }, 4, parent)

    /**
     * A wrap-content button on its own line, or in [parent] (e.g. a [row]). Styled by the theme
     * (AppButton: a soft green pill); buttons in a row get a gap between them.
     */
    protected fun button(res: Int, parent: LinearLayout = column, onClick: () -> Unit) = Button(this).apply {
        setText(res)
        setOnClickListener { onClick() }
        parent.addView(this, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
            if (parent.orientation == LinearLayout.HORIZONTAL && parent.childCount > 0) marginStart = dp(8)
            if (parent.orientation == LinearLayout.VERTICAL) topMargin = dp(6)
        })
    }

    /** Turns [b] into the filled green button (the screen's main action; 0.10.0). */
    protected fun primary(b: Button) = b.apply {
        setBackgroundResource(R.drawable.btn_primary)
        setTextColor(getColor(R.color.brand_accent_ink))
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)
    }

    /** The mark, "Hebrish" in the display face and the tagline: home's top and the side menu's header. */
    protected fun brandHeader(markSize: Int, nameSize: Float): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        addView(ImageView(this@Page).apply { setImageResource(R.drawable.ic_hebrish) }, LinearLayout.LayoutParams(dp(markSize), dp(markSize)))
        val words = LinearLayout(this@Page).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(14), 0, 0, 0) }
        words.addView(TextView(this@Page).apply {
            setText(R.string.app_name)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, nameSize)
            typeface = display(this@Page, 700)
            setTextColor(getColor(R.color.brand_ink))
            includeFontPadding = false
        })
        words.addView(TextView(this@Page).apply {
            setText(R.string.tagline)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            setTextColor(getColor(R.color.brand_muted))
            setPadding(0, dp(3), 0, 0)
        })
        addView(words)
    }

    /**
     * A card that groups [nav] rows (home, 0.10.0): pass it as their parent; rows after the first
     * get a hairline above them.
     */
    protected fun group(parent: LinearLayout = column) = add(LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setBackgroundResource(R.drawable.card_bg)
        clipToOutline = true
    }, 10, parent)

    /** A horizontal line of buttons. */
    protected fun row(parent: LinearLayout = column) = add(LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }, 0, parent)

    protected fun switch(res: Int, get: () -> Boolean, set: (Boolean) -> Unit, parent: LinearLayout = column) = add(Switch(this).apply {
        setText(res)
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
        setPadding(0, dp(6), 0, dp(6))
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

    /**
     * A tappable two-line entry with a chevron that opens another screen; returns the summary line.
     * In a [group] card it is a padded row with a hairline above it (0.10.0).
     */
    protected fun nav(title: Int, summary: TextView.() -> Unit, target: Class<out Activity>, parent: LinearLayout = column): TextView {
        val inCard = parent !== column
        if (inCard && parent.childCount > 0) parent.addView(View(this).apply { setBackgroundColor(getColor(R.color.brand_line)) },
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)).apply { marginStart = dp(16) })
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            val side = if (inCard) dp(16) else 0
            setPadding(side, dp(14), if (inCard) dp(10) else 0, dp(14))
            val out = TypedValue()
            theme.resolveAttribute(android.R.attr.selectableItemBackground, out, true)
            setBackgroundResource(out.resourceId)
            setOnClickListener { startActivity(Intent(this@Page, target)) }
        }
        if (inCard) parent.addView(row, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        else add(row, 2, parent)
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        row.addView(box, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        row.addView(ImageView(this).apply { setImageResource(R.drawable.ic_chevron) }, LinearLayout.LayoutParams(dp(20), dp(20)))
        box.addView(TextView(this).apply {
            setText(title)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            typeface = android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL)
            setTextColor(getColor(R.color.brand_ink))
        })
        return TextView(this).apply {
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            setTextColor(getColor(R.color.brand_muted))
            setPadding(0, dp(2), 0, 0)
            summary()
        }.also { box.addView(it) }
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

    companion object {
        private val faces = HashMap<Int, android.graphics.Typeface>()

        /**
         * Fraunces, the brand's display face (Hebrish-Mgmt/brand/fonts, subset to Latin in
         * assets/fonts; OFL), at [weight]. Headings and the name only; body text stays the system
         * sans. Falls back to the system serif if the font can't be read.
         */
        fun display(ctx: android.content.Context, weight: Int = 600): android.graphics.Typeface = faces.getOrPut(weight) {
            runCatching {
                android.graphics.Typeface.Builder(ctx.assets, "fonts/Fraunces.ttf")
                    .setFontVariationSettings("'wght' $weight, 'opsz' 48").build()
            }.getOrNull() ?: android.graphics.Typeface.create(android.graphics.Typeface.SERIF, android.graphics.Typeface.BOLD)
        }
    }
}
