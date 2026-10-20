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
 * Where it sits: drag the mic anywhere; on release it snaps to the nearer side, and the side and
 * height are saved (Prefs.bubbleSide / bubbleY), which the setup screen can also set. The bar
 * always opens towards the middle of the screen, so the mic stays where it was parked.
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
    private lateinit var controls: List<View>
    private val micBg = GradientDrawable().apply { shape = GradientDrawable.OVAL }
    private val barBg = GradientDrawable()
    private var state = State.IDLE
    private var recorder: Recorder? = null
    /** The field that had focus when the take started; the transcript goes there if it still exists. */
    private var target: AccessibilityNodeInfo? = null
    private var editableFocused = false
    private var shownSeconds = -1

    private val open get() = state == State.RECORDING || state == State.PAUSED

    override fun onServiceConnected() {
        wm = getSystemService(WINDOW_SERVICE) as WindowManager
        Prefs.listen(this, this)
        addBubble()
    }

    override fun onDestroy() {
        Prefs.unlisten(this, this)
        recorder?.cancel()
        recorder = null
        root?.let { runCatching { wm.removeView(it) } }
        root = null
        super.onDestroy()
    }

    override fun onInterrupt() = Unit

    /** Only used for "show only while typing": tracks whether an editable field has input focus. */
    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        if (!Prefs.bubbleOnlyTyping(this)) return
        editableFocused = when (event.eventType) {
            AccessibilityEvent.TYPE_VIEW_FOCUSED -> event.source?.isEditable == true
            else -> findFocus(AccessibilityNodeInfo.FOCUS_INPUT)?.isEditable == true
        }
        render()
    }

    override fun onSharedPreferenceChanged(sp: SharedPreferences?, key: String?) {
        if (key?.startsWith("bubble_") != true) return
        if (key == "bubble_only_typing") editableFocused = findFocus(AccessibilityNodeInfo.FOCUS_INPUT)?.isEditable == true
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
        controls = listOf(
            timer,
            pauseBtn,
            button(R.drawable.ic_retake, R.string.bubble_retake) { retake() },
            button(R.drawable.ic_close, R.string.discard) { discard() },
        )
        barBg.setColor(getColor(R.color.ime_bg))
        root = LinearLayout(themed).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(4), dp(4), dp(4), dp(4))
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

    /**
     * Positions the bubble from Prefs: a side and a fraction of the usable height. The window is
     * anchored to that side (gravity LEFT or RIGHT), so when the bar appears it grows inwards,
     * and the mic is the child next to the edge.
     */
    private fun place(attached: Boolean = true) {
        val r = root ?: return
        val size = dp(Prefs.bubbleSize(this))
        val left = Prefs.bubbleSide(this) == Prefs.SIDE_LEFT
        mic.removeAllViews()
        val pad = size / 5
        mic.addView(icon, FrameLayout.LayoutParams(size - 2 * pad, size - 2 * pad, Gravity.CENTER))
        mic.addView(spinner, FrameLayout.LayoutParams(size - 2 * pad, size - 2 * pad, Gravity.CENTER))
        r.removeAllViews()
        val children = listOf<View>(mic) + controls
        for (c in if (left) children else children.reversed()) {
            r.addView(c, if (c === mic) LinearLayout.LayoutParams(size, size) else LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        }
        params.gravity = Gravity.TOP or if (left) Gravity.LEFT else Gravity.RIGHT
        params.x = dp(EDGE_DP)
        params.y = (Prefs.bubbleY(this) * (resources.displayMetrics.heightPixels - size)).toInt()
        if (attached) runCatching { wm.updateViewLayout(r, params) }
    }

    /** Saves where a drag ended, judged by the mic's centre; the prefs listener then snaps it there. */
    private fun savePosition() {
        val size = dp(Prefs.bubbleSize(this))
        val m = resources.displayMetrics
        val left = params.gravity and Gravity.HORIZONTAL_GRAVITY_MASK == Gravity.LEFT
        val centre = if (left) params.x + dp(4) + size / 2 else m.widthPixels - params.x - dp(4) - size / 2
        val side = if (centre < m.widthPixels / 2) Prefs.SIDE_LEFT else Prefs.SIDE_RIGHT
        val y = (params.y.toFloat() / (m.heightPixels - size).coerceAtLeast(1)).coerceIn(0f, 1f)
        // Unchanged values fire no prefs callback, so place() directly as well.
        Prefs.setBubbleSide(this, side)
        Prefs.setBubbleY(this, y)
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
                        params.x = startX + (if (left) dx else -dx).toInt()
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
        if (!Transcriber.isLoaded(this)) Thread { runCatching { Transcriber.load(this) } }.start()
        target = findFocus(AccessibilityNodeInfo.FOCUS_INPUT)?.takeIf { it.isEditable && !it.isPassword }
        val r = Recorder(
            onLevel = { l -> main.post { setLevel(l) } },
            onLimit = { main.post { if (state == State.RECORDING) stopAndTranscribe() } },
        )
        try {
            r.start()
        } catch (e: Exception) {
            return toast(getString(R.string.ime_mic_error, e.message ?: ""))
        }
        recorder = r
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

    /** Throws the take away and starts a fresh one at once, into the same field. */
    private fun retake() {
        if (!open) return
        val keep = target
        recorder?.cancel()
        recorder = null
        state = State.IDLE
        startRecording()
        if (keep != null) target = keep
    }

    private fun discard() {
        if (!open) return
        recorder?.cancel()
        recorder = null
        target = null
        state = State.IDLE
        toast(getString(R.string.bubble_discarded))
        render()
    }

    private fun stopAndTranscribe() {
        val r = recorder ?: return
        recorder = null
        val samples = r.stop()
        if (samples.size < Transcriber.SAMPLE_RATE / 4) {
            state = State.IDLE
            render()
            return toast(getString(R.string.ime_too_short))
        }
        state = State.TRANSCRIBING
        render()
        Thread {
            val result = runCatching { Transcriber.transcribe(this, samples) }
            main.post {
                state = State.IDLE
                render()
                result.onSuccess { text ->
                    if (text.isEmpty()) toast(getString(R.string.ime_nothing_heard))
                    else {
                        Prefs.setLastTranscript(this, text)
                        deliver(text)
                    }
                }.onFailure { toast(getString(R.string.ime_error, it.message ?: it.javaClass.simpleName)) }
            }
        }.start()
    }

    /**
     * Puts [text] at the cursor of the field the take started in, or else the focused field.
     * 1. ACTION_SET_TEXT replaces the whole field, so the new value is built from the field's
     *    text and selection, then the cursor is moved to the end of the insert.
     * 2. If the field refuses SET_TEXT (some WebViews and custom editors), clipboard + ACTION_PASTE.
     * 3. Otherwise the text stays on the clipboard and as the last transcript (long-press).
     */
    private fun deliver(text: String) {
        val node = target?.takeIf { it.refresh() && it.isEditable }
            ?: findFocus(AccessibilityNodeInfo.FOCUS_INPUT)?.takeIf { it.isEditable }
        target = null
        if (node == null || node.isPassword) return toast(getString(R.string.bubble_no_field))
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
            return
        }
        // A background service can't read the clipboard (Android 10+), so the user's old clip
        // can't be restored; the transcript is left there, which is also the useful fallback.
        val cm = getSystemService(ClipboardManager::class.java)
        cm.setPrimaryClip(ClipData.newPlainText(getString(R.string.app_name), insert))
        if (!node.performAction(AccessibilityNodeInfo.ACTION_PASTE)) toast(getString(R.string.bubble_on_clipboard))
    }

    private fun render() {
        val r = root ?: return
        val show = !Prefs.bubbleOnlyTyping(this) || editableFocused || state != State.IDLE
        r.visibility = if (show) View.VISIBLE else View.GONE
        r.background = if (open) barBg.apply { cornerRadius = dp(Prefs.bubbleSize(this@FloatingMicService)).toFloat() } else null
        for (c in controls) c.visibility = if (open) View.VISIBLE else View.GONE
        micBg.setColor(getColor(if (open) R.color.bubble_recording else R.color.accent))
        icon.setImageResource(if (open) R.drawable.ic_stop else R.drawable.ic_mic)
        icon.visibility = if (state == State.TRANSCRIBING) View.GONE else View.VISIBLE
        spinner.visibility = if (state == State.TRANSCRIBING) View.VISIBLE else View.GONE
        mic.contentDescription = getString(if (open) R.string.try_cd_stop else R.string.cd_mic)
        pauseBtn.setImageResource(if (state == State.PAUSED) R.drawable.ic_play else R.drawable.ic_pause)
        pauseBtn.contentDescription = getString(if (state == State.PAUSED) R.string.resume else R.string.pause)
        r.alpha = if (state == State.IDLE) IDLE_ALPHA else 1f
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
        /** Gap between the bubble and the screen edge it is parked on. */
        const val EDGE_DP = 6
        /** Idle bubble is slightly see-through so it hides less of the app under it. */
        const val IDLE_ALPHA = 0.85f
    }
}
