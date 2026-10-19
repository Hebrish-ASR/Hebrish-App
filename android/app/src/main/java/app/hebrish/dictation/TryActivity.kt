package app.hebrish.dictation

import app.hebrish.core.*
import android.Manifest
import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast

/**
 * "Try it": a notepad with a mic button, so people can hear what the model does before
 * setting it up as a keyboard. Records with [Recorder] and decodes with [Transcriber]
 * directly; no input method is involved.
 */
class TryActivity : Activity() {
    private enum class State { LOADING, IDLE, RECORDING, BUSY }

    private lateinit var text: EditText
    private lateinit var mic: ImageButton
    private lateinit var status: TextView
    private lateinit var level: ProgressBar
    private val ui = Handler(Looper.getMainLooper())
    private var state = State.LOADING
    private var startedAt = 0L

    private val recorder = Recorder(
        onLevel = { v -> ui.post { level.progress = (v * 100).toInt() } },
        onLimit = { ui.post { if (state == State.RECORDING) stopAndTranscribe() } },
    )

    private val tick = object : Runnable {
        override fun run() {
            if (state != State.RECORDING) return
            val s = recorder.seconds
            status.text = getString(R.string.try_listening, s / 60, s % 60, Recorder.MAX_SECONDS)
            ui.postDelayed(this, 250)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_try)
        text = findViewById(R.id.try_text)
        mic = findViewById(R.id.try_mic)
        status = findViewById(R.id.try_status)
        level = findViewById(R.id.try_level)

        mic.setOnClickListener { onMic() }
        findViewById<Button>(R.id.try_copy).setOnClickListener { copy() }
        findViewById<Button>(R.id.try_share).setOnClickListener { share() }
        findViewById<Button>(R.id.try_clear).setOnClickListener { text.setText("") }
        findViewById<Button>(R.id.try_setup).setOnClickListener { finish() }

        // Tapping an example shows it as a toast: something to read aloud, not to paste.
        val examples = findViewById<LinearLayout>(R.id.try_examples)
        for (ex in resources.getStringArray(R.array.try_examples)) {
            examples.addView(TextView(this).apply {
                setText("“$ex”")
                setPadding(0, 6, 0, 6)
                setOnClickListener { Toast.makeText(this@TryActivity, R.string.try_example_toast, Toast.LENGTH_SHORT).show() }
            })
        }

        if (!ModelStore.isReady(this)) {
            setState(State.LOADING, getString(R.string.try_no_model))
            mic.isEnabled = false
            return
        }
        preload()
    }

    override fun onPause() {
        super.onPause()
        if (state == State.RECORDING) stopAndTranscribe()   // never leave the mic open off-screen
    }

    /** The first load reads 650 MB and takes a few seconds; do it before the first tap. */
    private fun preload() {
        if (Transcriber.isLoaded(this)) return setState(State.IDLE, getString(R.string.try_ready))
        setState(State.LOADING, getString(R.string.try_loading))
        Thread {
            val err = runCatching { Transcriber.load(this) }.exceptionOrNull()
            ui.post {
                if (err == null) setState(State.IDLE, getString(R.string.try_ready))
                else setState(State.LOADING, getString(R.string.try_load_failed, err.message ?: "?"))
            }
        }.start()
    }

    private fun onMic() {
        when (state) {
            State.IDLE -> start()
            State.RECORDING -> stopAndTranscribe()
            else -> Unit
        }
    }

    private fun start() {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQ_MIC)
            return
        }
        recorder.start()
        startedAt = SystemClock.elapsedRealtime()
        setState(State.RECORDING, getString(R.string.try_listening, 0, 0, Recorder.MAX_SECONDS))
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        ui.post(tick)
    }

    private fun stopAndTranscribe() {
        val samples = recorder.stop()
        level.progress = 0
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        if (samples.size < Transcriber.SAMPLE_RATE / 3) {
            setState(State.IDLE, getString(R.string.try_too_short))
            return
        }
        setState(State.BUSY, getString(R.string.try_transcribing))
        val t0 = SystemClock.elapsedRealtime()
        Thread {
            val result = runCatching { Transcriber.transcribe(this, samples) }
            val took = (SystemClock.elapsedRealtime() - t0) / 1000f
            val audio = samples.size / Transcriber.SAMPLE_RATE.toFloat()
            ui.post {
                result.onSuccess { said ->
                    if (said.isBlank()) setState(State.IDLE, getString(R.string.try_nothing))
                    else {
                        insert(said)
                        setState(State.IDLE, getString(R.string.try_done, audio, took))
                    }
                }.onFailure { setState(State.IDLE, getString(R.string.try_failed, it.message ?: "?")) }
            }
        }.start()
    }

    /** At the cursor, with a space before it unless the cursor starts a line. */
    private fun insert(said: String) {
        val e = text.text
        val at = text.selectionStart.coerceAtLeast(0)
        val prev = if (at > 0) e[at - 1] else '\n'
        val chunk = if (prev.isWhitespace()) said else " $said"
        e.insert(at, chunk)
        text.setSelection(at + chunk.length)
    }

    private fun setState(s: State, message: String) {
        state = s
        status.text = message
        mic.setImageResource(if (s == State.RECORDING) R.drawable.ic_stop else R.drawable.ic_mic)
        mic.isEnabled = s == State.IDLE || s == State.RECORDING
        mic.alpha = if (mic.isEnabled) 1f else 0.4f
        level.visibility = if (s == State.RECORDING) View.VISIBLE else View.INVISIBLE
        mic.contentDescription = getString(if (s == State.RECORDING) R.string.try_cd_stop else R.string.cd_mic)
    }

    private fun copy() {
        val clip = ClipData.newPlainText(getString(R.string.app_name), text.text)
        (getSystemService(CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(clip)
        Toast.makeText(this, R.string.try_copied, Toast.LENGTH_SHORT).show()
    }

    private fun share() {
        if (text.text.isBlank()) return
        startActivity(Intent.createChooser(
            Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, text.text.toString()),
            getString(R.string.try_share)))
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        if (requestCode == REQ_MIC && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) start()
        else if (requestCode == REQ_MIC) status.setText(R.string.try_need_mic)
    }

    private companion object {
        const val REQ_MIC = 10
    }
}
