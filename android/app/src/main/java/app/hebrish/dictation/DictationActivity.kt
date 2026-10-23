package app.hebrish.dictation

import android.content.Intent
import android.widget.TextView
import android.widget.Toast
import app.hebrish.core.OutputStyle
import app.hebrish.core.Recorder
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * How takes behave in both the keyboard and the floating mic: long dictation, type as you go,
 * ALL CAPS; and the transcription history with its CSV export (0.8.1, [History]).
 */
class DictationActivity : Page() {
    private lateinit var historyCount: TextView

    override fun build() {
        heading(R.string.dictation_long_title)
        text(getString(R.string.dictation_long, Recorder.MAX_SEGMENTED_SECONDS / 60))
        switch(R.string.dictation_type_as_you_go, { Prefs.typeAsYouGo(this) }, { Prefs.setTypeAsYouGo(this, it) })
        small(R.string.dictation_type_as_you_go_hint)
        switch(R.string.dictation_all_caps, { OutputStyle.allCaps(this) }, { OutputStyle.setAllCaps(this, it) })
        small(R.string.dictation_all_caps_hint)

        heading(R.string.history_title)
        text(R.string.history_body)
        switch(R.string.history_keep, { Prefs.keepHistory(this) }, { Prefs.setKeepHistory(this, it) })
        historyCount = text("")
        val r = row()
        button(R.string.history_export, r) { export() }
        button(R.string.history_clear, r) { confirmClear() }
        small(R.string.history_export_hint)

        heading(R.string.dictation_speed_title)
        text(R.string.dictation_speed)

        heading(R.string.dictation_missed_title)
        text(R.string.dictation_missed)
    }

    override fun onResume() {
        super.onResume()
        refreshCount()
    }

    private fun refreshCount() {
        historyCount.text = getString(R.string.history_count, History.count(this))
    }

    /** Storage Access Framework: the system picker offers Drive, Downloads, etc. No permission needed. */
    private fun export() {
        if (History.count(this) == 0) return Toast.makeText(this, R.string.history_empty, Toast.LENGTH_SHORT).show()
        val name = "hebrish-history-" + SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date()) + ".csv"
        val pick = Intent(Intent.ACTION_CREATE_DOCUMENT)
            .addCategory(Intent.CATEGORY_OPENABLE)
            .setType("text/csv")
            .putExtra(Intent.EXTRA_TITLE, name)
        try {
            @Suppress("DEPRECATION") startActivityForResult(pick, EXPORT)
        } catch (_: android.content.ActivityNotFoundException) {
            Toast.makeText(this, R.string.history_no_picker, Toast.LENGTH_LONG).show()
        }
    }

    @Deprecated("Activity.onActivityResult")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION") super.onActivityResult(requestCode, resultCode, data)
        val uri = data?.data
        if (requestCode != EXPORT || resultCode != RESULT_OK || uri == null) return
        val app = applicationContext
        Thread {
            val result = runCatching {
                (contentResolver.openOutputStream(uri, "wt") ?: error("no stream")).use { History.writeCsv(app, it) }
            }
            runOnUiThread {
                result.onSuccess { Toast.makeText(this, getString(R.string.history_exported, it), Toast.LENGTH_LONG).show() }
                    .onFailure { Toast.makeText(this, getString(R.string.history_export_failed, it.message ?: it.javaClass.simpleName), Toast.LENGTH_LONG).show() }
            }
        }.start()
    }

    private fun confirmClear() {
        android.app.AlertDialog.Builder(this)
            .setMessage(R.string.history_clear_confirm)
            .setPositiveButton(R.string.history_clear) { _, _ -> History.clear(this); refreshCount() }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private companion object { const val EXPORT = 41 }
}
