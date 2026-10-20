package app.hebrish.dictation

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.net.Uri
import android.widget.Toast

/**
 * Install and updates: the Hebrish F-Droid repository (the way to get updates automatically),
 * for people who installed the APK directly. Same values as hebrish.app/download#fdroid.
 */
class InstallActivity : Page() {
    override fun build() {
        text(getString(R.string.install_version, versionName()))

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
        button(R.string.install_copy_repo, r) { copy(Hebrish.FDROID_REPO) }
        button(R.string.install_copy_fingerprint, r) { copy(Hebrish.FDROID_FINGERPRINT) }

        heading(R.string.install_apk_title)
        text(R.string.install_apk)
        button(R.string.install_get_apk) { open(Hebrish.APK) }
        button(R.string.install_web) { open(Hebrish.DOWNLOAD_PAGE) }
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

    private fun copy(text: String) {
        getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText(getString(R.string.app_name), text))
        Toast.makeText(this, R.string.try_copied, Toast.LENGTH_SHORT).show()
    }
}
