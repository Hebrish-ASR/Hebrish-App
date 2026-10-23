package app.hebrish.dictation

import android.content.Intent
import android.provider.Settings
import android.text.InputType
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import app.hebrish.core.PersonalDictionary
import java.text.DateFormat
import java.util.Date

/**
 * The personal dictionary (0.9.0, [PersonalDictionary]; rules in shared/personal-dictionary.md):
 * add and remove words, shared with Android's personal dictionary once the voice keyboard is
 * enabled. Daniel, 2026-10-23: "when you enter a custom word, it basically writes to the personal
 * dictionary and you read from it".
 */
class DictionaryActivity : Page() {
    private lateinit var access: TextView
    private lateinit var accessBtn: View
    private lateinit var count: TextView
    private lateinit var list: LinearLayout
    private lateinit var word: EditText
    private lateinit var heard: EditText

    override fun build() {
        text(R.string.dict_body)
        access = text(top = 12)
        accessBtn = button(R.string.dict_enable_keyboard) { startActivity(Intent(this, KeyboardActivity::class.java)) }

        heading(R.string.dict_add)
        word = field(R.string.dict_word_hint)
        heard = field(R.string.dict_heard_hint)
        small(R.string.dict_heard_explain)
        button(R.string.dict_add_button) { add() }

        count = heading("")
        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        column.addView(list)
        button(R.string.dict_open_system) {
            try { startActivity(Intent(Settings.ACTION_USER_DICTIONARY_SETTINGS)) }
            catch (_: android.content.ActivityNotFoundException) { Toast.makeText(this, R.string.dict_no_system_screen, Toast.LENGTH_LONG).show() }
        }
        small(R.string.dict_limits)
    }

    override fun onResume() {
        super.onResume()
        render()
    }

    private fun field(hint: Int) = EditText(this).apply {
        setHint(hint)
        isSingleLine = true
        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        column.addView(this, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
    }

    private fun add() {
        val w = word.text.toString().trim()
        if (w.isEmpty()) return
        val shared = PersonalDictionary.add(this, w, heard.text.toString())
        word.setText("")
        heard.setText("")
        Toast.makeText(this, getString(if (shared) R.string.dict_added_shared else R.string.dict_added_local, w), Toast.LENGTH_SHORT).show()
        render()
    }

    private fun render() {
        val system = PersonalDictionary.readSystem(this)
        val shared = system != null
        access.text = if (shared) getString(R.string.dict_shared)
        else {
            val at = PersonalDictionary.systemReadAt(this)
            if (at > 0) getString(R.string.dict_not_shared_copy, DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(at)))
            else getString(R.string.dict_not_shared)
        }
        accessBtn.visibility = if (shared) View.GONE else View.VISIBLE

        // One row per word: Hebrish's own entries and Android's, merged.
        val own = PersonalDictionary.own(this)
        val sys = system ?: PersonalDictionary.cachedSystem(this)
        val words = (own + sys).groupBy { it.word }.toSortedMap(String.CASE_INSENSITIVE_ORDER)
        count.text = getString(R.string.dict_words, words.size)
        list.removeAllViews()
        if (words.isEmpty()) list.addView(TextView(this).apply { setText(R.string.dict_empty); alpha = 0.75f })
        for ((w, entries) in words) {
            val heardAs = entries.flatMap { it.heard }.distinct()
            val where = when {
                entries.any { it.system } && entries.any { !it.system } -> R.string.dict_from_both
                entries.any { it.system } -> R.string.dict_from_android
                else -> R.string.dict_from_hebrish
            }
            val r = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(6), 0, dp(6)) }
            r.addView(TextView(this).apply {
                text = (if (heardAs.isEmpty()) w else getString(R.string.dict_row_heard, w, heardAs.joinToString(", "))) +
                    "\n" + getString(where)
            }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            // Without access, Android's words can only be removed in Android's own screen.
            if (shared || entries.any { !it.system }) button(R.string.dict_remove, r) { confirmRemove(w, shared) }
            list.addView(r)
        }
    }

    private fun confirmRemove(w: String, shared: Boolean) {
        android.app.AlertDialog.Builder(this)
            .setMessage(getString(if (shared) R.string.dict_remove_confirm_shared else R.string.dict_remove_confirm, w))
            .setPositiveButton(R.string.dict_remove) { _, _ -> PersonalDictionary.remove(this, w); render() }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }
}
