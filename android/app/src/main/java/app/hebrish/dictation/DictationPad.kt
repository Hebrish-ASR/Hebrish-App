package app.hebrish.dictation

import app.hebrish.core.*
import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.ImageButton
import android.widget.ProgressBar
import android.widget.TextView

/**
 * A mic button that dictates into an [EditText] in the app's own screen: Try it ([TryActivity]) and
 * Notes ([NoteActivity]). Split out of TryActivity (2026-11-09) when Notes needed the same thing.
 * Records with [Recorder] and decodes with [TakeDecoder] directly; no input method is involved.
 * Text appears segment by segment while you talk (always "type as you go" here), inserted at the
 * cursor, and the status line reports the wait after Stop.
 *
 * The owning activity forwards [onResume], [onPause], [onDestroy] and [onPermissionResult].
 * [onTake] runs on the main thread after a take's last text is in the box, also when the screen
 * has already been closed (Back while recording stops the take; its text still arrives), so a
 * caller that stores the text should store it there, not only from the screen's lifecycle.
 */
class DictationPad(
    private val act: Activity,
    private val text: EditText,
    private val mic: ImageButton,
    private val status: TextView,
    private val level: ProgressBar,
    /** Under the status line, only when the screen would otherwise be stuck: Open Models, or Try again. */
    private val fix: Button,
    /** The History source this pad's takes are recorded under. */
    private val source: String,
    private val onTake: () -> Unit = {},
) {
    private enum class State { LOADING, IDLE, RECORDING, BUSY }

    private val ui = Handler(Looper.getMainLooper())
    private var state = State.LOADING
    private var decoder: TakeDecoder? = null
    /** The mic this take records from (Mic.label), under the timer. */
    private var micName = ""
    /** Set while the screen waits for a model: coming back from Models with one loads it. */
    private var noModel = false

    private val recorder = Recorder(
        onLevel = { v -> ui.post { level.progress = (v * 100).toInt() } },
        onLimit = { ui.post { if (state == State.RECORDING) stopAndTranscribe() } },
        onSegment = { decoder?.add(it) },
    )

    private val tick = object : Runnable {
        override fun run() {
            if (state != State.RECORDING) return
            val s = recorder.seconds
            status.text = act.getString(R.string.try_listening, s / 60, s % 60) + "\n" + micName
            ui.postDelayed(this, 250)
        }
    }

    /** Call once from onCreate, after the views exist. */
    fun init() {
        mic.setOnClickListener { onMic() }
        if (!ModelStore.isReady(act)) showNoModel() else preload()
    }

    fun onResume() {
        if (noModel && ModelStore.isReady(act)) {
            noModel = false
            preload()
        }
    }

    fun onPause() {
        if (state == State.RECORDING) stopAndTranscribe()   // never leave the mic open off-screen
    }

    fun onDestroy() {
        decoder?.cancel()
        TakeGuard.pad(this, false)
    }

    /** True if [requestCode] was this pad's microphone request. */
    fun onPermissionResult(requestCode: Int, grantResults: IntArray): Boolean {
        if (requestCode != REQ_MIC) return false
        if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) start()
        else status.setText(R.string.try_need_mic)
        return true
    }

    private fun showNoModel() {
        noModel = true
        setState(State.LOADING, act.getString(R.string.try_no_model))
        showFix(R.string.try_open_models) { act.startActivity(Intent(act, ModelsActivity::class.java)) }
    }

    private fun showFix(label: Int, action: () -> Unit) {
        fix.setText(label)
        fix.setOnClickListener { action() }
        fix.visibility = View.VISIBLE
    }

    /** The first load reads 650 MB and takes a few seconds; do it before the first tap. */
    private fun preload() {
        fix.visibility = View.GONE
        if (Transcriber.isLoaded(act)) return setState(State.IDLE, act.getString(R.string.try_ready))
        setState(State.LOADING, act.getString(R.string.try_loading))
        val app = act.applicationContext   // the load takes seconds: don't hold the screen meanwhile
        Thread {
            val err = runCatching { Transcriber.load(app) }.exceptionOrNull()
            ui.post {
                if (act.isDestroyed) return@post
                if (err == null) setState(State.IDLE, act.getString(R.string.try_ready))
                else {
                    setState(State.LOADING, act.getString(R.string.try_load_failed, err.message ?: "?"))
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
        if (act.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            act.requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQ_MIC)
            return
        }
        decoder = TakeDecoder(act) { said -> ui.post { insert(said) } }
        Mic.prepare(act, recorder)
        try {
            recorder.start()
        } catch (e: Exception) {
            // Mic busy (a call, another recorder): say so, as the keyboard does, instead of crashing.
            Mic.release(act)
            decoder?.cancel()
            decoder = null
            setState(State.IDLE, act.getString(R.string.ime_mic_error, e.message ?: "?"))
            return
        }
        Feedback.cue(act, Feedback.Cue.START)
        micName = Mic.label(act, recorder.routedDevice)
        setState(State.RECORDING, act.getString(R.string.try_listening, 0, 0))
        act.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        ui.post(tick)
    }

    private fun stopAndTranscribe() {
        val audio = recorder.samples / Transcriber.SAMPLE_RATE.toFloat()
        val samples = recorder.stop()
        Mic.release(act)
        Feedback.cue(act, Feedback.Cue.STOP)
        val d = decoder ?: return
        decoder = null
        level.progress = 0
        act.window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        if (samples.size < Transcriber.SAMPLE_RATE / 3 && d.segmentsQueued == 0) {
            d.cancel()
            setState(State.IDLE, act.getString(R.string.try_too_short))
            return
        }
        setState(State.BUSY, act.getString(R.string.try_transcribing))
        val t0 = SystemClock.elapsedRealtime()
        val before = text.text.length
        val app = act.applicationContext
        d.finish(samples) { result ->
            val took = (SystemClock.elapsedRealtime() - t0) / 1000f
            ui.post {
                result.onSuccess { said ->
                    if (said.isNotBlank()) insert(said)
                    History.record(app, d.text, d.stats(), source)
                    if (said.isBlank() && d.segmentsQueued == 0 && text.text.length == before) setState(State.IDLE, act.getString(R.string.try_nothing))
                    else setState(State.IDLE, act.getString(R.string.try_done, audio, took))
                    onTake()
                }.onFailure { setState(State.IDLE, act.getString(R.string.try_failed, it.message ?: "?")) }
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
        TakeGuard.pad(this, s == State.RECORDING || s == State.BUSY)
        status.text = message
        mic.setImageResource(if (s == State.RECORDING) R.drawable.ic_stop else R.drawable.ic_mic)
        mic.isEnabled = s == State.IDLE || s == State.RECORDING
        mic.alpha = if (mic.isEnabled) 1f else 0.4f
        level.visibility = if (s == State.RECORDING) View.VISIBLE else View.INVISIBLE
        mic.contentDescription = act.getString(if (s == State.RECORDING) R.string.try_cd_stop else R.string.cd_mic)
    }

    private companion object {
        const val REQ_MIC = 10
    }
}
