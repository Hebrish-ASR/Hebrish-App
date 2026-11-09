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
 * Notes (2026-11-09): the list of notes, newest edit first, and New note. Each row opens
 * [NoteActivity]. Stored on the phone only ([Notes]); no sync.
 */
class NotesActivity : Page() {
    private lateinit var count: TextView
    private lateinit var list: LinearLayout

    override fun build() {
        text(R.string.notes_body)
        val add = primary(Button(this)).apply {
            setText(R.string.notes_new)
            setOnClickListener { startActivity(Intent(this@NotesActivity, NoteActivity::class.java)) }
        }
        column.addView(add, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(56)).apply { topMargin = dp(16) })
        count = heading("")
        list = group()
    }

    override fun onResume() {
        super.onResume()
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
                text = first ?: getString(R.string.notes_untitled)
                maxLines = 2
                ellipsize = TextUtils.TruncateAt.END
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
                setTextColor(getColor(R.color.brand_ink))
            })
            val words = n.text.split(Regex("\\s+")).count { it.isNotEmpty() }
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
