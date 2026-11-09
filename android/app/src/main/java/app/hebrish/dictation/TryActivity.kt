package app.hebrish.dictation

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

/**
 * "Try it": a notepad with a mic button, so people can hear what the model does before
 * setting it up as a keyboard. The mic, model load and status line are [DictationPad]
 * (shared with Notes since 2026-11-09); this screen adds the examples and the way to setup.
 */
class TryActivity : Activity() {
    private lateinit var text: EditText
    private lateinit var pad: DictationPad

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_try)
        text = findViewById(R.id.try_text)
        pad = DictationPad(this, text, findViewById(R.id.try_mic), findViewById(R.id.try_status),
            findViewById(R.id.try_level), findViewById(R.id.try_fix), History.TRY)

        findViewById<Button>(R.id.try_copy).setOnClickListener { TextOut.copy(this, text.text) }
        findViewById<Button>(R.id.try_share).setOnClickListener { TextOut.share(this, text.text) }
        findViewById<Button>(R.id.try_clear).setOnClickListener { text.setText("") }
        // Up to 1.008 this only closed the screen, which from home left the user where they started.
        findViewById<Button>(R.id.try_setup).setOnClickListener {
            startActivity(Intent(this, SetupActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP))
            finish()
        }

        // Tapping an example shows it as a toast: something to read aloud, not to paste.
        val examples = findViewById<LinearLayout>(R.id.try_examples)
        for (ex in resources.getStringArray(R.array.try_examples)) {
            examples.addView(TextView(this).apply {
                setText("“$ex”")
                (6 * resources.displayMetrics.density).toInt().let { setPadding(0, it, 0, it) }
                setOnClickListener { Toast.makeText(this@TryActivity, R.string.try_example_toast, Toast.LENGTH_SHORT).show() }
            })
        }

        pad.init()
    }

    override fun onResume() {
        super.onResume()
        pad.onResume()
    }

    override fun onPause() {
        super.onPause()
        pad.onPause()
    }

    override fun onDestroy() {
        pad.onDestroy()
        super.onDestroy()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        pad.onPermissionResult(requestCode, grantResults)
    }
}
