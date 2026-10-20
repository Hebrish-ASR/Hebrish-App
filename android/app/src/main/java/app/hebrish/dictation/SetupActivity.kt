package app.hebrish.dictation

import app.hebrish.core.*
import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.Settings
import android.util.TypedValue
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView

/**
 * The setup checklist (0.6.0, Daniel 2026-10-20: "an orderly setup checklist"): every step a new
 * user has to take, in order, each with its state and a button that goes straight to the right
 * system page. The same steps, with the same ids, are on hebrish.app/setup (`#step-<id>`).
 *
 * Counted as required: microphone, a model, a way to dictate (the voice keyboard or the floating
 * mic), battery unrestricted, and not pausing the app when unused. The floating mic and all-files
 * access are optional. [Checklist] does the counting, so home can show "3 of 5 done".
 */
class SetupActivity : Page() {
    private val steps = mutableListOf<Step>()
    private lateinit var progress: TextView

    private class Step(val id: String, val done: () -> Boolean, val mark: TextView, val actions: View) {
        val normal: android.content.res.ColorStateList = mark.textColors
    }

    override fun build() {
        text(R.string.setup_intro)
        progress = text(top = 8).apply { setTypeface(typeface, android.graphics.Typeface.BOLD) }

        step("mic", R.string.setup_mic_title, R.string.setup_mic, { Setup.hasMic(this) }) { r ->
            button(R.string.setup_mic_button, r) { askMic() }
        }
        step("model", R.string.setup_model_title, R.string.setup_model, { ModelStore.isReady(this) }) { r ->
            button(R.string.setup_model_button, r) { startActivity(Intent(this, ModelsActivity::class.java)) }
        }
        step("keyboard", R.string.setup_keyboard_title, R.string.setup_keyboard, { Setup.imeEnabled(this) }) { r ->
            button(R.string.enable, r) { startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS)) }
            button(R.string.setup_more, r) { startActivity(Intent(this, KeyboardActivity::class.java)) }
        }
        step("floating", R.string.setup_floating_title, R.string.setup_floating, { Setup.bubbleOn(this) }) { r ->
            button(R.string.setup_floating_button, r) { startActivity(Intent(this, FloatingMicGuideActivity::class.java)) }
        }
        step("battery", R.string.setup_battery_title, R.string.setup_battery, { Setup.batteryExempt(this) }) { r ->
            button(R.string.guide_battery_button, r) {
                runCatching {
                    startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
                }.onFailure { startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)) }
            }
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            step("unused", R.string.setup_unused_title, R.string.setup_unused, { Setup.notPausedWhenUnused(this) }) { r ->
                button(R.string.setup_unused_button, r) {
                    runCatching {
                        startActivity(Intent(Intent.ACTION_AUTO_REVOKE_PERMISSIONS, Uri.parse("package:$packageName")))
                    }.onFailure { appInfo() }
                }
            }
            step("files", R.string.setup_files_title, R.string.setup_files, { Environment.isExternalStorageManager() }) { r ->
                button(R.string.setup_files_button, r) {
                    startActivity(Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION, Uri.parse("package:$packageName")))
                }
            }
        }

        heading(R.string.setup_try_title)
        text(R.string.setup_try)
        val r = row()
        button(R.string.try_open, r) { startActivity(Intent(this, TryActivity::class.java)) }
        button(R.string.setup_guide_button, r) { open(Hebrish.SETUP_GUIDE) }
    }

    /** One numbered card: ✓ or the number, title, what and why, and its buttons (hidden once done). */
    private fun step(id: String, title: Int, body: Int, done: () -> Boolean, actions: (LinearLayout) -> Unit) {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundResource(R.drawable.card_bg)
            setPadding(dp(16), dp(12), dp(16), dp(12))
        }
        column.addView(card, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            .apply { topMargin = dp(12) })
        val mark = TextView(this).apply {
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        }
        card.addView(mark)
        mark.tag = getString(title)
        card.addView(TextView(this).apply { setText(body); setPadding(0, dp(4), 0, 0) })
        val r = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        card.addView(r)
        actions(r)
        steps += Step(id, done, mark, r)
    }

    override fun onResume() {
        super.onResume()
        render()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        render()
        if (grantResults.firstOrNull() == PackageManager.PERMISSION_DENIED && !shouldShowRequestPermissionRationale(Manifest.permission.RECORD_AUDIO)) appInfo()
    }

    private fun askMic() {
        // Once refused for good, Android no longer shows the prompt: only App info can grant it.
        if (Prefs.micAsked(this) && !shouldShowRequestPermissionRationale(Manifest.permission.RECORD_AUDIO)) return appInfo()
        Prefs.setMicAsked(this)
        requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1)
    }

    private fun appInfo() = startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))

    private fun render() {
        steps.forEachIndexed { i, s ->
            val done = s.done()
            val optional = s.id in Checklist.OPTIONAL
            s.mark.text = (if (done) "✓  " else "${i + 1}.  ") + s.mark.tag +
                (if (optional) getString(R.string.setup_optional) else "")
            if (done) s.mark.setTextColor(getColor(R.color.hebrish_green)) else s.mark.setTextColor(s.normal)
            s.actions.visibility = if (done) View.GONE else View.VISIBLE
        }
        val (n, of) = Checklist.progress(this)
        progress.text = if (n == of) getString(R.string.setup_all_done) else getString(R.string.setup_progress, n, of)
    }
}

/** What counts towards "set up": shared by the checklist and the home screen. */
object Checklist {
    val OPTIONAL = setOf("floating", "files")

    /** (done, required) over: mic, model, keyboard or floating mic, battery, not paused when unused. */
    fun progress(ctx: android.content.Context): Pair<Int, Int> {
        val checks = listOfNotNull(
            Setup.hasMic(ctx),
            ModelStore.isReady(ctx),
            Setup.imeEnabled(ctx) || Setup.bubbleOn(ctx),
            Setup.batteryExempt(ctx),
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) Setup.notPausedWhenUnused(ctx) else null,
        )
        return checks.count { it } to checks.size
    }
}
