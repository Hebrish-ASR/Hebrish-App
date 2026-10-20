package app.hebrish.dictation

import android.Manifest
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.view.View
import android.widget.Button
import android.widget.TextView

/**
 * Step by step: turning on the floating mic. The hard part is Android 13+'s "restricted
 * settings": an app installed from an APK can't be given accessibility until the user allows it
 * from App info, and that menu item only appears after one attempt to turn the service on.
 */
class FloatingMicGuideActivity : Page() {
    private lateinit var status: TextView
    private lateinit var micStep: List<View>

    override fun build() {
        status = text()

        heading(R.string.guide_step1_title)
        text(R.string.guide_step1)
        button(R.string.bubble_enable) { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            heading(R.string.guide_step2_title)
            text(R.string.guide_step2)
            button(R.string.bubble_app_info) {
                startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
            }
            heading(R.string.guide_step3_title)
            text(R.string.guide_step3)
            button(R.string.bubble_enable) { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
        }

        val micTitle = heading(R.string.guide_mic_title)
        val micText = text(R.string.guide_mic)
        val micBtn: Button = button(R.string.grant) { requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1) }
        micStep = listOf(micTitle, micText, micBtn)

        heading(R.string.guide_done_title)
        text(R.string.guide_done)
        button(R.string.guide_position) { finish() }
    }

    override fun onResume() {
        super.onResume()
        render()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) = render()

    private fun render() {
        status.setText(if (Setup.bubbleOn(this)) R.string.guide_status_on else R.string.guide_status_off)
        val mic = Setup.hasMic(this)
        for (v in micStep) v.visibility = if (mic) View.GONE else View.VISIBLE
    }
}
