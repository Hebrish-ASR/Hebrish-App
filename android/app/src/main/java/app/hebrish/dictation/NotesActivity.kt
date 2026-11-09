package app.hebrish.dictation

import android.content.Intent
import android.text.TextUtils
import android.text.format.DateUtils
import android.util.TypedValue
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/**
 * Notes (B-100, 2026-11-09): the list of notes, newest edit first, and New note. Each row opens
 * [NoteActivity]: its title (or first line while it has none), then the first line of the text
 * under a title, the time and the word count. Stored on the phone only ([Notes]); no sync.
 * Titles (B-101): the *Give notes a title* switch and, when the model is missing, where to get it;
 * hidden on phones that can't run the title model ([CleanupStore.title] null).
 */
class NotesActivity : Page() {
    private lateinit var count: TextView
    private lateinit var list: LinearLayout
    private lateinit var titleBox: LinearLayout
    private lateinit var titleLine: TextView
    private lateinit var modelsBtn: Button
    private val onTitled: (Long) -> Unit = { render() }

    override fun build() {
        text(R.string.notes_body)
        val add = primary(Button(this)).apply {
            setText(R.string.notes_new)
            setOnClickListener { startActivity(Intent(this@NotesActivity, NoteActivity::class.java)) }
        }
        column.addView(add, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(56)).apply { topMargin = dp(16) })
        titleBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        column.addView(titleBox, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(12) })
        switch(R.string.notes_titles, { Prefs.noteTitles(this) }, { on -> Prefs.setNoteTitles(this, on); renderTitles() }, titleBox)
        titleLine = TextView(this).apply { setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f); setTextColor(getColor(R.color.brand_muted)) }
        titleBox.addView(titleLine)
        modelsBtn = button(R.string.notes_open_models, titleBox) { startActivity(Intent(this, ModelsActivity::class.java)) }
        count = heading("")
        list = group()
    }

    private fun renderTitles() {
        val e = CleanupStore.title(this)
        titleBox.visibility = if (e == null) android.view.View.GONE else android.view.View.VISIBLE
        if (e == null) return
        val missing = CleanupStore.titleFile(this) == null
        titleLine.text = if (missing) getString(R.string.notes_titles_missing, e.downloadMb) else getString(R.string.notes_titles_ready)
        titleLine.visibility = if (Prefs.noteTitles(this)) android.view.View.VISIBLE else android.view.View.GONE
        modelsBtn.visibility = if (missing && Prefs.noteTitles(this)) android.view.View.VISIBLE else android.view.View.GONE
    }

    override fun onPause() {
        super.onPause()
        Notes.listeners -= onTitled
    }

    override fun onResume() {
        super.onResume()
        Notes.listeners += onTitled
        renderTitles()
        render()
    }

    private fun render() {
        val app = applicationContext
        // Read off the main thread: Notes.io also orders this after a save the note screen just queued.
        Notes.io.execute {
            val notes = Notes.all(app)
            runOnUiThread { if (!isDestroyed) show(notes) }
        }
    }

    private fun show(notes: List<Notes.Note>) {
        count.text = resources.getQuantityString(R.plurals.notes_count, notes.size, notes.size)
        list.removeAllViews()
        if (notes.isEmpty()) {
            list.addView(TextView(this).apply {
                setText(R.string.notes_empty)
                setPadding(dp(16), dp(14), dp(16), dp(14))
                setTextColor(getColor(R.color.brand_muted))
            })
            return
        }
        for (n in notes) {
            if (list.childCount > 0) list.addView(android.view.View(this).apply { setBackgroundColor(getColor(R.color.brand_line)) },
                LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)).apply { marginStart = dp(16) })
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(16), dp(12), dp(16), dp(12))
                val out = TypedValue()
                theme.resolveAttribute(android.R.attr.selectableItemBackground, out, true)
                setBackgroundResource(out.resourceId)
                setOnClickListener {
                    startActivity(Intent(this@NotesActivity, NoteActivity::class.java).putExtra(NoteActivity.EXTRA_ID, n.id))
                }
            }
            val first = n.text.trim().lineSequence().firstOrNull { it.isNotBlank() }?.trim()
            row.addView(TextView(this).apply {
                text = n.title.ifBlank { first ?: getString(R.string.notes_untitled) }
                maxLines = 2
                ellipsize = TextUtils.TruncateAt.END
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
                setTextColor(getColor(R.color.brand_ink))
                if (n.title.isNotBlank()) typeface = android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL)
            })
            if (n.title.isNotBlank() && first != null) row.addView(TextView(this).apply {
                text = first
                maxLines = 1
                ellipsize = TextUtils.TruncateAt.END
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
                setTextColor(getColor(R.color.brand_ink))
                alpha = 0.8f
            })
            val words = Notes.words(n.text)
            val at = DateUtils.getRelativeDateTimeString(this, n.updated, DateUtils.MINUTE_IN_MILLIS, DateUtils.WEEK_IN_MILLIS, 0)
            row.addView(TextView(this).apply {
                text = getString(R.string.notes_row_meta, at, words)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
                setTextColor(getColor(R.color.brand_muted))
                setPadding(0, dp(2), 0, 0)
            })
            list.addView(row, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        }
    }
}
