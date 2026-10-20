package app.hebrish.dictation

import app.hebrish.core.*
import android.Manifest
import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import android.view.View
import android.view.accessibility.AccessibilityManager
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.TextView

/**
 * Home: what's set up, a big Try button, and the way to each area's own screen (models, voice
 * keyboard, floating mic, dictation, install and updates, help and contact).
 */
class MainActivity : Page() {
    private lateinit var version: TextView
    private lateinit var tryBtn: Button
    private lateinit var micLine: TextView
    private lateinit var micBtn: Button
    private lateinit var modelsSummary: TextView
    private lateinit var keyboardSummary: TextView
    private lateinit var bubbleSummary: TextView

    override fun build() {
        text(R.string.intro)
        version = text()
        tryBtn = Button(this).apply {
            backgroundTintList = android.content.res.ColorStateList.valueOf(getColor(R.color.accent))
            setTextColor(0xFFFFFFFF.toInt())
            textSize = 17f
            setOnClickListener {
                if (ModelStore.isReady(this@MainActivity)) startActivity(Intent(this@MainActivity, TryActivity::class.java))
                else startActivity(Intent(this@MainActivity, ModelsActivity::class.java))
            }
        }
        column.addView(tryBtn, android.widget.LinearLayout.LayoutParams(
            android.widget.LinearLayout.LayoutParams.MATCH_PARENT, dp(64)).apply { topMargin = dp(16) })
        text(R.string.try_open_hint).gravity = android.view.Gravity.CENTER

        micLine = text(R.string.mic_missing, top = 16)
        micBtn = button(R.string.grant) { requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQ_MIC) }

        heading(R.string.home_setup)
        modelsSummary = nav(R.string.nav_models, {}, ModelsActivity::class.java)
        keyboardSummary = nav(R.string.nav_keyboard, {}, KeyboardActivity::class.java)
        bubbleSummary = nav(R.string.nav_bubble, {}, FloatingMicActivity::class.java)
        nav(R.string.nav_dictation, { setText(R.string.nav_dictation_summary) }, DictationActivity::class.java)
        heading(R.string.home_more)
        nav(R.string.nav_install, { setText(R.string.nav_install_summary) }, InstallActivity::class.java)
        nav(R.string.nav_contact, { setText(R.string.nav_contact_summary) }, ContactActivity::class.java)
    }

    override fun onResume() {
        super.onResume()
        ModelDownload.listener = { render() }
        noteDefaultIme()
        ModelDownload.check(this)
        render()
    }

    override fun onPause() {
        super.onPause()
        ModelDownload.listener = null
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        render()
        if (grantResults.firstOrNull() == PackageManager.PERMISSION_DENIED && !shouldShowRequestPermissionRationale(Manifest.permission.RECORD_AUDIO)) {
            // Permanently denied: only the app settings page can grant it now.
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
        }
    }

    private fun render() {
        val model = Catalogue.selected(this)
        val installed = ModelStore.installed(this, model)
        val ready = ModelStore.isReady(this)
        version.text = if (installed != null)
            getString(R.string.version_line, versionName(), model.name, installed.version, installed.revision.take(12))
        else getString(R.string.version_line_none, versionName(), model.name)
        tryBtn.setText(if (ready) R.string.try_open else R.string.try_open_no_model)

        val mic = Setup.hasMic(this)
        micLine.visibility = if (mic) View.GONE else View.VISIBLE
        micBtn.visibility = if (mic) View.GONE else View.VISIBLE

        val s = ModelDownload.status
        val others = ModelStore.readyModels(this).count { it.id != model.id }
        modelsSummary.text = when {
            s is ModelDownload.Status.Running && !ModelDownload.moving -> getString(R.string.home_models_downloading,
                ModelDownload.target?.first?.name ?: "", s.done / 1_000_000, s.total / 1_000_000)
            ready -> getString(R.string.home_models_ready, model.name, installed!!.version) +
                (if (others > 0) getString(R.string.home_models_others, others) else "") +
                (if (ModelDownload.updateAvailable(this) != null) getString(R.string.home_models_update) else "")
            else -> getString(R.string.home_models_missing, model.name)
        }
        keyboardSummary.setText(if (Setup.imeEnabled(this)) R.string.home_keyboard_on else R.string.home_keyboard_off)
        bubbleSummary.setText(if (Setup.bubbleOn(this)) R.string.home_bubble_on else R.string.home_bubble_off)
    }

    /**
     * The IME service can't see which keyboard it was opened from, but the system default is
     * readable here. When the app opens it is usually the user's regular keyboard: remember it
     * as a fallback target for VoiceImeService.switchBack.
     */
    private fun noteDefaultIme() {
        val id = Settings.Secure.getString(contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD) ?: return
        if (!id.startsWith("$packageName/")) Prefs.setLastOtherIme(this, id)
    }

    private companion object {
        const val REQ_MIC = 1
    }
}

/** Setup state shared by the screens. */
object Setup {
    fun hasMic(ctx: Context) = ctx.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    fun imeEnabled(ctx: Context) = (ctx.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager)
        .enabledInputMethodList.any { it.packageName == ctx.packageName }

    fun batteryExempt(ctx: Context) = (ctx.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager)
        .isIgnoringBatteryOptimizations(ctx.packageName)

    fun bubbleOn(ctx: Context) = (ctx.getSystemService(Context.ACCESSIBILITY_SERVICE) as AccessibilityManager)
        .getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
        .any { it.resolveInfo.serviceInfo.packageName == ctx.packageName && it.resolveInfo.serviceInfo.name == FloatingMicService::class.java.name }
}
