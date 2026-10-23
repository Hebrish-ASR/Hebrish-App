package app.hebrish.dictation

import app.hebrish.core.*
import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.inputmethodservice.InputMethodService
import android.os.Handler
import android.text.InputType
import android.os.Looper
import android.view.KeyEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.ImageButton
import android.widget.ProgressBar
import android.widget.TextView

/**
 * The voice input method. Opened from another keyboard's mic key (HeliBoard finds it through
 * the `voice` subtype in res/xml/method.xml) or picked directly. Tap the mic to stop; the
 * transcript is committed and, by default, the previous keyboard comes back.
 *
 * Getting back to the regular keyboard is the part voice IMEs most often get wrong, so there
 * are three routes (keyboard key, Back, long-press for the system picker), and [switchBack]
 * falls through several methods. See docs/maintaining.md, "Returning to the keyboard".
 */
class VoiceImeService : InputMethodService() {
    private enum class State { IDLE, LOADING, RECORDING, PAUSED, TRANSCRIBING }

    private val main = Handler(Looper.getMainLooper())
    private var state = State.IDLE
    private var recorder: Recorder? = null
    /** Decodes the take's segments while it is recorded, so Stop only waits for the tail. */
    private var decoder: TakeDecoder? = null
    /** The take's text that went in already (type as you go), for Prefs.lastTranscript. */
    private val takeText = StringBuilder()
    /** Set when the user asked to leave while a take was being transcribed: insert, then switch. */
    private var switchWhenDone = false
    private var shownSeconds = -1
    /** Short name of the mic the current take records from (Mic.label), shown in the status line. */
    private var micName = ""
    private lateinit var status: TextView
    private lateinit var mic: ImageButton
    private lateinit var spinner: ProgressBar
    private lateinit var level: View
    private lateinit var takeControls: View
    private lateinit var pauseBtn: Button
    private lateinit var insertLastBtn: Button

    override fun onCreateInputView(): View {
        val v = layoutInflater.inflate(R.layout.ime_view, null)
        status = v.findViewById(R.id.status)
        mic = v.findViewById(R.id.mic)
        spinner = v.findViewById(R.id.spinner)
        level = v.findViewById(R.id.level)
        takeControls = v.findViewById(R.id.take_controls)
        pauseBtn = v.findViewById(R.id.pause)
        insertLastBtn = v.findViewById(R.id.insert_last)
        insertLastBtn.setOnClickListener { insertLast() }
        mic.setOnClickListener { onMic() }
        v.findViewById<ImageButton>(R.id.switch_ime).apply {
            setOnClickListener { leave() }
            // Escape hatch that cannot fail: the system's own keyboard picker.
            setOnLongClickListener { showPicker(); true }
        }
        v.findViewById<ImageButton>(R.id.backspace).setOnClickListener { sendDownUpKeyEvents(KeyEvent.KEYCODE_DEL) }
        v.findViewById<ImageButton>(R.id.space).setOnClickListener { currentInputConnection?.commitText(" ", 1) }
        v.findViewById<ImageButton>(R.id.enter).setOnClickListener { sendEnter() }
        v.findViewById<Button>(R.id.comma).setOnClickListener { punctuate(",") }
        v.findViewById<Button>(R.id.period).setOnClickListener { punctuate(".") }
        v.findViewById<ImageButton>(R.id.settings).setOnClickListener { openSetup() }
        pauseBtn.setOnClickListener { togglePause() }
        v.findViewById<Button>(R.id.restart).setOnClickListener { restart() }
        v.findViewById<Button>(R.id.discard).setOnClickListener { discard() }
        return v
    }

    /**
     * Password fields (0.8.0) are never recorded for or typed into, as with the floating mic
     * (FloatingMicService skips isPassword nodes): no auto-start, the mic does nothing, commits fail.
     */
    private var passwordField = false

    private fun isPassword(info: EditorInfo?): Boolean {
        val t = info?.inputType ?: return false
        val variation = t and InputType.TYPE_MASK_VARIATION
        return when (t and InputType.TYPE_MASK_CLASS) {
            InputType.TYPE_CLASS_TEXT -> variation == InputType.TYPE_TEXT_VARIATION_PASSWORD ||
                variation == InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD ||
                variation == InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD
            InputType.TYPE_CLASS_NUMBER -> variation == InputType.TYPE_NUMBER_VARIATION_PASSWORD
            else -> false
        }
    }

    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        passwordField = isPassword(info)
        if (restarting) return
        switchWhenDone = false
        when {
            passwordField -> show(getString(R.string.ime_password), busy = false)
            !ModelStore.isReady(this) -> show(getString(R.string.ime_no_model), busy = false)
            !hasMic() -> show(getString(R.string.ime_no_permission), busy = false)
            Prefs.autoStart(this) -> startRecording()
            else -> { show(getString(R.string.ime_tap_to_speak), busy = false); preload() }
        }
        renderTake()
    }

    override fun onFinishInputView(finishingInput: Boolean) {
        super.onFinishInputView(finishingInput)
        if (state == State.RECORDING || state == State.PAUSED) {
            dropTake()
            state = State.IDLE
            renderTake()
        }
    }

    /** Back leaves for the regular keyboard instead of just hiding this one (Prefs.backSwitches). */
    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK && isInputViewShown && Prefs.backSwitches(this)) {
            event.startTracking()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onKeyUp(keyCode: Int, event: KeyEvent): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK && isInputViewShown && Prefs.backSwitches(this) && event.isTracking && !event.isCanceled) {
            leave()
            return true
        }
        return super.onKeyUp(keyCode, event)
    }

    private fun hasMic() = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun onMic() {
        when {
            !ModelStore.isReady(this) || !hasMic() -> openSetup()
            state == State.IDLE -> startRecording()
            state == State.RECORDING || state == State.PAUSED -> stopAndTranscribe()
            else -> Unit
        }
    }

    private fun preload() = Transcriber.preload(this)

    private fun startRecording(cue: Feedback.Cue = Feedback.Cue.START) {
        if (passwordField) return show(getString(R.string.ime_password), busy = false)
        preload()
        takeText.setLength(0)
        val d = TakeDecoder(this, if (Prefs.typeAsYouGo(this)) { text -> main.post { commitPart(text) } } else null)
        val r = Recorder(
            onLevel = { l -> main.post { setLevel(l) } },
            onLimit = { main.post { if (state == State.RECORDING) stopAndTranscribe() } },
            onSegment = { d.add(it) },
        )
        Mic.prepare(this, r)
        try {
            r.start()
        } catch (e: Exception) {
            d.cancel()
            Mic.release(this)
            show(getString(R.string.ime_mic_error, e.message ?: ""), busy = false)
            return
        }
        recorder = r
        decoder = d
        micName = Mic.label(this, r.routedDevice)
        state = State.RECORDING
        shownSeconds = -1
        Feedback.cue(this, cue)
        if (cue == Feedback.Cue.RESTART) flashRetake()
        mic.setImageResource(R.drawable.ic_stop)
        show(getString(R.string.ime_listening) + " · " + micName, busy = false)
        renderTake()
    }

    private fun togglePause() {
        val r = recorder ?: return
        when (state) {
            State.RECORDING -> {
                r.pause()
                setLevel(0f)
                state = State.PAUSED
                show(getString(R.string.ime_paused, r.seconds / 60, r.seconds % 60), busy = false)
            }
            State.PAUSED -> {
                try {
                    r.start()
                } catch (e: Exception) {
                    show(getString(R.string.ime_mic_error, e.message ?: ""), busy = false)
                    return
                }
                state = State.RECORDING
                shownSeconds = -1
                show(getString(R.string.ime_listening) + " · " + micName, busy = false)
            }
            else -> return
        }
        renderTake()
    }

    private fun dropTake() {
        recorder?.cancel()
        recorder = null
        decoder?.cancel()
        decoder = null
        Mic.release(this)
    }

    /** Throws the take away and starts a fresh one at once. */
    private fun restart() {
        if (state != State.RECORDING && state != State.PAUSED) return
        dropTake()
        state = State.IDLE
        startRecording(Feedback.Cue.RESTART)
    }

    private fun discard() {
        if (state != State.RECORDING && state != State.PAUSED) return
        dropTake()
        state = State.IDLE
        Feedback.cue(this, Feedback.Cue.DISCARD)
        setLevel(0f)
        mic.setImageResource(R.drawable.ic_mic)
        show(getString(R.string.ime_discarded), busy = false)
        renderTake()
    }

    private fun stopAndTranscribe() {
        val r = recorder ?: return
        val d = decoder ?: return
        recorder = null
        decoder = null
        val samples = r.stop()
        Mic.release(this)
        Feedback.cue(this, Feedback.Cue.STOP)
        setLevel(0f)
        mic.setImageResource(R.drawable.ic_mic)
        if (samples.size < Transcriber.SAMPLE_RATE / 4 && d.segmentsQueued == 0) {
            d.cancel()
            state = State.IDLE
            renderTake()
            show(getString(R.string.ime_too_short), busy = false)
            if (switchWhenDone) switchBack()
            return
        }
        state = if (Transcriber.isLoaded(this)) State.TRANSCRIBING else State.LOADING
        renderTake()
        show(getString(if (state == State.LOADING) R.string.ime_loading else R.string.ime_transcribing), busy = true)
        d.finish(samples) { result ->
            main.post {
                state = State.IDLE
                val leave = switchWhenDone
                switchWhenDone = false
                result.onSuccess { text ->
                    val inserted = text.isEmpty() || commitPart(text)
                    if (takeText.isEmpty()) {
                        show(getString(R.string.ime_nothing_heard), busy = false)
                        if (leave) switchBack()
                    } else {
                        Prefs.setLastTranscript(this, takeText.toString())
                        History.record(this, d.text, d.stats(), History.KEYBOARD)
                        if (inserted) {
                            show(getString(R.string.ime_tap_to_speak), busy = false)
                            if (leave || Prefs.autoReturn(this)) switchBack()
                        } else {
                            // No field to type into (focus moved, field closed): keep this keyboard
                            // up so Insert last is one tap away, even if the user asked to leave.
                            show(getString(R.string.ime_not_inserted), busy = false)
                        }
                    }
                    renderTake()
                }.onFailure {
                    show(getString(R.string.ime_error, it.message ?: it.javaClass.simpleName), busy = false)
                    if (leave) switchBack()
                }
            }
        }
    }

    /** One piece of the take: typed in at the cursor and added to [takeText]. False if no field took it. */
    private fun commitPart(text: String): Boolean {
        if (takeText.isNotEmpty()) takeText.append(' ')
        takeText.append(text)
        return commit(text)
    }

    /**
     * Adds a separating space when the cursor sits right after a non-space character. False
     * when there is no live text field: commitText returns false on a dead connection.
     */
    private fun commit(text: String): Boolean {
        if (passwordField) return false
        val ic = currentInputConnection ?: return false
        val before = ic.getTextBeforeCursor(1, 0)
        val sep = if (!before.isNullOrEmpty() && !before[0].isWhitespace()) " " else ""
        return ic.commitText(sep + text, 1)
    }

    /** Re-inserts the last transcript (kept in Prefs, so it survives the process being killed). */
    private fun insertLast() {
        val text = Prefs.lastTranscript(this) ?: return
        if (commit(text)) {
            show(getString(R.string.ime_tap_to_speak), busy = false)
            if (Prefs.autoReturn(this)) switchBack()
        } else {
            show(getString(R.string.ime_no_field), busy = false)
        }
    }

    /** Comma and period keys: a space the dictation left before the cursor goes, so "word ." becomes "word.". */
    private fun punctuate(mark: String) {
        val ic = currentInputConnection ?: return
        if (ic.getTextBeforeCursor(1, 0)?.toString() == " ") ic.deleteSurroundingText(1, 0)
        ic.commitText(mark, 1)
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

    /**
     * The keyboard key and Back. A take in progress is not thrown away: it is transcribed and
     * inserted first (Discard is the way to drop it), because losing a minute of dictation to a
     * stray tap is worse than a sentence to delete.
     */
    private fun leave() {
        when (state) {
            State.RECORDING, State.PAUSED -> {
                switchWhenDone = true
                stopAndTranscribe()
            }
            State.LOADING, State.TRANSCRIBING -> {
                switchWhenDone = true
                show(getString(R.string.ime_switch_after), busy = true)
            }
            State.IDLE -> switchBack()
        }
    }

    /**
     * 1. The keyboard chosen in setup, if any. 2. Android's own "previous" IME, which returns
     *    false when it has no history (e.g. this IME was picked from the system picker).
     * 3. The last other keyboard seen as the system default, then HeliBoard, then any other
     *    enabled keyboard. 4. The system picker, which always works.
     */
    private fun switchBack() {
        val others = (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).enabledInputMethodList
            .filter { it.packageName != packageName }.map { it.id }
        val chosen = Prefs.returnIme(this)?.takeIf { it in others }
        if (chosen != null && trySwitch(chosen)) return
        if (runCatching { switchToPreviousInputMethod() }.getOrDefault(false)) return
        val fallback = Prefs.lastOtherIme(this)?.takeIf { it in others }
            ?: others.firstOrNull { it.startsWith(HEBRISH_KEYBOARD) }
            ?: others.firstOrNull { it.startsWith(HELIBOARD) } ?: others.firstOrNull()
        if (fallback != null && trySwitch(fallback)) return
        showPicker()
    }

    private fun trySwitch(id: String) = runCatching { switchInputMethod(id); true }.getOrDefault(false)

    private fun showPicker() = (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker()

    private fun openSetup() {
        startActivity(Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    private fun show(msg: String, busy: Boolean) {
        if (!::status.isInitialized) return
        status.text = msg
        spinner.visibility = if (busy) View.VISIBLE else View.GONE
        mic.isEnabled = !busy
    }

    /** Pause / Restart / Discard while a take is open; Insert last when idle and there is one. */
    private fun renderTake() {
        if (!::takeControls.isInitialized) return
        val open = state == State.RECORDING || state == State.PAUSED
        takeControls.visibility = if (open) View.VISIBLE else View.GONE
        insertLastBtn.visibility = if (state == State.IDLE && Prefs.lastTranscript(this) != null) View.VISIBLE else View.GONE
        pauseBtn.setText(if (state == State.PAUSED) R.string.resume else R.string.pause)
    }

    /**
     * Retake is too quick to see otherwise: for a second the mic and the status line turn amber,
     * the status says "New take", and the mic spins back once (the ↺ of the Restart button).
     */
    private fun flashRetake() {
        if (!::status.isInitialized) return
        val amber = android.content.res.ColorStateList.valueOf(getColor(R.color.bubble_retake))
        status.setBackgroundColor(getColor(R.color.bubble_retake))
        status.setText(R.string.bubble_new_take)
        mic.backgroundTintList = amber
        mic.animate().cancel()
        mic.rotation = 0f
        mic.animate().rotation(-360f).setDuration(500).withEndAction { mic.rotation = 0f }
        flashing = true
        status.postDelayed({
            flashing = false
            status.background = null
            mic.backgroundTintList = null
            shownSeconds = -1
        }, 1000)
    }
    private var flashing = false

    private fun setLevel(l: Float) {
        if (!::level.isInitialized) return
        level.scaleX = (l * 4f).coerceIn(0.02f, 1f)
        val secs = recorder?.seconds ?: return
        if (state == State.RECORDING && secs != shownSeconds && !flashing) {
            shownSeconds = secs
            status.text = getString(R.string.ime_listening_time, secs / 60, secs % 60) + " · " + micName
        }
    }

    companion object {
        /** HeliBoard's package (`helium314.keyboard`, plus `.debug` / `.nouserlib` builds). */
        const val HELIBOARD = "helium314.keyboard"
        /** Hebrish Keyboard, the HeliBoard fork (`Hebrish-ASR/Hebrish-Keyboard`). */
        const val HEBRISH_KEYBOARD = "app.hebrish.keyboard"
    }
}
