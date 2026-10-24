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
 * keyboard, floating mic, dictation, sound / microphone / buttons, install and updates, help and contact).
 */
class MainActivity : Page() {
    private lateinit var version: TextView
    private lateinit var tryBtn: Button
    private lateinit var micLine: TextView
    private lateinit var micBtn: Button
    private lateinit var modelsSummary: TextView
    private lateinit var keyboardSummary: TextView
    private lateinit var bubbleSummary: TextView
    private lateinit var setupSummary: TextView
    private lateinit var versionShort: TextView

    override fun build() {
        // Home (0.10.0): the brand header replaces the bar's title; the rows sit in cards.
        title = ""
        column.addView(brandHeader(markSize = 52, nameSize = 30f), android.widget.LinearLayout.LayoutParams(
            android.widget.LinearLayout.LayoutParams.MATCH_PARENT, android.widget.LinearLayout.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(4) })
        text(R.string.intro_home, top = 16)
        tryBtn = primary(Button(this)).apply {
            setOnClickListener {
                if (ModelStore.isReady(this@MainActivity)) startActivity(Intent(this@MainActivity, TryActivity::class.java))
                else startActivity(Intent(this@MainActivity, ModelsActivity::class.java))
            }
        }
        column.addView(tryBtn, android.widget.LinearLayout.LayoutParams(
            android.widget.LinearLayout.LayoutParams.MATCH_PARENT, dp(60)).apply { topMargin = dp(20) })
        small(R.string.try_open_hint).gravity = android.view.Gravity.CENTER
        nav(R.string.title_transcription, { setText(R.string.nav_transcription_summary) }, TranscriptionActivity::class.java, group().also {
            (it.layoutParams as android.view.ViewGroup.MarginLayoutParams).topMargin = dp(16)
        })

        micLine = text(R.string.mic_missing, top = 16)
        micBtn = button(R.string.grant) { requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQ_MIC) }

        setupSummary = nav(R.string.title_setup, {}, SetupActivity::class.java, group().also {
            (it.layoutParams as android.view.ViewGroup.MarginLayoutParams).topMargin = dp(20)
        })

        heading(R.string.home_setup)
        val setup = group()
        modelsSummary = nav(R.string.nav_models, {}, ModelsActivity::class.java, setup)
        keyboardSummary = nav(R.string.nav_keyboard, {}, KeyboardActivity::class.java, setup)
        bubbleSummary = nav(R.string.nav_bubble, {}, FloatingMicActivity::class.java, setup)
        nav(R.string.nav_dictation, { setText(R.string.nav_dictation_summary) }, DictationActivity::class.java, setup)
        nav(R.string.nav_dictionary, { setText(R.string.nav_dictionary_summary) }, DictionaryActivity::class.java, setup)
        nav(R.string.nav_controls, { setText(R.string.nav_controls_summary) }, ControlsActivity::class.java, setup)
        heading(R.string.home_more)
        val more = group()
        if (Channel.installScreen) nav(R.string.nav_install, { setText(R.string.nav_install_summary) }, InstallActivity::class.java, more)
        nav(R.string.nav_contact, { setText(R.string.nav_contact_summary) }, ContactActivity::class.java, more)
        nav(R.string.title_about, { setText(R.string.nav_about_summary) }, AboutActivity::class.java, more)

        // The version, at the bottom (Daniel, 2026-10-20); the detailed line is for bug reports.
        versionShort = text(top = 32).apply { gravity = android.view.Gravity.CENTER; textSize = 13f; setTextColor(getColor(R.color.brand_muted)) }
        version = text().apply { gravity = android.view.Gravity.CENTER; textSize = 11f; setTextColor(getColor(R.color.brand_muted)); alpha = 0.8f }
    }

    override fun onResume() {
        super.onResume()
        ModelDownload.listener = { render() }
        noteDefaultIme()
        retireModelLocation()
        ModelDownload.check(this)
        render()
    }

    /**
     * The custom model location was retired in 0.8.0 (all-files access is gone from the manifest,
     * on the way to Google Play compliance). An install that still points at a shared folder moves
     * back to app storage: ModelDownload.relocate copies whatever is still readable there and,
     * if nothing is (Android revokes the permission when the update removes it), just switches,
     * so the models download again. (I: the revoke-on-update behaviour is not verified on a device.)
     */
    private fun retireModelLocation() {
        if (ModelPrefs.modelRoot(this) != null) ModelDownload.relocate(this, null)
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
        // Pin the model in use once one is ready, so a later catalogue change can't move it.
        if (ready && ModelPrefs.selectedModel(this) == null) ModelPrefs.setSelectedModel(this, model.id)
        versionShort.text = versionSummary()
        val (done, of) = Checklist.progress(this)
        setupSummary.text = if (done == of) getString(R.string.setup_all_done) else getString(R.string.setup_progress_home, done, of)
        version.text = if (installed != null)
            getString(R.string.version_line, versionName(), model.name, installed.label)
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
            ready -> getString(R.string.home_models_ready, model.name, installed!!.label) +
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

    /**
     * Asks for the microphone. Once it has been refused for good, Android no longer shows the
     * prompt and only App info can grant it, so that opens instead. Used by every Grant button
     * (Setup, the keyboard page, the floating mic guide); before 0.7.5 only Setup did this.
     */
    fun askMic(a: android.app.Activity, requestCode: Int = 1) {
        if (Prefs.micAsked(a) && !a.shouldShowRequestPermissionRationale(Manifest.permission.RECORD_AUDIO)) return appInfo(a)
        Prefs.setMicAsked(a)
        a.requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), requestCode)
    }

    fun appInfo(ctx: Context) = ctx.startActivity(
        android.content.Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS, android.net.Uri.parse("package:${ctx.packageName}")))

    fun imeEnabled(ctx: Context) = (ctx.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager)
        .enabledInputMethodList.any { it.packageName == ctx.packageName }

    fun batteryExempt(ctx: Context) = (ctx.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager)
        .isIgnoringBatteryOptimizations(ctx.packageName)

    /** Android 11+: true once "Pause app activity if unused" is off, so the mic permission is never auto-revoked. */
    fun notPausedWhenUnused(ctx: Context) =
        android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.R || ctx.packageManager.isAutoRevokeWhitelisted

    fun bubbleOn(ctx: Context) = (ctx.getSystemService(Context.ACCESSIBILITY_SERVICE) as AccessibilityManager)
        .getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
        .any { it.resolveInfo.serviceInfo.packageName == ctx.packageName && it.resolveInfo.serviceInfo.name == FloatingMicService::class.java.name }
}
