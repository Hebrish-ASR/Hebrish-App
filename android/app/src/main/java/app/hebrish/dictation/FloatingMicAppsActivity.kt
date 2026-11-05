package app.hebrish.dictation

import android.content.Intent
import android.graphics.drawable.Drawable
import android.text.Editable
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.widget.CheckBox
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import kotlin.concurrent.thread

/**
 * "Hide in these apps" (B-90, Daniel 2026-11-05): tick the apps the idle floating mic should stay
 * hidden in. Each tick writes Prefs.bubbleHiddenApps and the service applies it at once. Lists apps
 * with a launcher icon (the `<queries>` entry in the manifest), ticked ones first; icons load off the
 * main thread because a phone can have hundreds.
 */
class FloatingMicAppsActivity : Page() {
    private class App(val pkg: String, val label: String, val icon: Drawable)

    override fun build() {
        text(R.string.bubble_apps_intro)
        val filter = EditText(this).apply { setHint(R.string.bubble_apps_filter); setSingleLine() }
        column.addView(filter)
        val loading = text(R.string.bubble_apps_loading, top = 12)
        val list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        column.addView(list)

        thread {
            val apps = launchableApps()
            runOnUiThread {
                if (isDestroyed) return@runOnUiThread
                loading.visibility = View.GONE
                val rows = apps.map { it to row(it).also(list::addView) }
                filter.addTextChangedListener(object : TextWatcher {
                    override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) = Unit
                    override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) = Unit
                    override fun afterTextChanged(s: Editable?) {
                        val q = s.toString().trim()
                        for ((app, v) in rows) v.visibility = if (app.label.contains(q, ignoreCase = true)) View.VISIBLE else View.GONE
                    }
                })
            }
        }
    }

    private fun launchableApps(): List<App> {
        val hidden = Prefs.bubbleHiddenApps(this)
        return packageManager.queryIntentActivities(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER), 0)
            .distinctBy { it.activityInfo.packageName }
            .filter { it.activityInfo.packageName != packageName }
            .map { App(it.activityInfo.packageName, it.loadLabel(packageManager).toString(), it.loadIcon(packageManager)) }
            .sortedWith(compareBy<App> { it.pkg !in hidden }.thenBy(String.CASE_INSENSITIVE_ORDER) { it.label })
    }

    private fun row(app: App) = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        setPadding(0, dp(6), 0, dp(6))
        addView(ImageView(this@FloatingMicAppsActivity).apply {
            setImageDrawable(app.icon)
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }, LinearLayout.LayoutParams(dp(36), dp(36)).apply { marginEnd = dp(12) })
        addView(CheckBox(this@FloatingMicAppsActivity).apply {
            text = app.label
            isChecked = app.pkg in Prefs.bubbleHiddenApps(this@FloatingMicAppsActivity)
            setOnCheckedChangeListener { _, on -> Prefs.setBubbleHiddenApp(this@FloatingMicAppsActivity, app.pkg, on) }
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
    }
}
