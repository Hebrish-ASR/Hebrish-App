package app.hebrish.dictation

import android.Manifest
import android.content.Intent
import android.provider.Settings
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.TextView

/** The voice keyboard: microphone, turning the keyboard on, HeliBoard, and how it behaves. */
class KeyboardActivity : Page() {
    private lateinit var micStatus: TextView
    private lateinit var micBtn: Button
    private lateinit var imeStatus: TextView
    private lateinit var returnStatus: TextView

    override fun build() {
        text(R.string.keyboard_intro)

        heading(R.string.step_mic)
        micStatus = text()
        micBtn = button(R.string.grant) { Setup.askMic(this, REQ_MIC) }

        heading(R.string.step_ime)
        imeStatus = text()
        val r = row()
        button(R.string.enable, r) { Setup.openSystem(this, Intent(Settings.ACTION_INPUT_METHOD_SETTINGS)) }
        button(R.string.pick, r) { (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker() }

        heading(R.string.step_heliboard)
        text(R.string.heliboard_body)
        button(R.string.get_heliboard) { open(getString(R.string.url_heliboard)) }

        heading(R.string.step_options)
        switch(R.string.auto_start, { Prefs.autoStart(this) }, { Prefs.setAutoStart(this, it) })
        switch(R.string.auto_return, { Prefs.autoReturn(this) }, { Prefs.setAutoReturn(this, it) })
        switch(R.string.back_switches, { Prefs.backSwitches(this) }, { Prefs.setBackSwitches(this, it) })
        subheading(R.string.return_title)
        returnStatus = text()
        button(R.string.return_change) { chooseReturnIme() }
        text(R.string.return_hint)

        heading(R.string.step_try)
        column.addView(EditText(this).apply {
            setHint(R.string.try_hint)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE or
                android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
            minLines = 3
        })
    }

    override fun onResume() {
        super.onResume()
        render()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) = render()

    private fun render() {
        val mic = Setup.hasMic(this)
        micStatus.setText(if (mic) R.string.mic_ok else R.string.mic_missing)
        micBtn.visibility = if (mic) View.GONE else View.VISIBLE
        imeStatus.setText(if (Setup.imeEnabled(this)) R.string.ime_enabled else R.string.ime_disabled)
        val fixed = imeLabel(Prefs.returnIme(this))
        val auto = imeLabel(Prefs.lastOtherIme(this))
        returnStatus.text = when {
            fixed != null -> getString(R.string.return_fixed, fixed)
            auto != null -> getString(R.string.return_auto, auto)
            else -> getString(R.string.return_auto_unknown)
        }
    }

    private fun otherImes() = (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).enabledInputMethodList
        .filter { it.packageName != packageName }

    private fun imeLabel(id: String?) = otherImes().firstOrNull { it.id == id }?.loadLabel(packageManager)?.toString()

    private fun chooseReturnIme() {
        val imes = otherImes()
        val labels = listOf(getString(R.string.return_auto_option)) + imes.map { it.loadLabel(packageManager).toString() }
        val current = imes.indexOfFirst { it.id == Prefs.returnIme(this) } + 1
        android.app.AlertDialog.Builder(this)
            .setTitle(R.string.return_title)
            .setSingleChoiceItems(labels.toTypedArray(), current) { d, which ->
                Prefs.setReturnIme(this, if (which == 0) null else imes[which - 1].id)
                d.dismiss()
                render()
            }
            .show()
    }

    private companion object {
        const val REQ_MIC = 1
    }
}
