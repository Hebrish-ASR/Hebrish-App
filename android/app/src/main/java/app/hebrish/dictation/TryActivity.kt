package app.hebrish.dictation

import app.hebrish.core.*
import android.Manifest
import android.app.Activity
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
 * setting it up as a keyboard. Records with [Recorder] and decodes with [TakeDecoder]
 * directly; no input method is involved. Text appears segment by segment while you talk
 * (always "type as you go" here), and the status line reports the wait after Stop.
 */
class TryActivity : Activity() {
    private enum class State { LOADING, IDLE, RECORDING, BUSY }

    private lateinit var text: EditText
    private lateinit var mic: ImageButton
    private lateinit var status: TextView
    private lateinit var level: ProgressBar
    /** Under the status line, only when the screen would otherwise be stuck: Open Models, or Try again. */
    private lateinit var fix: Button
    private val ui = Handler(Looper.getMainLooper())
    private var state = State.LOADING
    private var startedAt = 0L
    private var decoder: TakeDecoder? = null

    private val recorder = Recorder(
        onLevel = { v -> ui.post { level.progress = (v * 100).toInt() } },
        onLimit = { ui.post { if (state == State.RECORDING) stopAndTranscribe() } },
        onSegment = { decoder?.add(it) },
    )

    private val tick = object : Runnable {
        override fun run() {
            if (state != State.RECORDING) return
            val s = recorder.seconds
            status.text = getString(R.string.try_listening, s / 60, s % 60) + "\n" + micName
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
        fix = findViewById(R.id.try_fix)

        mic.setOnClickListener { onMic() }
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

        if (!ModelStore.isReady(this)) return showNoModel()
        preload()
    }

    /** Set while the screen waits for a model: coming back from Models with one loads it. */
    private var noModel = false

    private fun showNoModel() {
        noModel = true
        setState(State.LOADING, getString(R.string.try_no_model))
        showFix(R.string.try_open_models) { startActivity(Intent(this, ModelsActivity::class.java)) }
    }

    override fun onResume() {
        super.onResume()
        if (noModel && ModelStore.isReady(this)) {
            noModel = false
            preload()
        }
    }

    private fun showFix(label: Int, action: () -> Unit) {
        fix.setText(label)
        fix.setOnClickListener { action() }
        fix.visibility = View.VISIBLE
    }

    /** The mic this take records from (Mic.label), under the timer. */
    private var micName = ""

    override fun onPause() {
        super.onPause()
        if (state == State.RECORDING) stopAndTranscribe()   // never leave the mic open off-screen
    }

    override fun onDestroy() {
        decoder?.cancel()
        super.onDestroy()
    }

    /** The first load reads 650 MB and takes a few seconds; do it before the first tap. */
    private fun preload() {
        fix.visibility = View.GONE
        if (Transcriber.isLoaded(this)) return setState(State.IDLE, getString(R.string.try_ready))
        setState(State.LOADING, getString(R.string.try_loading))
        val app = applicationContext   // the load takes seconds: don't hold the screen meanwhile
        Thread {
            val err = runCatching { Transcriber.load(app) }.exceptionOrNull()
            ui.post {
                if (isDestroyed) return@post
                if (err == null) setState(State.IDLE, getString(R.string.try_ready))
                else {
                    setState(State.LOADING, getString(R.string.try_load_failed, err.message ?: "?"))
                    showFix(R.string.try_again) { preload() }
                }
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
        decoder = TakeDecoder(this) { said -> ui.post { insert(said) } }
        Mic.prepare(this, recorder)
        try {
            recorder.start()
        } catch (e: Exception) {
            // Mic busy (a call, another recorder): say so, as the keyboard does, instead of crashing.
            Mic.release(this)
            decoder?.cancel()
            decoder = null
            setState(State.IDLE, getString(R.string.ime_mic_error, e.message ?: "?"))
            return
        }
        Feedback.cue(this, Feedback.Cue.START)
        micName = Mic.label(this, recorder.routedDevice)
        startedAt = SystemClock.elapsedRealtime()
        setState(State.RECORDING, getString(R.string.try_listening, 0, 0))
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        ui.post(tick)
    }

    private fun stopAndTranscribe() {
        val audio = recorder.samples / Transcriber.SAMPLE_RATE.toFloat()
        val samples = recorder.stop()
        Mic.release(this)
        Feedback.cue(this, Feedback.Cue.STOP)
        val d = decoder ?: return
        decoder = null
        level.progress = 0
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        if (samples.size < Transcriber.SAMPLE_RATE / 3 && d.segmentsQueued == 0) {
            d.cancel()
            setState(State.IDLE, getString(R.string.try_too_short))
            return
        }
        setState(State.BUSY, getString(R.string.try_transcribing))
        val t0 = SystemClock.elapsedRealtime()
        val before = text.text.length
        d.finish(samples) { result ->
            val took = (SystemClock.elapsedRealtime() - t0) / 1000f
            ui.post {
                result.onSuccess { said ->
                    if (said.isNotBlank()) insert(said)
                    History.record(this, d.text, d.stats(), History.TRY)
                    if (said.isBlank() && d.segmentsQueued == 0 && text.text.length == before) setState(State.IDLE, getString(R.string.try_nothing))
                    else setState(State.IDLE, getString(R.string.try_done, audio, took))
                }.onFailure { setState(State.IDLE, getString(R.string.try_failed, it.message ?: "?")) }
            }
        }
    }

    /** At the cursor, with a space before it unless the cursor starts a line. */
    private fun insert(said: String) {
        val e = text.text
        val at = text.selectionStart.coerceAtLeast(0)
        val chunk = TakeDecoder.join(e.subSequence(0, at), said)
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

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        if (requestCode == REQ_MIC && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) start()
        else if (requestCode == REQ_MIC) status.setText(R.string.try_need_mic)
    }

    private companion object {
        const val REQ_MIC = 10
    }
}
