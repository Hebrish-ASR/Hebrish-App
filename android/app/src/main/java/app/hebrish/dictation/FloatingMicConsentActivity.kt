package app.hebrish.dictation

import android.app.Activity
import android.content.Intent
import android.provider.Settings

/**
 * The floating mic's prominent disclosure (0.8.0). Google Play requires apps that are not
 * accessibility tools to say, in the app and before the user turns the service on, what the
 * accessibility API is used for, and to get an explicit accept; the service's
 * android:description doesn't count. Every button that opens Accessibility settings for the
 * floating mic goes through [openSettings], so the disclosure is shown until it is accepted.
 * No thanks just closes it. Shown in both builds; the key-press paragraph differs (play strings).
 */
class FloatingMicConsentActivity : Page() {
    override fun build() {
        text(R.string.consent_intro)
        heading(R.string.consent_reads_title)
        text(R.string.consent_reads)
        heading(R.string.consent_does_title)
        text(R.string.consent_does)
        text(R.string.consent_keys, top = 8)
        heading(R.string.consent_data_title)
        text(R.string.consent_data)
        button(R.string.consent_privacy) { open(Hebrish.PRIVACY) }
        val r = row()
        button(R.string.consent_decline, r) { finish() }
        button(R.string.consent_accept, r) {
            Prefs.setA11yConsent(this, true)
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            finish()
        }
    }

    companion object {
        fun openSettings(from: Activity) =
            if (Prefs.a11yConsent(from)) from.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            else from.startActivity(Intent(from, FloatingMicConsentActivity::class.java))
    }
}
