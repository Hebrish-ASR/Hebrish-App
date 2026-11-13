package app.hebrish.dictation

import android.content.Intent
import android.net.Uri
import android.widget.Toast

/**
 * Install and updates: the Hebrish F-Droid repository (the way to get updates automatically),
 * for people who installed the APK directly. Same values as hebrish.app/download#fdroid.
 */
class InstallActivity : Page() {
    private lateinit var permissionNote: android.widget.TextView
    private lateinit var allowBtn: android.widget.Button
    private lateinit var autoSwitch: android.widget.Switch
    private lateinit var checkBtn: android.widget.Button
    private lateinit var checkStatus: android.widget.TextView
    /** Set while [refresh] moves the switch, so that isn't taken as the user's choice. */
    private var refreshing = false

    override fun build() {
        text(getString(R.string.install_version, versionName()))

        // B-106: automatic updates (this screen exists only in the `fdroid` build, Channel.installScreen).
        if (Channel.selfUpdate) {
            heading(R.string.appupdate_title)
            text(R.string.appupdate_intro)
            permissionNote = text(R.string.appupdate_not_allowed, top = 8)
            allowBtn = button(R.string.appupdate_allow) { Setup.openSystem(this, AppUpdates.permissionIntent(this), Setup.appInfoIntent(this)) }
            autoSwitch = switch(R.string.appupdate_switch, { AppUpdates.backgroundOn(this) }, {
                if (!refreshing) {
                    Prefs.setAppAutoUpdate(this, it)
                    UpdateJobs.sync(this)
                }
            })
            checkBtn = button(R.string.appupdate_check) { checkNow() }
            checkStatus = text(top = 4)
        }

        heading(R.string.install_fdroid_title)
        text(R.string.install_fdroid_why)
        subheading(R.string.install_step1)
        button(R.string.install_get_fdroid) { open(Hebrish.FDROID_APP) }
        subheading(R.string.install_step2)
        button(R.string.install_add_repo) { addRepo() }
        subheading(R.string.install_step3)
        text(R.string.install_step3_body)

        heading(R.string.install_manual_title)
        text(R.string.install_manual)
        text(Hebrish.FDROID_REPO, top = 8).setTextIsSelectable(true)
        text(R.string.install_fingerprint, top = 8)
        text(Hebrish.FDROID_FINGERPRINT.chunked(2).joinToString(" "), top = 2).apply {
            setTextIsSelectable(true)
            typeface = android.graphics.Typeface.MONOSPACE
            textSize = 12f
        }
        val r = row()
        button(R.string.install_copy_repo, r) { TextOut.copy(this, Hebrish.FDROID_REPO) }
        button(R.string.install_copy_fingerprint, r) { TextOut.copy(this, Hebrish.FDROID_FINGERPRINT) }

        heading(R.string.install_apk_title)
        text(R.string.install_apk)
        button(R.string.install_get_apk) { open(Hebrish.APK) }
        button(R.string.install_web) { open(Hebrish.DOWNLOAD_PAGE) }
    }

    override fun onResume() {
        super.onResume()
        if (!Channel.selfUpdate) return
        AppUpdates.listener = { msg -> checkStatus.text = msg }
        refresh()
    }

    override fun onPause() {
        super.onPause()
        if (Channel.selfUpdate) AppUpdates.listener = null
    }

    /** Permission state, switch and button follow "Install unknown apps" (the user may have just changed it). */
    private fun refresh() {
        val ok = AppUpdates.permitted(this)
        permissionNote.visibility = if (ok) android.view.View.GONE else android.view.View.VISIBLE
        allowBtn.visibility = permissionNote.visibility
        autoSwitch.isEnabled = ok
        refreshing = true
        autoSwitch.isChecked = AppUpdates.backgroundOn(this)
        refreshing = false
        UpdateJobs.sync(this)
    }

    /** The background path in the foreground: result on [checkStatus]. */
    private fun checkNow() {
        checkBtn.isEnabled = false
        checkStatus.setText(R.string.appupdate_checking)
        val app = applicationContext
        Thread {
            val o = AppUpdates.run(app, manual = true)
            runOnUiThread {
                checkBtn.isEnabled = true
                // An install in progress keeps its own messages (AppUpdates.say, AppUpdateReceiver).
                if (o.kind != AppUpdates.Kind.INSTALLING) checkStatus.text = AppUpdates.describe(this, o)
                if (o.kind == AppUpdates.Kind.NEEDS_PERMISSION) refresh()
            }
        }.start()
    }

    /**
     * F-Droid (and Droid-ify, Neo Store) handle the `fdroidrepos://` scheme directly; if none is
     * installed, the https link opens hebrish.app's repository page in the browser instead.
     */
    private fun addRepo() {
        val q = "?fingerprint=${Hebrish.FDROID_FINGERPRINT}"
        val direct = Intent(Intent.ACTION_VIEW, Uri.parse(Hebrish.FDROID_REPO.replace("https://", "fdroidrepos://") + q))
        try { startActivity(direct) } catch (_: android.content.ActivityNotFoundException) {
            Toast.makeText(this, R.string.install_no_fdroid, Toast.LENGTH_LONG).show()
            open(Hebrish.FDROID_REPO + q)
        }
    }
}
