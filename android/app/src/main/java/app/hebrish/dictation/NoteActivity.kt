package app.hebrish.dictation

import android.app.Activity
import android.app.AlertDialog
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.Editable
import android.text.TextWatcher
import android.view.MenuItem
import android.widget.Button
import android.widget.EditText

/**
 * One note ([Notes]): a text box with the in-app mic ([DictationPad], History source `note`).
 * Saves by itself: 800 ms after the last edit, after every take, and when the screen pauses.
 * A note that becomes empty is deleted; a new note is not stored until it has text.
 * Opened from [NotesActivity] with [EXTRA_ID] (absent or 0 = a new note).
 */
class NoteActivity : Activity() {
    private lateinit var text: EditText
    private lateinit var pad: DictationPad
    private val ui = Handler(Looper.getMainLooper())
    /** The row's id, 0 until the first save. Read and written only on [Notes.io], so saves stay in order. */
    private var id = 0L
    /** What was last handed to [Notes.io], so an unchanged box isn't written again. Main thread. */
    private var lastSaved = ""
    private val saveSoon = Runnable { save() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_note)
        actionBar?.setDisplayHomeAsUpEnabled(true)
        text = findViewById(R.id.note_text)

        // Recreated after rotation or process death: keep the id the first instance got.
        val start = savedInstanceState?.getLong(EXTRA_ID) ?: intent.getLongExtra(EXTRA_ID, 0L)
        if (start != 0L) {
            Notes.get(this, start)?.let {
                id = it.id
                text.setText(it.text)
                lastSaved = it.text
            }
        }

        pad = DictationPad(this, text, findViewById(R.id.note_mic), findViewById(R.id.note_status),
            findViewById(R.id.note_level), findViewById(R.id.note_fix), History.NOTE) { save() }

        text.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) = Unit
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) = Unit
            override fun afterTextChanged(s: Editable?) {
                ui.removeCallbacks(saveSoon)
                ui.postDelayed(saveSoon, 800)
            }
        })
        findViewById<Button>(R.id.note_copy).setOnClickListener { TextOut.copy(this, text.text) }
        findViewById<Button>(R.id.note_share).setOnClickListener { TextOut.share(this, text.text) }
        findViewById<Button>(R.id.note_delete).setOnClickListener { confirmDelete() }
        if (start == 0L) text.requestFocus()

        pad.init()
    }

    /** Hands the box's text to [Notes.io]: insert, update, or delete when it was emptied. */
    private fun save() {
        ui.removeCallbacks(saveSoon)
        val t = text.text.toString()
        if (t == lastSaved) return
        lastSaved = t
        val app = applicationContext
        Notes.io.execute {
            if (t.isBlank()) {
                if (id != 0L) Notes.delete(app, id)
                id = 0L
            } else id = Notes.save(app, id, t)
        }
    }

    private fun confirmDelete() {
        AlertDialog.Builder(this)
            .setMessage(R.string.note_delete_confirm)
            .setPositiveButton(R.string.note_delete) { _, _ ->
                lastSaved = ""
                text.setText("")
                ui.removeCallbacks(saveSoon)   // the watcher just queued one
                val app = applicationContext
                Notes.io.execute { if (id != 0L) Notes.delete(app, id); id = 0L }
                finish()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == android.R.id.home) { finish(); return true }
        return super.onOptionsItemSelected(item)
    }

    override fun onResume() {
        super.onResume()
        pad.onResume()
    }

    override fun onPause() {
        super.onPause()
        pad.onPause()   // stops a take; its text arrives later and saves through onTake
        save()
    }

    override fun onSaveInstanceState(out: Bundle) {
        super.onSaveInstanceState(out)
        // id is written on Notes.io; wait for pending saves so the restored screen updates the same row.
        out.putLong(EXTRA_ID, Notes.io.submit<Long> { id }.get())
    }

    override fun onDestroy() {
        ui.removeCallbacks(saveSoon)
        pad.onDestroy()
        super.onDestroy()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        pad.onPermissionResult(requestCode, grantResults)
    }

    companion object {
        const val EXTRA_ID = "note_id"
    }
}
