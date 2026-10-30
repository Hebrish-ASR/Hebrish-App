package app.hebrish.dictation

import app.hebrish.core.*
import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.inputmethodservice.InputMethodService
import android.media.AudioDeviceCallback
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.os.Handler
import android.text.InputType
import android.os.Looper
import android.view.HapticFeedbackConstants
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

    /** LOADING / TRANSCRIBING: no take open, earlier takes still decoding ([finishing]). */
    private enum class State { IDLE, LOADING, RECORDING, PAUSED, TRANSCRIBING }

    /**
     * One take (B-43a, R-2026-10-24-6: takes can overlap; the mic works while the last take is
     * still transcribing). Text decoded while an earlier take is still landing waits in [waiting],
     * so the texts go in in order.
     */
    private class Take(val decoder: TakeDecoder) {
        /** The take's text that went in already, for Prefs.lastTranscript. */
        val text = StringBuilder()
        val waiting = ArrayList<String>()
        /** Some piece found no field to go into. */
        var missed = false
        var ended = false
        var error: Throwable? = null
        /** Enter guard: Enter went through before this take landed; the rest waits for Insert last. */
        var diverted = false
        val late = StringBuilder()
    }

    private val main = Handler(Looper.getMainLooper())
    private var state = State.IDLE
    private var recorder: Recorder? = null
    /** The open take; its decoder works on segments while it is recorded, so Stop only waits for the tail. */
    private var take: Take? = null
    /** Stopped takes whose text is still coming, oldest first. */
    private val finishing = ArrayDeque<Take>()
    private val open get() = state == State.RECORDING || state == State.PAUSED
    /** Enter guard (B-50 on desktop): Enter tapped while takes are still landing waits for them. */
    private var enterHeld = false
    private val enterTimeout = Runnable { enterHoldExpired() }
    /** Set when the user asked to leave while a take was being transcribed: insert, then switch. */
    private var switchWhenDone = false
    private var shownSeconds = -1
    /** The mic source chip (1.008): Mic.shortLabel of the mic the next or current take uses. */
    private lateinit var source: TextView
    private lateinit var status: TextView
    private lateinit var mic: ImageButton
    private lateinit var spinner: ProgressBar
    private lateinit var level: View
    private lateinit var pauseBtn: ImageButton
    private lateinit var restartBtn: ImageButton
    private lateinit var discardBtn: ImageButton
    private lateinit var insertLastBtn: ImageButton
    private lateinit var pauseLbl: TextView
    private lateinit var micLbl: TextView

    override fun onCreateInputView(): View {
        val v = layoutInflater.inflate(R.layout.ime_view, null)
        status = v.findViewById(R.id.status)
        mic = v.findViewById(R.id.mic)
        spinner = v.findViewById(R.id.spinner)
        level = v.findViewById(R.id.level)
        pauseBtn = v.findViewById(R.id.pause)
        restartBtn = v.findViewById(R.id.restart)
        discardBtn = v.findViewById(R.id.discard)
        insertLastBtn = v.findViewById(R.id.insert_last)
        pauseLbl = v.findViewById(R.id.pause_lbl)
        micLbl = v.findViewById(R.id.mic_lbl)
        source = v.findViewById(R.id.source)
        source.setOnClickListener { switchMic() }
        insertLastBtn.setOnClickListener { insertLast() }
        mic.setOnClickListener { onMic() }
        v.findViewById<ImageButton>(R.id.switch_ime).apply {
            setOnClickListener { leave() }
            // Escape hatch that cannot fail: the system's own keyboard picker.
            setOnLongClickListener { showPicker(); true }
        }
        v.findViewById<ImageButton>(R.id.backspace).setOnClickListener { sendDownUpKeyEvents(KeyEvent.KEYCODE_DEL) }
        v.findViewById<ImageButton>(R.id.space).setOnClickListener { currentInputConnection?.commitText(" ", 1) }
        v.findViewById<ImageButton>(R.id.enter).setOnClickListener { onEnter() }
        v.findViewById<Button>(R.id.comma).setOnClickListener { punctuate(",") }
        v.findViewById<Button>(R.id.period).setOnClickListener { punctuate(".") }
        v.findViewById<ImageButton>(R.id.settings).setOnClickListener { openSetup() }
        pauseBtn.setOnClickListener { togglePause() }
        restartBtn.setOnClickListener { restart() }
        discardBtn.setOnClickListener { discard() }
        renderTake()
        showSource()
        return v
    }

    /** Keeps the idle chip right when a headset connects or drops while the keyboard is up. */
    private val devices = object : AudioDeviceCallback() {
        override fun onAudioDevicesAdded(added: Array<out AudioDeviceInfo>) { if (!open) showSource() }
        override fun onAudioDevicesRemoved(removed: Array<out AudioDeviceInfo>) { if (!open) showSource() }
    }

    override fun onCreate() {
        super.onCreate()
        getSystemService(AudioManager::class.java).registerAudioDeviceCallback(devices, main)
    }

    override fun onDestroy() {
        getSystemService(AudioManager::class.java).unregisterAudioDeviceCallback(devices)
        super.onDestroy()
    }

    /** The chip names the take's mic while one is open, else the mic the next take will use. */
    private fun showSource() {
        if (!::source.isInitialized) return
        val name = Mic.shortLabel(this, recorder?.preferredDevice ?: Mic.preferred(this))
        source.text = name
        source.contentDescription = getString(R.string.bubble_mic_cd, name)
    }

    /**
     * The source chip was tapped (1.008, as the floating mic's since 0.7.2): switch between
     * Bluetooth and the phone's mic. Idle, the next take uses the new mic; mid-take the recorder
     * pauses, re-routes and resumes, so the take keeps what it had; paused, it applies on Resume.
     */
    private fun switchMic() {
        val r = recorder
        Mic.toggle(this, r?.preferredDevice ?: Mic.preferred(this))
            ?: return show(getString(R.string.bubble_no_headset), busy = finishing.isNotEmpty())
        source.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
        if (r != null && open) {
            val wasRecording = state == State.RECORDING
            if (wasRecording) r.pause()
            Mic.release(this)
            Mic.prepare(this, r)
            if (wasRecording) {
                try {
                    r.start()
                } catch (e: Exception) {
                    state = State.PAUSED
                    show(getString(R.string.ime_mic_error, e.message ?: ""), busy = false)
                }
            }
            renderTake()
        }
        showSource()
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
        showSource()
    }

    override fun onFinishInputView(finishingInput: Boolean) {
        super.onFinishInputView(finishingInput)
        // The field the held Enter was meant for is gone: don't send it into the next one.
        if (enterHeld) { enterHeld = false; main.removeCallbacks(enterTimeout) }
        if (open) {
            dropTake()
            state = settled()
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
            open -> stopAndTranscribe()
            else -> startRecording()          // idle, or the last take still transcribing (B-43a)
        }
    }

    private fun preload() = Transcriber.preload(this)

    private fun startRecording(cue: Feedback.Cue = Feedback.Cue.START) {
        if (passwordField) return show(getString(R.string.ime_password), busy = false)
        preload()
        var t: Take? = null
        val d = TakeDecoder(this, if (Prefs.typeAsYouGo(this)) { text -> main.post { t?.let { deliverPart(it, text) } } } else null)
        t = Take(d)
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
        take = t
        state = State.RECORDING
        showSource()
        shownSeconds = -1
        Feedback.cue(this, cue)
        if (cue == Feedback.Cue.RESTART) flashRetake()
        show(getString(R.string.ime_status_listening, 0, 0), busy = false)
        renderTake()
    }

    private fun togglePause() {
        val r = recorder ?: return
        when (state) {
            State.RECORDING -> {
                r.pause()
                setLevel(0f)
                state = State.PAUSED
                show(getString(R.string.ime_status_paused, r.seconds / 60, r.seconds % 60), busy = false)
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
                show(getString(R.string.ime_status_listening, r.seconds / 60, r.seconds % 60), busy = false)
            }
            else -> return
        }
        renderTake()
    }

    private fun dropTake() {
        recorder?.cancel()
        recorder = null
        take?.decoder?.cancel()
        take = null
        Mic.release(this)
    }

    /** No take open: TRANSCRIBING while earlier takes are still landing, else IDLE. */
    private fun settled() = if (finishing.isEmpty()) State.IDLE else State.TRANSCRIBING

    /** Throws the take away and starts a fresh one at once. */
    private fun restart() {
        if (!open) return
        dropTake()
        state = settled()
        startRecording(Feedback.Cue.RESTART)
    }

    private fun discard() {
        if (!open) return
        dropTake()
        state = settled()
        Feedback.cue(this, Feedback.Cue.DISCARD)
        setLevel(0f)
        show(getString(R.string.ime_discarded), busy = finishing.isNotEmpty())
        renderTake()
    }

    private fun stopAndTranscribe() {
        val r = recorder ?: return
        val t = take ?: return
        val d = t.decoder
        recorder = null
        take = null
        val samples = r.stop()
        Mic.release(this)
        Feedback.cue(this, Feedback.Cue.STOP)
        setLevel(0f)
        if (samples.size < Transcriber.SAMPLE_RATE / 4 && d.segmentsQueued == 0) {
            d.cancel()
            state = settled()
            renderTake()
            show(getString(R.string.ime_too_short), busy = finishing.isNotEmpty())
            if (switchWhenDone && state == State.IDLE) { switchWhenDone = false; switchBack() }
            return
        }
        finishing.addLast(t)
        state = if (Transcriber.isLoaded(this)) State.TRANSCRIBING else State.LOADING
        renderTake()
        show(getString(if (state == State.LOADING) R.string.ime_loading else R.string.ime_transcribing), busy = true)
        d.finish(samples) { result ->
            main.post {
                result.onSuccess { text -> if (text.isNotEmpty()) deliverPart(t, text) }
                t.ended = true
                t.error = result.exceptionOrNull()
                if (finishing.firstOrNull() === t) land(t)
            }
        }
    }

    /**
     * [t] is the oldest take still landing and its decoder is done: record it, put in what the
     * next take decoded meanwhile, and report once nothing is left in flight.
     */
    private fun land(t: Take) {
        finishing.remove(t)
        val err = t.error
        if (err == null && t.text.isNotEmpty()) {
            // A diverted take keeps only its late words for Insert last; History gets the whole take.
            Prefs.setLastTranscript(this, if (t.late.isNotEmpty()) t.late.toString() else t.text.toString())
            History.record(this, t.decoder.text, t.decoder.stats(), History.KEYBOARD)
        }
        val next = finishing.firstOrNull() ?: take
        if (next != null) {
            for (piece in next.waiting) commitNow(next, piece)
            next.waiting.clear()
            if (next !== take && next.ended) return land(next)
        }
        if (finishing.isEmpty() && enterHeld) releaseEnter()
        if (open || finishing.isNotEmpty()) return renderTake()   // the next take's status line stays
        state = State.IDLE
        val leave = switchWhenDone
        switchWhenDone = false
        when {
            err != null -> {
                show(getString(R.string.ime_error, err.message ?: err.javaClass.simpleName), busy = false)
                if (leave) switchBack()
            }
            t.text.isEmpty() -> {
                show(getString(R.string.ime_nothing_heard), busy = false)
                if (leave) switchBack()
            }
            t.late.isNotEmpty() -> show(getString(R.string.ime_late_words), busy = false)
            !t.missed -> {
                show(getString(R.string.ime_tap_to_speak), busy = false)
                if (leave || Prefs.autoReturn(this)) switchBack()
            }
            // No field to type into (focus moved, field closed): keep this keyboard up so Insert
            // last is one tap away, even if the user asked to leave.
            else -> show(getString(R.string.ime_not_inserted), busy = false)
        }
        renderTake()
    }

    /** One piece of [t]: typed in at the cursor now, or held while an earlier take is still landing. */
    private fun deliverPart(t: Take, text: String) {
        val first = finishing.firstOrNull()
        if (first != null && first !== t) t.waiting.add(text) else commitNow(t, text)
    }

    private fun commitNow(t: Take, text: String) {
        t.text.append(TakeDecoder.join(t.text, text))
        if (t.diverted) t.late.append(TakeDecoder.join(t.late, text))
        else if (!commit(text)) t.missed = true
    }

    /**
     * The keyboard's Enter. With stopped takes still landing it waits for their last words
     * (at most [ENTER_HOLD_MS]), so a message isn't sent without them; desktop twin: the Enter
     * guard's `hold`, which here needs no keyboard grab because the Enter is this keyboard's own.
     */
    private fun onEnter() {
        if (enterHeld) return
        if (finishing.isEmpty()) return sendEnter()
        enterHeld = true
        main.postDelayed(enterTimeout, ENTER_HOLD_MS)
        show(getString(R.string.ime_enter_held), busy = true)
    }

    private fun releaseEnter() {
        enterHeld = false
        main.removeCallbacks(enterTimeout)
        sendEnter()
    }

    /** Still not in after [ENTER_HOLD_MS]: send now and keep what is still coming out of this message. */
    private fun enterHoldExpired() {
        if (!enterHeld) return
        for (t in finishing) t.diverted = true
        releaseEnter()
    }

    /**
     * Adds a separating space when the cursor sits right after a non-space character. False
     * when there is no live text field: commitText returns false on a dead connection.
     */
    private fun commit(text: String): Boolean {
        if (passwordField) return false
        val ic = currentInputConnection ?: return false
        val before = ic.getTextBeforeCursor(1, 0)
        // TakeDecoder.join: a space after a word, none before a held full stop (". Next", 0.8.2).
        return ic.commitText(TakeDecoder.join(before ?: "", text), 1)
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
        // The mic stays enabled while transcribing (B-43a): a tap starts the next take. Up to
        // 1.000 it was disabled, so a tap then did nothing.
    }

    /**
     * The control row (1.007): the five buttons are always there, so the keyboard keeps one
     * height; the ones that don't apply now are dimmed and disabled. Discard / Retake / Pause
     * while a take is open, Insert last when idle and there is one. The mic is green with a mic
     * when no take is open and red with a stop square while one is.
     */
    private fun renderTake() {
        if (!::pauseBtn.isInitialized) return
        val open = state == State.RECORDING || state == State.PAUSED
        enable(discardBtn, open)
        enable(restartBtn, open)
        enable(pauseBtn, open)
        enable(insertLastBtn, state == State.IDLE && Prefs.lastTranscript(this) != null)
        val paused = state == State.PAUSED
        pauseBtn.setImageResource(if (paused) R.drawable.ic_play else R.drawable.ic_pause)
        pauseBtn.backgroundTintList = tint(if (paused) R.color.ime_paused else R.color.ime_pause)
        pauseLbl.setText(if (paused) R.string.resume else R.string.pause)
        mic.setImageResource(if (open) R.drawable.ic_stop_round else R.drawable.ic_mic)
        if (!flashing) mic.backgroundTintList = tint(if (open) R.color.bubble_recording else R.color.ime_mic_idle)
        micLbl.setText(if (open) R.string.ime_lbl_stop else R.string.ime_lbl_record)
    }

    private fun enable(b: View, on: Boolean) {
        b.isEnabled = on
        b.alpha = if (on) 1f else 0.3f
    }

    private fun tint(color: Int) = android.content.res.ColorStateList.valueOf(getColor(color))

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
            renderTake()
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
            status.text = getString(R.string.ime_status_listening, secs / 60, secs % 60)
        }
    }

    companion object {
        /** Longest wait for a held Enter (desktop `ENTER_HOLD_S`, 4 s). */
        const val ENTER_HOLD_MS = 4000L
        /** HeliBoard's package (`helium314.keyboard`, plus `.debug` / `.nouserlib` builds). */
        const val HELIBOARD = "helium314.keyboard"
        /** Hebrish Keyboard, the HeliBoard fork (`Hebrish-ASR/Hebrish-Keyboard`). */
        const val HEBRISH_KEYBOARD = "app.hebrish.keyboard"
    }
}
