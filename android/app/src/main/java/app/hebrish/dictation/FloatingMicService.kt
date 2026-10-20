package app.hebrish.dictation

import app.hebrish.core.*
import android.Manifest
import android.accessibilityservice.AccessibilityService
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
 * Where it sits: drag the mic anywhere. On release it snaps to the nearer side, or with the side
 * set to "free" it stays where it was dropped. The setup screen sets side, height, horizontal
 * place, edge gap, size and idle opacity (Prefs.bubble*). The bar always opens towards the
 * middle of the screen, so the mic stays where it was parked.
 *
 * Same engine and process as the voice keyboard, so both share one loaded model. Recording needs
 * no foreground service: see docs/maintaining.md, "Floating mic".
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

    private val open get() = state == State.RECORDING || state == State.PAUSED

    override fun onServiceConnected() {
        wm = getSystemService(WINDOW_SERVICE) as WindowManager
        Prefs.listen(this, this)
        addBubble()
        Transcriber.preload(this)
    }

    override fun onDestroy() {
        Prefs.unlisten(this, this)
        recorder?.cancel()
        recorder = null
        decoder?.cancel()
        decoder = null
        root?.let { runCatching { wm.removeView(it) } }
        root = null
        super.onDestroy()
    }

    override fun onInterrupt() = Unit

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
            setOnTouchListener(Drag())
        }
        timer = TextView(themed).apply {
            setTextColor(getColor(R.color.ime_text))
            textSize = 14f
            setPadding(dp(8), 0, dp(4), 0)
        }
        fun button(drawable: Int, cd: Int, action: () -> Unit) = ImageButton(themed).apply {
            setImageResource(drawable)
            contentDescription = getString(cd)
            background = null
            setPadding(dp(10), dp(10), dp(10), dp(10))
            setOnClickListener { action() }
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
        }
        pendingControls = listOf(insert, button(R.drawable.ic_close, R.string.bubble_dismiss) { dismissPending() })
        barBg.setColor(getColor(R.color.ime_bg))
        root = LinearLayout(themed).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(PAD_DP), dp(PAD_DP), dp(PAD_DP), dp(PAD_DP))
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

    /** Tap, long-press and drag on the mic; a move past the touch slop makes it a drag. */
    private inner class Drag : View.OnTouchListener {
        private val slop = ViewConfiguration.get(this@FloatingMicService).scaledTouchSlop
        private var downX = 0f
        private var downY = 0f
        private var startX = 0
        private var startY = 0
        private var dragging = false
        private var longPressed = false
        private val longPress = Runnable { longPressed = true; onLongPress() }

        override fun onTouch(v: View, e: MotionEvent): Boolean {
            val r = root ?: return false
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    downX = e.rawX; downY = e.rawY
                    startX = params.x; startY = params.y
                    dragging = false; longPressed = false
                    main.postDelayed(longPress, ViewConfiguration.getLongPressTimeout().toLong())
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = e.rawX - downX
                    val dy = e.rawY - downY
                    if (!dragging && !longPressed && dx * dx + dy * dy > slop * slop) {
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
                    if (dragging) savePosition() else if (!longPressed) onTap()
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

    /** Idle: insert the last transcript again (it is kept in Prefs). */
    private fun onLongPress() {
        if (state != State.IDLE) return
        val text = Prefs.lastTranscript(this) ?: return toast(getString(R.string.bubble_no_last))
        target = null
        deliver(text)
    }

    private fun startRecording() {
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
        try {
            r.start()
        } catch (e: Exception) {
            d.cancel()
            return toast(getString(R.string.ime_mic_error, e.message ?: ""))
        }
        recorder = r
        decoder = d
        state = State.RECORDING
        shownSeconds = -1
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
    }

    /** Throws the take away and starts a fresh one at once, into the same field. */
    private fun retake() {
        if (!open) return
        val keep = target
        dropTake()
        state = State.IDLE
        startRecording()
        if (keep != null) target = keep
    }

    private fun discard() {
        if (!open) return
        dropTake()
        target = null
        state = State.IDLE
        toast(getString(R.string.bubble_discarded))
        render()
    }

    private fun stopAndTranscribe() {
        val r = recorder ?: return
        val d = decoder ?: return
        recorder = null
        decoder = null
        val samples = r.stop()
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

    /** True if [text] went into [node]; tries SET_TEXT, then clipboard + PASTE. */
    private fun insertInto(node: AccessibilityNodeInfo, text: String): Boolean {
        val current = if (node.isShowingHintText) "" else node.text?.toString() ?: ""
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
        micBg.setColor(getColor(if (open) R.color.bubble_recording else R.color.accent))
        icon.setImageResource(if (open) R.drawable.ic_stop else R.drawable.ic_mic)
        icon.visibility = if (state == State.TRANSCRIBING) View.GONE else View.VISIBLE
        spinner.visibility = if (state == State.TRANSCRIBING) View.VISIBLE else View.GONE
        mic.contentDescription = getString(if (open) R.string.try_cd_stop else R.string.cd_mic)
        pauseBtn.setImageResource(if (state == State.PAUSED) R.drawable.ic_play else R.drawable.ic_pause)
        pauseBtn.contentDescription = getString(if (state == State.PAUSED) R.string.resume else R.string.pause)
        r.alpha = if (state == State.IDLE && !waiting) Prefs.bubbleAlpha(this) / 100f else 1f
        if (state != State.RECORDING) setLevel(0f)
        if (open) showTime()
    }

    private fun setLevel(l: Float) {
        if (!::icon.isInitialized) return
        val s = 1f + (l * 3f).coerceAtMost(0.35f)
        icon.scaleX = s
        icon.scaleY = s
        if (state == State.RECORDING) showTime()
    }

    private fun showTime() {
        val secs = recorder?.seconds ?: return
        if (secs == shownSeconds && state == State.RECORDING) return
        shownSeconds = secs
        timer.text = getString(if (state == State.PAUSED) R.string.bubble_paused_time else R.string.bubble_time, secs / 60, secs % 60)
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()

    private companion object {
        /** Padding inside the bubble's window, around the mic and the bar. */
        const val PAD_DP = 4
        /** Most nodes [findFocusedEditable] visits per search. */
        const val MAX_NODES = 1500
    }
}
