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
 * One note ([Notes]): a title, a text box and the in-app mic ([DictationPad], History source `note`).
 * Saves by itself: 800 ms after the last edit, after every take, and when the screen pauses.
 * A note that becomes empty is deleted; a new note is not stored until it has text.
 * Leaving a note with no title asks the title model for one ([Notes.titleLater]); it appears in
 * the title field if the screen is still open, and a title typed by hand is never replaced.
 * Opened from [NotesActivity] with [EXTRA_ID] (absent or 0 = a new note).
 */
class NoteActivity : Activity() {
    private lateinit var title: EditText
    private lateinit var text: EditText
    private lateinit var pad: DictationPad
    private val ui = Handler(Looper.getMainLooper())
    /** The row's id, 0 until the first save. Written only on [Notes.io], so saves stay in order. */
    @Volatile private var id = 0L
    /** What was last handed to [Notes.io], so an unchanged note isn't written again. Main thread. */
    private var lastSaved = "" to ""
    private val saveSoon = Runnable { save() }
    private val onTitled: (Long) -> Unit = { n ->
        if (n == id) Notes.io.execute {
            val t = Notes.get(applicationContext, n)?.title.orEmpty()
            ui.post {
                if (isDestroyed || t.isEmpty() || title.text.isNotBlank()) return@post
                lastSaved = t to lastSaved.second
                title.setText(t)
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_note)
        actionBar?.setDisplayHomeAsUpEnabled(true)
        title = findViewById(R.id.note_title)
        text = findViewById(R.id.note_text)

        // Recreated after rotation or process death: keep the id the first instance got.
        val start = savedInstanceState?.getLong(EXTRA_ID) ?: intent.getLongExtra(EXTRA_ID, 0L)
        if (start != 0L) {
            Notes.get(this, start)?.let {
                id = it.id
                title.setText(it.title)
                text.setText(it.text)
                lastSaved = it.title to it.text
            }
        }

        pad = DictationPad(this, text, findViewById(R.id.note_mic), findViewById(R.id.note_status),
            findViewById(R.id.note_level), findViewById(R.id.note_fix), History.NOTE) {
            save()
            // A take stopped by leaving the screen lands after onStop: title with its text too.
            if (isFinishing || isDestroyed) titleIfNeeded()
        }

        val watcher = object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) = Unit
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) = Unit
            override fun afterTextChanged(s: Editable?) {
                ui.removeCallbacks(saveSoon)
                ui.postDelayed(saveSoon, 800)
            }
        }
        title.addTextChangedListener(watcher)
        text.addTextChangedListener(watcher)
        findViewById<Button>(R.id.note_copy).setOnClickListener { TextOut.copy(this, text.text) }
        findViewById<Button>(R.id.note_share).setOnClickListener { TextOut.share(this, shareText()) }
        findViewById<Button>(R.id.note_delete).setOnClickListener { confirmDelete() }
        if (start == 0L) text.requestFocus()

        pad.init()
    }

    /** Share sends the title as the first line when there is one. */
    private fun shareText(): CharSequence {
        val t = title.text.toString().trim()
        return if (t.isEmpty() || text.text.isBlank()) text.text else "$t\n\n${text.text}"
    }

    /** Hands the note to [Notes.io]: insert, update, or delete when the text was emptied. */
    private fun save() {
        ui.removeCallbacks(saveSoon)
        val now = title.text.toString().trim() to text.text.toString()
        if (now == lastSaved) return
        lastSaved = now
        val app = applicationContext
        Notes.io.execute {
            if (now.second.isBlank()) {
                if (id != 0L) Notes.delete(app, id)
                id = 0L
            } else id = Notes.save(app, id, now.first, now.second)
        }
    }

    /** After the save just queued, title the note if it has none (and the model is there). */
    private fun titleIfNeeded() {
        if (title.text.isNotBlank()) return
        val body = text.text.toString()
        val app = applicationContext
        Notes.io.execute { val n = id; ui.post { Notes.titleLater(app, n, body) } }
    }

    private fun confirmDelete() {
        AlertDialog.Builder(this)
            .setMessage(R.string.note_delete_confirm)
            .setPositiveButton(R.string.note_delete) { _, _ ->
                lastSaved = "" to ""
                title.setText("")
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
        Notes.listeners += onTitled
        pad.onResume()
    }

    override fun onPause() {
        super.onPause()
        Notes.listeners -= onTitled
        pad.onPause()   // stops a take; its text arrives later and saves through onTake
        save()
    }

    override fun onStop() {
        super.onStop()
        // Leaving the note (Back, Home, screen off): the moment to title it. Not on every pause,
        // so a title isn't written from the first sentence of a note still being dictated.
        if (text.text.isNotBlank()) titleIfNeeded()
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
