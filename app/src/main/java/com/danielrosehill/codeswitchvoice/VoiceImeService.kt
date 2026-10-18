package com.danielrosehill.codeswitchvoice

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.inputmethodservice.InputMethodService
import android.os.Handler
import android.os.Looper
import android.view.KeyEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.ImageButton
import android.widget.ProgressBar
import android.widget.TextView

/**
 * The voice input method. Opened from another keyboard's mic key (HeliBoard finds it through
 * the `voice` subtype in res/xml/method.xml) or picked directly. Tap the mic to stop; the
 * transcript is committed and, by default, the previous keyboard comes back.
 */
class VoiceImeService : InputMethodService() {
    private enum class State { IDLE, LOADING, RECORDING, TRANSCRIBING }

    private val main = Handler(Looper.getMainLooper())
    private var state = State.IDLE
    private var recorder: Recorder? = null
    private lateinit var status: TextView
    private lateinit var mic: ImageButton
    private lateinit var spinner: ProgressBar
    private lateinit var level: View

    override fun onCreateInputView(): View {
        val v = layoutInflater.inflate(R.layout.ime_view, null)
        status = v.findViewById(R.id.status)
        mic = v.findViewById(R.id.mic)
        spinner = v.findViewById(R.id.spinner)
        level = v.findViewById(R.id.level)
        mic.setOnClickListener { onMic() }
        v.findViewById<ImageButton>(R.id.switch_ime).setOnClickListener { cancelAndSwitchBack() }
        v.findViewById<ImageButton>(R.id.backspace).setOnClickListener { sendDownUpKeyEvents(KeyEvent.KEYCODE_DEL) }
        v.findViewById<ImageButton>(R.id.space).setOnClickListener { currentInputConnection?.commitText(" ", 1) }
        v.findViewById<ImageButton>(R.id.enter).setOnClickListener { sendEnter() }
        return v
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        if (restarting) return
        when {
            !ModelStore.isReady(this) -> show(getString(R.string.ime_no_model), busy = false)
            !hasMic() -> show(getString(R.string.ime_no_permission), busy = false)
            Prefs.autoStart(this) -> startRecording()
            else -> { show(getString(R.string.ime_tap_to_speak), busy = false); preload() }
        }
    }

    override fun onFinishInputView(finishingInput: Boolean) {
        super.onFinishInputView(finishingInput)
        if (state == State.RECORDING) {
            recorder?.cancel()
            recorder = null
            state = State.IDLE
        }
    }

    private fun hasMic() = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun onMic() {
        when {
            !ModelStore.isReady(this) || !hasMic() -> openSetup()
            state == State.IDLE -> startRecording()
            state == State.RECORDING -> stopAndTranscribe()
            else -> Unit
        }
    }

    private fun preload() {
        if (Transcriber.isLoaded()) return
        Thread { runCatching { Transcriber.load(this) } }.start()
    }

    private fun startRecording() {
        preload()
        val r = Recorder(
            onLevel = { l -> main.post { setLevel(l) } },
            onLimit = { main.post { if (state == State.RECORDING) stopAndTranscribe() } },
        )
        try {
            r.start()
        } catch (e: Exception) {
            show(getString(R.string.ime_mic_error, e.message ?: ""), busy = false)
            return
        }
        recorder = r
        state = State.RECORDING
        mic.setImageResource(R.drawable.ic_stop)
        show(getString(R.string.ime_listening), busy = false)
    }

    private fun stopAndTranscribe() {
        val r = recorder ?: return
        recorder = null
        val samples = r.stop()
        setLevel(0f)
        mic.setImageResource(R.drawable.ic_mic)
        if (samples.size < Transcriber.SAMPLE_RATE / 4) {
            state = State.IDLE
            show(getString(R.string.ime_too_short), busy = false)
            return
        }
        state = if (Transcriber.isLoaded()) State.TRANSCRIBING else State.LOADING
        show(getString(if (state == State.LOADING) R.string.ime_loading else R.string.ime_transcribing), busy = true)
        Thread {
            val result = runCatching { Transcriber.transcribe(this, samples) }
            main.post {
                state = State.IDLE
                result.onSuccess { text ->
                    if (text.isEmpty()) {
                        show(getString(R.string.ime_nothing_heard), busy = false)
                    } else {
                        commit(text)
                        show(getString(R.string.ime_tap_to_speak), busy = false)
                        if (Prefs.autoReturn(this)) switchBack()
                    }
                }.onFailure { show(getString(R.string.ime_error, it.message ?: it.javaClass.simpleName), busy = false) }
            }
        }.start()
    }

    /** Adds a separating space when the cursor sits right after a non-space character. */
    private fun commit(text: String) {
        val ic = currentInputConnection ?: return
        val before = ic.getTextBeforeCursor(1, 0)
        val sep = if (!before.isNullOrEmpty() && !before[0].isWhitespace()) " " else ""
        ic.commitText(sep + text, 1)
    }

    private fun sendEnter() {
        val ic = currentInputConnection ?: return
        val action = currentInputEditorInfo?.imeOptions?.and(EditorInfo.IME_MASK_ACTION) ?: EditorInfo.IME_ACTION_NONE
        if (action != EditorInfo.IME_ACTION_NONE && action != EditorInfo.IME_ACTION_UNSPECIFIED &&
            (currentInputEditorInfo?.imeOptions?.and(EditorInfo.IME_FLAG_NO_ENTER_ACTION) ?: 0) == 0
        ) {
            ic.performEditorAction(action)
        } else {
            sendDownUpKeyEvents(KeyEvent.KEYCODE_ENTER)
        }
    }

    private fun cancelAndSwitchBack() {
        recorder?.cancel()
        recorder = null
        state = State.IDLE
        switchBack()
    }

    private fun switchBack() {
        if (!switchToPreviousInputMethod()) {
            (getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager).showInputMethodPicker()
        }
    }

    private fun openSetup() {
        startActivity(Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    private fun show(msg: String, busy: Boolean) {
        if (!::status.isInitialized) return
        status.text = msg
        spinner.visibility = if (busy) View.VISIBLE else View.GONE
        mic.isEnabled = !busy
    }

    private fun setLevel(l: Float) {
        if (!::level.isInitialized) return
        level.scaleX = (l * 4f).coerceIn(0.02f, 1f)
    }
}
