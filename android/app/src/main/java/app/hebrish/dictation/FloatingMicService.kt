package app.hebrish.dictation

import app.hebrish.core.*
import android.Manifest
import android.accessibilityservice.AccessibilityService
import android.animation.ValueAnimator
import android.content.BroadcastReceiver
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.ContextThemeWrapper
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.util.Log
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import android.widget.FrameLayout
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast

/**
 * The floating mic: an accessibility overlay that dictates into whatever text field has focus,
 * so the regular keyboard never has to be switched. Tap the mic to start. While a take is open
 * the bubble grows a bar with Pause / Resume, Retake, Discard and a timer, and the mic becomes
 * Stop, which transcribes and puts the text in at the cursor. Idle, a long-press inserts the
 * last transcript again.
 *
 * Missed the field: if no text field has focus when the transcript is ready (or the field
 * refuses it), the text is held and the bar shows **Insert** and a close button. Tap a field,
 * then Insert puts the text in at its cursor. The text is on the clipboard as well.
 *
 * Speed: the model is loaded when the service starts and again whenever a text field gets focus
 * (if Android dropped it), not when the mic is tapped. Takes are decoded segment by segment while
 * they are recorded (Recorder.onSegment + TakeDecoder), so after Stop only the last few seconds
 * remain to decode, and takes can run to Recorder.MAX_SEGMENTED_SECONDS.
 *
 * Where it sits: drag it anywhere, by the mic or, while a take is open, by any part of the bar
 * (a button still works as a tap). Holding still first works too: during a take a long-press
 * on the mic or bar buzzes and "picks it up". On release it snaps to the nearer side, or with
 * the side set to "free" it stays where it was dropped. The setup screen sets side, height,
 * horizontal place, edge gap, size, idle opacity, bar opacity and mic colour (Prefs.bubble*).
 * The bar always opens towards the middle of the screen, so the mic stays where it was parked.
 *
 * Same engine and process as the voice keyboard, so both share one loaded model. Recording needs
 * no foreground service: see docs/maintaining.md, "Floating mic".
 *
 * Feedback and control (0.6.0): while recording the mic pulses, and each start / stop / retake /
 * discard can pip and buzz ([Feedback]). The bar names the microphone in use ([Mic]; Bluetooth
 * first). Broadcast intents and bound hardware keys (a Bluetooth shutter remote, a keyboard)
 * drive the same actions as the buttons ([Remote], [onKeyEvent]; docs/external-control.md).
 */
class FloatingMicService : AccessibilityService(), SharedPreferences.OnSharedPreferenceChangeListener {
    private enum class State { IDLE, RECORDING, PAUSED, TRANSCRIBING }

    private val main = Handler(Looper.getMainLooper())
    private lateinit var wm: WindowManager
    private lateinit var params: WindowManager.LayoutParams
    private var root: LinearLayout? = null
    private lateinit var mic: FrameLayout
    private lateinit var icon: ImageView
    private lateinit var spinner: ProgressBar
    private lateinit var timer: TextView
    private lateinit var pauseBtn: ImageButton
    /** Shown while a take is open. */
    private lateinit var takeControls: List<View>
    /** Shown while a transcript is waiting for a field ([pending]). */
    private lateinit var pendingControls: List<View>
    private val micBg = GradientDrawable().apply { shape = GradientDrawable.OVAL }
    private val barBg = GradientDrawable()
    private var state = State.IDLE
    private var recorder: Recorder? = null
    private var decoder: TakeDecoder? = null
    /** Everything this take has put in so far (type-as-you-go), for Prefs.lastTranscript. */
    private val takeText = StringBuilder()
    /** The field that had focus when the take started; the transcript goes there if it still exists. */
    private var target: AccessibilityNodeInfo? = null
    /** Transcript that found no field to go into; Insert puts it in once one has focus. */
    private var pending: String? = null
    private var editableFocused = false
    /** The last editable node an event came from: the fallback when findFocus can't see the field. */
    private var lastEditable: AccessibilityNodeInfo? = null
    private var shownSeconds = -1
    /** Short name of the mic the current take records from, shown in the bar. */
    private var micName = ""
    private var remote: BroadcastReceiver? = null
    /** Key code whose ACTION_UP must still be swallowed (its DOWN was consumed). */
    private var swallowUp = KeyEvent.KEYCODE_UNKNOWN
    /** Until this uptime the bar shows the retake flash (amber, "New take") instead of the timer. */
    private var flashUntil = 0L
    /** While recording the mic's colour breathes, so a take in progress is obvious at a glance. */
    private val pulse = ValueAnimator.ofInt(255, 120).apply {
        duration = 700
        repeatMode = ValueAnimator.REVERSE
        repeatCount = ValueAnimator.INFINITE
        addUpdateListener { micBg.alpha = it.animatedValue as Int }
    }

    private val open get() = state == State.RECORDING || state == State.PAUSED

    override fun onServiceConnected() {
        wm = getSystemService(WINDOW_SERVICE) as WindowManager
        Prefs.listen(this, this)
        addBubble()
        remote = Remote.register(this) { main.post { onRemote(it) } }
        Transcriber.preload(this)
    }

    override fun onDestroy() {
        Prefs.unlisten(this, this)
        remote?.let { runCatching { unregisterReceiver(it) } }
        remote = null
        pulse.cancel()
        Mic.release(this)
        recorder?.cancel()
        recorder = null
        decoder?.cancel()
        decoder = null
        root?.let { runCatching { wm.removeView(it) } }
        root = null
        super.onDestroy()
    }

    override fun onInterrupt() = Unit

    /** A broadcast or a bound key: the same actions as the bar's buttons. */
    private fun onRemote(a: Remote.Action) {
        if (a != Remote.Action.STOP && a != Remote.Action.DISCARD && (!ModelStore.isReady(this) || !hasMic())) return onTap()
        when (a) {
            Remote.Action.TOGGLE -> onTap()
            Remote.Action.START -> if (state == State.IDLE) startRecording()
            Remote.Action.STOP -> if (open) stopAndTranscribe()
            Remote.Action.RESTART -> if (open) retake() else if (state == State.IDLE) startRecording()
            Remote.Action.PAUSE -> togglePause()
            Remote.Action.DISCARD -> discard()
        }
    }

    /**
     * Hardware keys (flagRequestFilterKeyEvents in res/xml/floating_mic.xml). Only keys bound
     * to an action are consumed, plus the next key while the settings screen is learning one.
     * Back, Home and Recents are never taken. Acts on key down, once (not on auto-repeat).
     */
    override fun onKeyEvent(event: KeyEvent): Boolean = runCatching {
        val code = event.keyCode
        if (code == KeyEvent.KEYCODE_BACK || code == KeyEvent.KEYCODE_HOME || code == KeyEvent.KEYCODE_APP_SWITCH) return false
        if (event.action == KeyEvent.ACTION_UP && code == swallowUp) {
            swallowUp = KeyEvent.KEYCODE_UNKNOWN
            return true
        }
        val learning = Prefs.learning(this)?.let { n -> Remote.Action.entries.firstOrNull { it.name == n } }
        if (learning != null) {
            if (event.action != KeyEvent.ACTION_DOWN) return true
            for (other in Remote.Action.entries) if (other != learning && Prefs.keyFor(this, other) == code) Prefs.setKeyFor(this, other, 0)
            Prefs.setKeyFor(this, learning, code)
            Prefs.setLearning(this, null)
            swallowUp = code
            main.post { toast(getString(R.string.controls_key_bound, Remote.keyName(code))) }
            return true
        }
        val a = Remote.actionFor(this, code) ?: return false
        if (event.action == KeyEvent.ACTION_DOWN && event.repeatCount == 0) main.post { onRemote(a) }
        true
    }.getOrDefault(false)

    /**
     * Tracks whether an editable field has input focus: for "show only while typing", and to
     * load the model the moment someone is about to type rather than when they tap the mic.
     */
    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        // An exception here would crash the service, and Android turns a crashing service off.
        runCatching {
            val was = editableFocused
            val source = event.source
            if (source?.isEditable == true && !source.isPassword) lastEditable = source
            editableFocused = source?.isEditable == true && event.eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||
                keyboardShowing() || focusedField() != null
            if (editableFocused && !was) Transcriber.preload(this)
            if (Prefs.bubbleOnlyTyping(this) && was != editableFocused) render()
        }
    }

    /** True while a keyboard window is on screen: the surest sign that someone is typing. */
    private fun keyboardShowing() =
        runCatching { windows.any { it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD } }.getOrDefault(false)

    /**
     * The text field that has input focus, or null. `findFocus(FOCUS_INPUT)` alone misses fields
     * in Jetpack Compose apps (ChatGPT, reported 2026-10-20): there it can return the host
     * AndroidComposeView, which is not editable, or nothing. So, in order:
     * 1. findFocus, if it is editable;
     * 2. a focused editable node under what findFocus returned (the Compose host case);
     * 3. the last editable node an event came from, if it still exists and is focused (or the
     *    keyboard is up: some Compose fields never report isFocused);
     * 4. a focused editable node in any app window, the active one first.
     */
    private fun focusedField(): AccessibilityNodeInfo? {
        val f = findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
        if (f != null && f.isEditable) return f
        f?.let { findFocusedEditable(it) }?.let { return it }
        lastEditable?.takeIf { it.refresh() && it.isEditable && (it.isFocused || keyboardShowing()) }?.let { return it }
        val roots = runCatching { windows }.getOrDefault(emptyList())
            .filter { it.type == AccessibilityWindowInfo.TYPE_APPLICATION }
            .sortedByDescending { it.isActive }
            .mapNotNull { it.root }
        for (r in roots) findFocusedEditable(r)?.let { return it }
        return null
    }

    /** Depth-first search for a focused, editable node, bounded so a huge tree can't stall the service. */
    private fun findFocusedEditable(root: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        val stack = ArrayDeque<AccessibilityNodeInfo>().apply { add(root) }
        var seen = 0
        while (stack.isNotEmpty() && seen++ < MAX_NODES) {
            val n = stack.removeLast()
            if (n.isEditable && n.isFocused) return n
            for (i in n.childCount - 1 downTo 0) n.getChild(i)?.let { stack.add(it) }
        }
        return null
    }

    override fun onSharedPreferenceChanged(sp: SharedPreferences?, key: String?) {
        if (key?.startsWith("bubble_") != true) return
        if (key == "bubble_only_typing") editableFocused = keyboardShowing() || focusedField() != null
        place()
        render()
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        place()
    }

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun addBubble() {
        val themed = ContextThemeWrapper(this, android.R.style.Theme_DeviceDefault)
        icon = ImageView(themed).apply { setImageResource(R.drawable.ic_mic); scaleType = ImageView.ScaleType.FIT_CENTER }
        spinner = ProgressBar(themed).apply { isIndeterminate = true; visibility = View.GONE }
        mic = FrameLayout(themed).apply {
            background = micBg
            elevation = dp(6).toFloat()
            contentDescription = getString(R.string.cd_mic)
            setOnTouchListener(Drag(::onTap, ::onLongPress))
        }
        timer = TextView(themed).apply {
            setTextColor(getColor(R.color.ime_text))
            textSize = 14f
            setPadding(dp(8), 0, dp(4), 0)
            setOnTouchListener(Drag())
        }
        fun button(drawable: Int, cd: Int, action: () -> Unit) = ImageButton(themed).apply {
            setImageResource(drawable)
            contentDescription = getString(cd)
            background = null
            setPadding(dp(10), dp(10), dp(10), dp(10))
            setOnClickListener { action() }
            setOnTouchListener(Drag({ performClick() }))
        }
        pauseBtn = button(R.drawable.ic_pause, R.string.pause) { togglePause() }
        takeControls = listOf(
            timer,
            pauseBtn,
            button(R.drawable.ic_retake, R.string.bubble_retake) { retake() },
            button(R.drawable.ic_close, R.string.discard) { discard() },
        )
        val insert = TextView(themed).apply {
            setText(R.string.bubble_insert)
            setTextColor(getColor(R.color.ime_text))
            textSize = 15f
            setCompoundDrawablesRelativeWithIntrinsicBounds(R.drawable.ic_paste, 0, 0, 0)
            compoundDrawablePadding = dp(6)
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(10), dp(10), dp(10), dp(10))
            contentDescription = getString(R.string.bubble_insert_cd)
            setOnClickListener { insertPending() }
            setOnTouchListener(Drag({ performClick() }))
        }
        pendingControls = listOf(insert, button(R.drawable.ic_close, R.string.bubble_dismiss) { dismissPending() })
        barBg.setColor(getColor(R.color.ime_bg))
        root = LinearLayout(themed).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(PAD_DP), dp(PAD_DP), dp(PAD_DP), dp(PAD_DP))
            setOnTouchListener(Drag())
        }
        // TYPE_ACCESSIBILITY_OVERLAY needs no "draw over other apps" permission. Not focusable,
        // so tapping it leaves input focus (and the keyboard) on the field being dictated into.
        params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT,
        )
        place(attached = false)
        wm.addView(root, params)
        render()
    }

    /** Left edge of the mic in px, from Prefs: parked on an edge (with the edge gap) or free. */
    private fun micLeft(size: Int): Int {
        val w = resources.displayMetrics.widthPixels
        return when (Prefs.bubbleSide(this)) {
            Prefs.SIDE_LEFT -> dp(Prefs.bubbleEdge(this))
            Prefs.SIDE_FREE -> (Prefs.bubbleX(this) * (w - size)).toInt()
            else -> w - dp(Prefs.bubbleEdge(this)) - size
        }
    }

    /**
     * Positions the bubble from Prefs. The window is anchored to the side of the screen the mic
     * is on (gravity LEFT or RIGHT), so when the bar appears it grows towards the middle, and the
     * mic is the child next to that side.
     */
    private fun place(attached: Boolean = true) {
        val r = root ?: return
        val size = dp(Prefs.bubbleSize(this))
        val w = resources.displayMetrics.widthPixels
        val pad = dp(PAD_DP)
        val x = micLeft(size)
        val left = x + size / 2 < w / 2
        mic.removeAllViews()
        val inner = size - 2 * (size / 5)
        mic.addView(icon, FrameLayout.LayoutParams(inner, inner, Gravity.CENTER))
        mic.addView(spinner, FrameLayout.LayoutParams(inner, inner, Gravity.CENTER))
        r.removeAllViews()
        val children = listOf<View>(mic) + takeControls + pendingControls
        for (c in if (left) children else children.reversed()) {
            r.addView(c, if (c === mic) LinearLayout.LayoutParams(size, size) else LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        }
        params.gravity = Gravity.TOP or if (left) Gravity.LEFT else Gravity.RIGHT
        params.x = (if (left) x - pad else w - x - size - pad).coerceAtLeast(0)
        params.y = (Prefs.bubbleY(this) * (resources.displayMetrics.heightPixels - size)).toInt() - pad
        if (attached) runCatching { wm.updateViewLayout(r, params) }
    }

    /**
     * Saves where a drag ended. Parked on an edge: the side nearer the mic's centre (the prefs
     * listener snaps it there). Free: the exact spot.
     */
    private fun savePosition() {
        val size = dp(Prefs.bubbleSize(this))
        val m = resources.displayMetrics
        val pad = dp(PAD_DP)
        val anchoredLeft = params.gravity and Gravity.HORIZONTAL_GRAVITY_MASK == Gravity.LEFT
        val x = if (anchoredLeft) params.x + pad else m.widthPixels - params.x - pad - size
        if (Prefs.bubbleSide(this) == Prefs.SIDE_FREE) {
            Prefs.setBubbleX(this, x.toFloat() / (m.widthPixels - size).coerceAtLeast(1))
        } else {
            Prefs.setBubbleSide(this, if (x + size / 2 < m.widthPixels / 2) Prefs.SIDE_LEFT else Prefs.SIDE_RIGHT)
        }
        Prefs.setBubbleY(this, ((params.y + pad).toFloat() / (m.heightPixels - size).coerceAtLeast(1)))
        // Unchanged values fire no prefs callback, so place() directly as well.
        place()
    }

    /**
     * Tap, long-press and drag on any part of the bubble; a move past the touch slop makes it a
     * drag. [hold] runs on a long-press and says whether it did something; if not (a take is
     * open, or this is the bar), the long-press "picks up" the bubble instead: a buzz, then any
     * move drags it. Buttons pass performClick as [tap], so they still click.
     */
    private inner class Drag(private val tap: () -> Unit = {}, private val hold: () -> Boolean = { false }) : View.OnTouchListener {
        private val slop = ViewConfiguration.get(this@FloatingMicService).scaledTouchSlop
        private var downX = 0f
        private var downY = 0f
        private var startX = 0
        private var startY = 0
        private var dragging = false
        private var longPressed = false
        private var grabbed = false
        private var view: View? = null
        private val longPress = Runnable {
            longPressed = hold()
            if (!longPressed) {
                grabbed = true
                view?.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
            }
        }

        override fun onTouch(v: View, e: MotionEvent): Boolean {
            val r = root ?: return false
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downX = e.rawX; downY = e.rawY
                    startX = params.x; startY = params.y
                    dragging = false; longPressed = false; grabbed = false
                    view = v
                    main.postDelayed(longPress, ViewConfiguration.getLongPressTimeout().toLong())
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = e.rawX - downX
                    val dy = e.rawY - downY
                    if (!dragging && !longPressed && (grabbed || dx * dx + dy * dy > slop * slop)) {
                        dragging = true
                        main.removeCallbacks(longPress)
                    }
                    if (dragging) {
                        val left = params.gravity and Gravity.HORIZONTAL_GRAVITY_MASK == Gravity.LEFT
                        params.x = (startX + (if (left) dx else -dx).toInt()).coerceAtLeast(0)
                        params.y = startY + dy.toInt()
                        runCatching { wm.updateViewLayout(r, params) }
                    }
                }
                MotionEvent.ACTION_UP -> {
                    main.removeCallbacks(longPress)
                    if (dragging) savePosition() else if (!longPressed && !grabbed) tap()
                }
                MotionEvent.ACTION_CANCEL -> {
                    main.removeCallbacks(longPress)
                    if (dragging) savePosition()
                }
            }
            return true
        }
    }

    private fun hasMic() = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun onTap() {
        when {
            !ModelStore.isReady(this) || !hasMic() -> {
                toast(getString(if (!ModelStore.isReady(this)) R.string.ime_no_model else R.string.ime_no_permission))
                startActivity(Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
            state == State.IDLE -> startRecording()
            open -> stopAndTranscribe()
            else -> Unit
        }
    }

    /** Idle: insert the last transcript again (it is kept in Prefs). False during a take: nothing to do. */
    private fun onLongPress(): Boolean {
        if (state != State.IDLE) return false
        val text = Prefs.lastTranscript(this)
        if (text == null) toast(getString(R.string.bubble_no_last)) else {
            target = null
            deliver(text)
        }
        return true
    }

    private fun startRecording(cue: Feedback.Cue = Feedback.Cue.START) {
        Transcriber.preload(this)
        target = focusedField()?.takeIf { !it.isPassword }
        takeText.setLength(0)
        // Type as you go: each segment goes in when decoded. Otherwise it is all held for Stop.
        val d = TakeDecoder(this, if (Prefs.typeAsYouGo(this)) { text -> main.post { deliverPart(text) } } else null)
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
            return toast(getString(R.string.ime_mic_error, e.message ?: ""))
        }
        recorder = r
        decoder = d
        micName = Mic.label(this, r.routedDevice)
        state = State.RECORDING
        shownSeconds = -1
        Feedback.cue(this, cue)
        if (cue == Feedback.Cue.RESTART) flashRetake()
        // A quick pop, so the start is visible even from the corner of an eye.
        mic.animate().scaleX(1.2f).scaleY(1.2f).setDuration(110)
            .withEndAction { mic.animate().scaleX(1f).scaleY(1f).setDuration(140) }
        render()
    }

    /** Pause releases the microphone and keeps the take; Resume appends to it. */
    private fun togglePause() {
        val r = recorder ?: return
        when (state) {
            State.RECORDING -> {
                r.pause()
                state = State.PAUSED
            }
            State.PAUSED -> {
                try {
                    r.start()
                } catch (e: Exception) {
                    return toast(getString(R.string.ime_mic_error, e.message ?: ""))
                }
                state = State.RECORDING
            }
            else -> return
        }
        render()
    }

    private fun dropTake() {
        recorder?.cancel()
        recorder = null
        decoder?.cancel()
        decoder = null
        Mic.release(this)
    }

    /** Throws the take away and starts a fresh one at once, into the same field. */
    private fun retake() {
        if (!open) return
        val keep = target
        dropTake()
        state = State.IDLE
        startRecording(Feedback.Cue.RESTART)
        if (keep != null) target = keep
    }

    private fun discard() {
        if (!open) return
        dropTake()
        target = null
        state = State.IDLE
        Feedback.cue(this, Feedback.Cue.DISCARD)
        toast(getString(R.string.bubble_discarded))
        render()
    }

    private fun stopAndTranscribe() {
        val r = recorder ?: return
        val d = decoder ?: return
        recorder = null
        decoder = null
        val samples = r.stop()
        Mic.release(this)
        Feedback.cue(this, Feedback.Cue.STOP)
        if (samples.size < Transcriber.SAMPLE_RATE / 4 && d.segmentsQueued == 0) {
            d.cancel()
            state = State.IDLE
            render()
            return toast(getString(R.string.ime_too_short))
        }
        state = State.TRANSCRIBING
        render()
        d.finish(samples) { result ->
            main.post {
                state = State.IDLE
                render()
                result.onSuccess { text ->
                    if (text.isNotEmpty()) deliverPart(text)
                    if (takeText.isEmpty()) toast(getString(R.string.ime_nothing_heard))
                    else Prefs.setLastTranscript(this, takeText.toString())
                    target = null
                }.onFailure { toast(getString(R.string.ime_error, it.message ?: it.javaClass.simpleName)) }
            }
        }
    }

    /** One piece of the take's text: into the take's field, keeping it as the target for the next piece. */
    private fun deliverPart(text: String) {
        if (takeText.isNotEmpty()) takeText.append(' ')
        takeText.append(text)
        val keep = target
        deliver(text)
        target = keep
    }

    /**
     * Puts [text] at the cursor of the field the take started in, or else the focused field.
     * 1. ACTION_SET_TEXT replaces the whole field, so the new value is built from the field's
     *    text and selection, then the cursor is moved to the end of the insert.
     * 2. If the field refuses SET_TEXT (some WebViews and custom editors), clipboard + ACTION_PASTE.
     * 3. Otherwise it is held as [pending] (Insert button) and left on the clipboard.
     */
    private fun deliver(text: String) {
        val node = target?.takeIf { it.refresh() && it.isEditable }
            ?: focusedField()
        target = null
        if (node == null || node.isPassword || !insertInto(node, text)) hold(text)
    }

    /**
     * True when [current], the field's reported text, is really its placeholder ("Message" in
     * WhatsApp), so the transcript must replace it rather than follow it.
     * 1. isShowingHintText: the standard signal; many apps set it.
     * 2. The text equals the field's declared hint.
     * 3. Prefs.clearPlaceholder (on by default, 0.6.0): apps such as WhatsApp report the hint as
     *    the text and set neither. Short (≤ [PLACEHOLDER_MAX] chars), single-line text with no
     *    real cursor (selection -1 or 0..0) is taken for a placeholder. That could replace a real
     *    one-word draft whose cursor sits at its start, hence the setting. Never applied once this
     *    take has typed something ([takeText]), so type-as-you-go can't wipe its own text.
     * (I: 2026-10-20, 3. inferred from the reported WhatsApp behaviour; not yet tried on a phone.)
     */
    private fun isPlaceholder(node: AccessibilityNodeInfo, current: String, firstPart: Boolean): Boolean {
        if (current.isEmpty()) return false
        if (node.isShowingHintText) return true
        if (node.hintText?.toString() == current) return true
        if (!firstPart || !Prefs.clearPlaceholder(this)) return false
        val s = node.textSelectionStart
        val e = node.textSelectionEnd
        return current.length <= PLACEHOLDER_MAX && '\n' !in current && (s == -1 || (s == 0 && e == 0))
    }

    /** True if [text] went into [node]; tries SET_TEXT, then clipboard + PASTE. */
    private fun insertInto(node: AccessibilityNodeInfo, text: String): Boolean {
        val reported = node.text?.toString() ?: ""
        val placeholder = isPlaceholder(node, reported, firstPart = takeText.length <= text.length)
        val current = if (placeholder) "" else reported
        var start = node.textSelectionStart
        var end = node.textSelectionEnd
        if (start !in 0..current.length || end !in 0..current.length) { start = current.length; end = current.length }
        if (start > end) start = end.also { end = start }
        val before = current.substring(0, start)
        val insert = (if (before.isNotEmpty() && !before.last().isWhitespace()) " " else "") + text
        val set = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, before + insert + current.substring(end))
        }
        if (node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, set)) {
            if (placeholder) Log.i(TAG, "Replaced placeholder text (${reported.length} chars)")
            val cursor = start + insert.length
            node.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, Bundle().apply {
                putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, cursor)
                putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, cursor)
            })
            return true
        }
        // A background service can't read the clipboard (Android 10+), so the user's old clip
        // can't be restored; the transcript is left there, which is also the useful fallback.
        copy(insert)
        return node.performAction(AccessibilityNodeInfo.ACTION_PASTE)
    }

    /** No field took [text]: keep it for the Insert button, and on the clipboard. */
    private fun hold(text: String) {
        pending = pending?.let { "$it $text" } ?: text
        copy(pending!!)
        toast(getString(R.string.bubble_held))
        render()
    }

    /** Insert: the held text into whatever field has focus now, at its cursor. */
    private fun insertPending() {
        val text = pending ?: return
        val node = focusedField()?.takeIf { !it.isPassword }
            ?: return toast(getString(R.string.bubble_tap_field))
        if (!insertInto(node, text)) return toast(getString(R.string.bubble_on_clipboard))
        pending = null
        render()
    }

    private fun dismissPending() {
        pending = null
        render()
    }

    private fun copy(text: String) =
        getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText(getString(R.string.app_name), text))

    private fun render() {
        val r = root ?: return
        val waiting = pending != null && state == State.IDLE
        val show = !Prefs.bubbleOnlyTyping(this) || editableFocused || state != State.IDLE || waiting
        r.visibility = if (show) View.VISIBLE else View.GONE
        r.background = if (open || waiting) barBg.apply { cornerRadius = dp(Prefs.bubbleSize(this@FloatingMicService)).toFloat() } else null
        for (c in takeControls) c.visibility = if (open) View.VISIBLE else View.GONE
        for (c in pendingControls) c.visibility = if (waiting) View.VISIBLE else View.GONE
        barBg.alpha = Prefs.bubbleBarAlpha(this) * 255 / 100
        micBg.setColor(if (open) getColor(R.color.bubble_recording) else Prefs.bubbleColor(this))
        icon.setImageResource(if (open) R.drawable.ic_stop else R.drawable.ic_mic)
        icon.visibility = if (state == State.TRANSCRIBING) View.GONE else View.VISIBLE
        spinner.visibility = if (state == State.TRANSCRIBING) View.VISIBLE else View.GONE
        mic.contentDescription = getString(if (open) R.string.try_cd_stop else R.string.cd_mic)
        pauseBtn.setImageResource(if (state == State.PAUSED) R.drawable.ic_play else R.drawable.ic_pause)
        pauseBtn.contentDescription = getString(if (state == State.PAUSED) R.string.resume else R.string.pause)
        r.alpha = if (state == State.IDLE && !waiting) Prefs.bubbleAlpha(this) / 100f else 1f
        if (state != State.RECORDING) setLevel(0f)
        if (state == State.RECORDING) { if (!pulse.isStarted) pulse.start() } else { pulse.cancel(); micBg.alpha = 255 }
        if (open) showTime()
    }

    private fun setLevel(l: Float) {
        if (!::icon.isInitialized) return
        val s = 1f + (l * 3f).coerceAtMost(0.35f)
        icon.scaleX = s
        icon.scaleY = s
        if (state == State.RECORDING) showTime()
    }

    /**
     * Retake is otherwise too quick to see (the timer just goes back to 0:00): the bar turns
     * amber and says "New take" for [FLASH_MS], with or without sounds.
     */
    private fun flashRetake() {
        flashUntil = android.os.SystemClock.uptimeMillis() + FLASH_MS
        barBg.setColor(getColor(R.color.bubble_retake))
        timer.setText(R.string.bubble_new_take)
        main.postDelayed({
            if (android.os.SystemClock.uptimeMillis() < flashUntil) return@postDelayed
            barBg.setColor(getColor(R.color.ime_bg))
            shownSeconds = -1
            if (open) showTime()
        }, FLASH_MS)
    }

    private fun showTime() {
        if (android.os.SystemClock.uptimeMillis() < flashUntil) return
        val secs = recorder?.seconds ?: return
        if (secs == shownSeconds && state == State.RECORDING) return
        shownSeconds = secs
        timer.text = getString(if (state == State.PAUSED) R.string.bubble_paused_time else R.string.bubble_time, secs / 60, secs % 60) +
            if (micName.isNotEmpty()) " · $micName" else ""
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()

    private companion object {
        /** Padding inside the bubble's window, around the mic and the bar. */
        const val PAD_DP = 4
        const val TAG = "HebrishFloatingMic"
        /** Longest field text [isPlaceholder] will take for a placeholder. */
        const val PLACEHOLDER_MAX = 40
        /** How long the retake flash lasts. */
        const val FLASH_MS = 1000L
        /** Most nodes [findFocusedEditable] visits per search. */
        const val MAX_NODES = 1500
    }
}
