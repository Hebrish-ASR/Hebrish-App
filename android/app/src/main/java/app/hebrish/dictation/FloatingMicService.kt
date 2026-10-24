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
 * Out of the way (1.000, Daniel 2026-10-24: "it'll open, and then suddenly it's overlaying some
 * text I'm working on"): the bar has a grip at its outer end, so it can be moved mid-take without
 * going near the mic (a tap on it is Stop). By default the bar opens along the edge the mic is on,
 * up or down towards the middle, a narrow strip instead of a line across the text
 * (Prefs.bubbleBarDirection); its buttons can be scaled down (Prefs.bubbleBarScale), and a clear
 * bar drops the background so only the buttons, each on its own backdrop, cover anything
 * (Prefs.bubbleBarClear). The idle mic can show the Hebrish H or the letter ayin instead of the
 * mic glyph (Prefs.bubbleIcon).
 *
 * Staying up (0.7.3): with "only while typing" on, the bubble appears when a field gets focus and
 * then stays, even when the field loses focus or the bubble is dragged, so it can be moved off
 * what you are reading before you tap it. There is no close button (0.7.4): a × beside the mic
 * was hit by every attempt to grab and drag the mic, so turning the floating mic off in settings
 * is the only way to hide it (Daniel, 2026-10-22).
 *
 * Minimise (0.7.7): double-tap the idle mic and it shrinks to a dot a third of its size, at the
 * same spot and at idle opacity, for when it is in the way of what you are writing. Tap the dot
 * (or double-tap it) to bring it back. It never goes away: a take started from a remote, or a
 * held transcript, shows the full mic and bar until it is done, then the dot again. The cost is that a single tap on the idle mic now waits
 * for the double-tap timeout (~300 ms) before it starts a take; Stop during a take is immediate.
 * Daniel, 2026-10-23: "just make it a bit small, get out of the way".
 *
 * Same engine and process as the voice keyboard, so both share one loaded model. Recording needs
 * no foreground service: see docs/maintaining.md, "Floating mic".
 *
 * Feedback and control (0.6.0): while recording the mic pulses, and each start / stop / retake /
 * discard can pip and buzz ([Feedback]). The bar names the microphone in use ([Mic]; Bluetooth
 * first) in a chip that switches between Bluetooth and the phone's mic when tapped (0.7.2). Broadcast intents and bound hardware keys (a Bluetooth shutter remote, a keyboard)
 * drive the same actions as the buttons ([Remote], [onKeyEvent]; docs/external-control.md).
 *
 * Takes can overlap (B-43a, R-2026-10-24-6): a tap while the last take is still transcribing
 * starts the next one at once instead of being ignored. Each take is a [Take] with its own field
 * and decoder; a later take's text waits in [Take.waiting] until every earlier one has landed, so
 * the texts go in in order.
 */
class FloatingMicService : AccessibilityService(), SharedPreferences.OnSharedPreferenceChangeListener {
    /** TRANSCRIBING: no take open, earlier takes still decoding ([finishing]). */
    private enum class State { IDLE, RECORDING, PAUSED, TRANSCRIBING }

    /** One take's output: the field it goes to, what it has put in so far, and text held back. */
    private class Take(val target: AccessibilityNodeInfo?, val decoder: TakeDecoder) {
        /** Everything this take has put in (type-as-you-go), for Prefs.lastTranscript. */
        val text = StringBuilder()
        /** Pieces decoded while an earlier take was still landing; delivered when it has. */
        val waiting = ArrayList<String>()
        /** The decoder's finish callback has come back (result kept until the take's turn). */
        var ended = false
        var error: Throwable? = null
    }

    private val main = Handler(Looper.getMainLooper())
    private lateinit var wm: WindowManager
    private lateinit var params: WindowManager.LayoutParams
    private var root: LinearLayout? = null
    private lateinit var mic: FrameLayout
    private lateinit var icon: ImageView
    private lateinit var spinner: ProgressBar
    private lateinit var timer: TextView
    private lateinit var pauseBtn: ImageButton
    /** Which mic the take records from ("BT Pixel Bu…", "Internal"); tap to switch. */
    private lateinit var source: TextView
    /** Shown while a take is open. */
    private lateinit var takeControls: List<View>
    /** Shown while a transcript is waiting for a field ([pending]). */
    private lateinit var pendingControls: List<View>
    /** Drag handle at the bar's outer end, shown during a take (1.000). */
    private lateinit var grip: ImageButton
    /** Bar buttons without a filled circle of their own: they get a backdrop in a clear bar. */
    private lateinit var plainButtons: List<ImageButton>
    private lateinit var insert: TextView
    private val micBg = GradientDrawable().apply { shape = GradientDrawable.OVAL }
    private val barBg = GradientDrawable()
    private var state = State.IDLE
    private var recorder: Recorder? = null
    /** The open take (recording or paused). */
    private var take: Take? = null
    /** Stopped takes whose text is still coming, oldest first. */
    private val finishing = ArrayDeque<Take>()
    /** Transcript that found no field to go into; Insert puts it in once one has focus. */
    private var pending: String? = null
    private var editableFocused = false
    /** A field has had focus: with "only while typing", the bubble stays up from then on. */
    private var stuck = false
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
    /** A single tap on the idle mic, waiting to see if a second tap makes it a double-tap. */
    private val singleTap = Runnable { singleTapPending = false; onTap() }
    private var singleTapPending = false
    /** Whether [place] last laid the mic out as the dot; render() re-places when that changes. */
    private var placedMini = false
    /** Whether [place] last laid the bar out open ([expanded]); an upward bar needs re-placing then. */
    private var placedExpanded = false
    /** [place] put the mic at the bottom of an upward bar (along the edge, mic in the lower half). */
    private var placedUp = false
    /** Until this uptime mic taps are ignored: the second tap of a double-tap that restored the dot. */
    private var ignoreTapsUntil = 0L
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
        take?.decoder?.cancel()
        take = null
        for (t in finishing) t.decoder.cancel()
        finishing.clear()
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
            Remote.Action.START -> if (!open) startRecording()
            Remote.Action.STOP -> if (open) stopAndTranscribe()
            Remote.Action.RESTART -> if (open) retake() else startRecording()
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
            // Only the rising edge changes what is shown: losing focus leaves the bubble up
            // (stuck), so it can still be moved and tapped (Daniel, 2026-10-22).
            if (editableFocused && !was) {
                Transcriber.preload(this)
                stuck = true
                render()
            }
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
            setOnTouchListener(Drag(::onMicTap, ::onLongPress))
        }
        timer = TextView(themed).apply {
            setTextColor(getColor(R.color.ime_text))
            textSize = 14f
            setPadding(dp(8), 0, dp(4), 0)
            setOnTouchListener(Drag())
        }
        fun button(drawable: Int, cd: Int, fill: Int? = null, action: () -> Unit) = ImageButton(themed).apply {
            setImageResource(drawable)
            contentDescription = getString(cd)
            scaleType = ImageView.ScaleType.FIT_CENTER
            // Retake and Discard get a filled circle (0.7.2), so they are easy to find and hit.
            background = fill?.let { GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(getColor(it)) } }
            setPadding(dp(10), dp(10), dp(10), dp(10))
            setOnClickListener { action() }
            setOnTouchListener(Drag({ performClick() }))
        }
        pauseBtn = button(R.drawable.ic_pause, R.string.pause) { togglePause() }
        source = TextView(themed).apply {
            setTextColor(getColor(R.color.ime_text))
            textSize = 12f
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
            maxWidth = dp(SOURCE_MAX_DP)
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(8), dp(4), dp(8), dp(4))
            background = GradientDrawable().apply { cornerRadius = dp(12).toFloat(); setColor(getColor(R.color.ime_key)) }
            setOnClickListener { switchMic() }
            setOnTouchListener(Drag({ performClick() }))
        }
        // Buttons on the left, timer and mic chip on the right, whichever edge the mic is on
        // (Daniel, 2026-10-21: "controls to the left and then the timer to the right").
        takeControls = listOf(
            pauseBtn,
            button(R.drawable.ic_retake, R.string.bubble_retake, R.color.bubble_retake) { retake() },
            button(R.drawable.ic_close, R.string.discard, R.color.bubble_discard) { discard() },
            timer,
            source,
        )
        insert = TextView(themed).apply {
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
        val dismiss = button(R.drawable.ic_close, R.string.bubble_dismiss) { dismissPending() }
        pendingControls = listOf(insert, dismiss)
        grip = ImageButton(themed).apply {
            setImageResource(R.drawable.ic_drag)
            scaleType = ImageView.ScaleType.FIT_CENTER
            contentDescription = getString(R.string.bubble_grip_cd)
            background = null
            alpha = 0.8f
            setOnTouchListener(Drag())
        }
        plainButtons = listOf(grip, pauseBtn, dismiss)
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

    /** The bar is showing: a take is open, or a transcript is waiting for Insert. */
    private fun expanded() = open || (pending != null && state == State.IDLE)

    /** True while the mic is shown as the small dot: minimised, idle and holding nothing. */
    private fun mini() = Prefs.bubbleMinimised(this) && state == State.IDLE && pending == null

    /** Diameter of the mic in px: the set size, or the dot's when minimised. */
    private fun micSize(): Int {
        val full = Prefs.bubbleSize(this)
        return dp(if (mini()) maxOf(full / Prefs.MINI_DIVISOR, Prefs.MINI_MIN) else full)
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
     * mic is the child next to that side. Along the edge (1.000) the bar is a column: below the
     * mic if the mic is in the top half, above it otherwise; above means the window's top is
     * moved up by the bar's measured height, so the mic itself stays put.
     */
    private fun place(attached: Boolean = true) {
        val r = root ?: return
        placedMini = mini()
        placedExpanded = expanded()
        val size = micSize()
        val m = resources.displayMetrics
        val w = m.widthPixels
        val pad = dp(PAD_DP)
        val x = micLeft(size)
        val left = x + size / 2 < w / 2
        val micTop = (Prefs.bubbleY(this) * (m.heightPixels - size)).toInt()
        val along = Prefs.bubbleBarDirection(this) == Prefs.BAR_ALONG
        val up = along && micTop + size / 2 > m.heightPixels / 2
        placedUp = up
        mic.removeAllViews()
        val inner = size - 2 * (size / 5)
        mic.addView(icon, FrameLayout.LayoutParams(inner, inner, Gravity.CENTER))
        mic.addView(spinner, FrameLayout.LayoutParams(inner, inner, Gravity.CENTER))
        r.removeAllViews()
        r.orientation = if (along) LinearLayout.VERTICAL else LinearLayout.HORIZONTAL
        // Along the edge the column hugs the mic's edge, so a wide chip can't shift the mic.
        r.gravity = if (along) (if (left) Gravity.LEFT else Gravity.RIGHT) else Gravity.CENTER_VERTICAL
        val scale = Prefs.bubbleBarScale(this) / 100f
        val btn = (BUTTON_DP * scale).toInt()
        val btnPad = (BUTTON_PAD_DP * scale).toInt()
        // The mic is the child nearest its edge (or, along it, nearest the middle of the screen's
        // far side); the grip is at the bar's other end; the bar keeps its own order.
        val bar = takeControls + pendingControls
        val micFirst = if (along) !up else left
        for (c in if (micFirst) listOf<View>(mic) + bar + grip else listOf<View>(grip) + bar + mic) {
            val lp = when {
                c === mic -> LinearLayout.LayoutParams(size, size)
                c is ImageButton -> LinearLayout.LayoutParams(dp(btn), dp(btn)).also { c.setPadding(dp(btnPad), dp(btnPad), dp(btnPad), dp(btnPad)) }
                else -> LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            }
            if (c !== mic) if (along) lp.setMargins(0, dp(2), 0, dp(2)) else lp.setMargins(dp(2), 0, dp(2), 0)
            r.addView(c, lp)
        }
        timer.textSize = 14f * scale
        source.textSize = 12f * scale
        source.maxWidth = dp(if (along) SOURCE_ALONG_DP else SOURCE_MAX_DP)
        insert.textSize = 15f * scale
        styleBackdrops()
        params.gravity = Gravity.TOP or if (left) Gravity.LEFT else Gravity.RIGHT
        params.x = (if (left) x - pad else w - x - size - pad).coerceAtLeast(0)
        params.y = if (up) {
            r.measure(View.MeasureSpec.UNSPECIFIED, View.MeasureSpec.UNSPECIFIED)
            micTop + size + pad - r.measuredHeight
        } else micTop - pad
        if (attached) runCatching { wm.updateViewLayout(r, params) }
    }

    /**
     * Clear bar: the plain buttons, the timer and Insert each get a mostly opaque backdrop
     * ([BACKDROP_ALPHA]) of the bar's colour; otherwise none, the bar's background does that job.
     * The mic chip and Retake / Discard have their own fills either way. One drawable per view.
     */
    private fun styleBackdrops() {
        val clear = Prefs.bubbleBarClear(this)
        fun backdrop(oval: Boolean) = GradientDrawable().apply {
            if (oval) shape = GradientDrawable.OVAL else cornerRadius = dp(12).toFloat()
            setColor(getColor(R.color.ime_bg))
            alpha = BACKDROP_ALPHA
        }
        for (b in plainButtons) b.background = if (clear) backdrop(true) else null
        timer.background = if (clear) backdrop(false) else null
        insert.background = if (clear) backdrop(false) else null
        val tp = if (clear) dp(6) else 0
        timer.setPadding(dp(8), tp, dp(if (clear) 8 else 4), tp)
    }

    /**
     * Saves where a drag ended. Parked on an edge: the side nearer the mic's centre (the prefs
     * listener snaps it there). Free: the exact spot.
     */
    private fun savePosition() {
        val size = micSize()
        val m = resources.displayMetrics
        val pad = dp(PAD_DP)
        val anchoredLeft = params.gravity and Gravity.HORIZONTAL_GRAVITY_MASK == Gravity.LEFT
        val x = if (anchoredLeft) params.x + pad else m.widthPixels - params.x - pad - size
        // An upward bar has the mic at the bottom of the window, not the top.
        val micTop = if (placedUp) params.y + (root?.height ?: 0) - pad - size else params.y + pad
        if (Prefs.bubbleSide(this) == Prefs.SIDE_FREE) {
            Prefs.setBubbleX(this, x.toFloat() / (m.widthPixels - size).coerceAtLeast(1))
        } else {
            Prefs.setBubbleSide(this, if (x + size / 2 < m.widthPixels / 2) Prefs.SIDE_LEFT else Prefs.SIDE_RIGHT)
        }
        Prefs.setBubbleY(this, (micTop.toFloat() / (m.heightPixels - size).coerceAtLeast(1)))
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

    /**
     * A tap on the mic. Minimised: bring it back. Idle: wait [ViewConfiguration.getDoubleTapTimeout]
     * for a second tap, which minimises it; no second tap starts a take. Otherwise (Stop, a held
     * transcript) at once.
     */
    private fun onMicTap() {
        val now = android.os.SystemClock.uptimeMillis()
        if (now < ignoreTapsUntil) return
        when {
            mini() -> {
                ignoreTapsUntil = now + ViewConfiguration.getDoubleTapTimeout()
                setMinimised(false)
            }
            state != State.IDLE || pending != null -> onTap()
            singleTapPending -> {
                main.removeCallbacks(singleTap)
                singleTapPending = false
                setMinimised(true)
            }
            else -> {
                singleTapPending = true
                main.postDelayed(singleTap, ViewConfiguration.getDoubleTapTimeout().toLong())
            }
        }
    }

    /** The bubble_ prefs listener re-places and re-renders it at the new size. */
    private fun setMinimised(v: Boolean) {
        if (Prefs.bubbleMinimised(this) == v) return
        mic.performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
        Prefs.setBubbleMinimised(this, v)
    }

    private fun hasMic() = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun onTap() {
        when {
            !ModelStore.isReady(this) || !hasMic() -> {
                toast(getString(if (!ModelStore.isReady(this)) R.string.ime_no_model else R.string.ime_no_permission))
                startActivity(Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
            open -> stopAndTranscribe()
            else -> startRecording()          // idle, or the last take still transcribing (B-43a)
        }
    }

    /** Idle: insert the last transcript again (it is kept in Prefs). False during a take: nothing to do. */
    private fun onLongPress(): Boolean {
        if (state != State.IDLE) return false
        val text = Prefs.lastTranscript(this)
        if (text == null) toast(getString(R.string.bubble_no_last)) else deliver(text, null, firstPart = true)
        return true
    }

    /** [into]: the field the take's text goes to; by default the one focused now. */
    private fun startRecording(cue: Feedback.Cue = Feedback.Cue.START,
                               into: AccessibilityNodeInfo? = focusedField()?.takeIf { !it.isPassword }) {
        Transcriber.preload(this)
        // A take started from a remote keeps the bubble up afterwards.
        stuck = true
        // Type as you go: each segment goes in when decoded. Otherwise it is all held for Stop.
        var t: Take? = null
        val d = TakeDecoder(this, if (Prefs.typeAsYouGo(this)) { text -> main.post { t?.let { deliverPart(it, text) } } } else null)
        t = Take(into, d)
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
        take = t
        showSource(r.routedDevice)
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
        take?.decoder?.cancel()
        take = null
        Mic.release(this)
    }

    /** No take open: TRANSCRIBING while earlier takes are still landing, else IDLE. */
    private fun settled() = if (finishing.isEmpty()) State.IDLE else State.TRANSCRIBING

    private fun showSource(d: android.media.AudioDeviceInfo?) {
        micName = Mic.shortLabel(this, d)
        source.text = micName
        source.contentDescription = getString(R.string.bubble_mic_cd, micName)
    }

    /**
     * The source chip was tapped (0.7.2): switch between Bluetooth and the phone's mic in the
     * middle of the take. The recorder pauses, re-routes and resumes, so the take keeps what it
     * had; paused, the switch applies on Resume. The choice is saved ([Mic.toggle]).
     */
    private fun switchMic() {
        val r = recorder ?: return
        if (!open) return
        if (!Mic.toggle(this, r.routedDevice ?: r.preferredDevice)) return toast(getString(R.string.bubble_no_headset))
        val wasRecording = state == State.RECORDING
        if (wasRecording) r.pause()
        Mic.release(this)
        Mic.prepare(this, r)
        if (wasRecording) {
            try {
                r.start()
            } catch (e: Exception) {
                state = State.PAUSED
                toast(getString(R.string.ime_mic_error, e.message ?: ""))
            }
        }
        showSource(if (wasRecording && state == State.RECORDING) r.routedDevice else r.preferredDevice)
        render()
    }

    /** Throws the take away and starts a fresh one at once, into the same field. */
    private fun retake() {
        if (!open) return
        val keep = take?.target
        dropTake()
        state = settled()
        startRecording(Feedback.Cue.RESTART, keep ?: focusedField()?.takeIf { !it.isPassword })
    }

    private fun discard() {
        if (!open) return
        dropTake()
        state = settled()
        Feedback.cue(this, Feedback.Cue.DISCARD)
        toast(getString(R.string.bubble_discarded))
        render()
    }

    private fun stopAndTranscribe() {
        val r = recorder ?: return
        val t = take ?: return
        recorder = null
        take = null
        val d = t.decoder
        val samples = r.stop()
        Mic.release(this)
        Feedback.cue(this, Feedback.Cue.STOP)
        if (samples.size < Transcriber.SAMPLE_RATE / 4 && d.segmentsQueued == 0) {
            d.cancel()
            state = settled()
            render()
            return toast(getString(R.string.ime_too_short))
        }
        finishing.addLast(t)
        state = State.TRANSCRIBING
        render()
        d.finish(samples) { result ->
            main.post {
                result.onSuccess { text -> if (text.isNotEmpty()) deliverPart(t, text) }
                t.ended = true
                t.error = result.exceptionOrNull()
                if (finishing.firstOrNull() === t) land(t)
            }
        }
    }

    /** [t] is the oldest take still landing and its decoder is done: wrap it up, then the next. */
    private fun land(t: Take) {
        finishing.remove(t)
        val err = t.error
        when {
            err != null -> toast(getString(R.string.ime_error, err.message ?: err.javaClass.simpleName))
            t.text.isEmpty() -> toast(getString(R.string.ime_nothing_heard))
            else -> {
                Prefs.setLastTranscript(this, t.text.toString())
                History.record(this, t.decoder.text, t.decoder.stats(), History.FLOATING)
            }
        }
        // The next take's turn: what it decoded meanwhile goes in now.
        val next = finishing.firstOrNull() ?: take
        if (next != null) {
            for (piece in next.waiting) deliverNow(next, piece)
            next.waiting.clear()
            if (next !== take && next.ended) return land(next)
        }
        if (!open) state = settled()
        render()
    }

    /** One piece of [t]'s text: in now, or held while an earlier take is still landing. */
    private fun deliverPart(t: Take, text: String) {
        val first = finishing.firstOrNull()
        if (first != null && first !== t) t.waiting.add(text) else deliverNow(t, text)
    }

    private fun deliverNow(t: Take, text: String) {
        t.text.append(TakeDecoder.join(t.text, text))
        deliver(text, t.target, firstPart = t.text.length <= text.length)
    }

    /**
     * Puts [text] at the cursor of the field the take started in, or else the focused field.
     * 1. Clipboard + ACTION_PASTE at the field's own cursor ([insertInto]; SET_TEXT first only
     *    to replace a placeholder).
     * 2. If the field refuses PASTE, ACTION_SET_TEXT: the whole field rewritten from its reported
     *    text and selection, then the cursor moved to the end of the insert.
     * 3. Otherwise it is held as [pending] (Insert button) and left on the clipboard.
     */
    private fun deliver(text: String, to: AccessibilityNodeInfo?, firstPart: Boolean) {
        val node = to?.takeIf { it.refresh() && it.isEditable }
            ?: focusedField()
        if (node == null || node.isPassword || !insertInto(node, text, firstPart)) hold(text)
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
     *    take has typed something ([Take.text]), so type-as-you-go can't wipe its own text.
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

    /**
     * True if [text] went into [node]. Clipboard + PASTE first, SET_TEXT as the fallback (0.9.1).
     * SET_TEXT rewrites the whole field from the text the app *reports*: the field jumps on every
     * piece (its scroll position is reset by the rewrite), and anything the app doesn't report is
     * deleted. Seen: the line break before the take was removed (0.7.5, and again in 0.9.0, where
     * the cursor did not give the hidden break away, so 0.7.6's cursor check missed it). PASTE
     * inserts at the field's own cursor and deletes nothing. The placeholder case keeps SET_TEXT,
     * because there the reported text has to be replaced. See docs/debug-log/2026-10-23-*.
     * A background service can't read the clipboard (Android 10+), so the user's old clip can't be
     * restored; the transcript is left there, which is also the useful fallback.
     */
    private fun insertInto(node: AccessibilityNodeInfo, text: String, firstPart: Boolean): Boolean {
        val reported = node.text?.toString() ?: ""
        val placeholder = isPlaceholder(node, reported, firstPart)
        val current = if (placeholder) "" else reported
        var start = node.textSelectionStart
        var end = node.textSelectionEnd
        // A cursor past the reported text: the app hides the field's tail (trailing line breaks).
        val hidden = maxOf(start, end) - current.length
        if (start !in 0..current.length || end !in 0..current.length) { start = current.length; end = current.length }
        if (start > end) start = end.also { end = start }
        if (placeholder) {
            if (setText(node, current, start, end, text)) {
                Log.i(TAG, "Replaced placeholder text (${reported.length} chars)")
                return true
            }
            copy(text)
            return node.performAction(AccessibilityNodeInfo.ACTION_PASTE).also { if (it) clipboardTip() }
        }
        // The separator is judged from what is before the cursor; a hidden tail ends in a break.
        val insert = TakeDecoder.join(if (hidden > 0) "\n" else current.substring(0, start), text)
        copy(insert)
        if (node.performAction(AccessibilityNodeInfo.ACTION_PASTE)) return true.also { clipboardTip() }
        Log.i(TAG, "Paste refused: rewriting the field")
        // Restore a hidden tail as line breaks (the case seen) so the rewrite doesn't drop it.
        if (hidden > 0) {
            val full = current + "\n".repeat(hidden)
            return setText(node, full, full.length, full.length, text)
        }
        return setText(node, current, start, end, text)
    }

    /**
     * ACTION_SET_TEXT with [current] (what the field holds) with [start]..[end] replaced by [text],
     * a space first if it would follow a word; then the cursor goes to the end of the insert.
     */
    private fun setText(node: AccessibilityNodeInfo, current: String, start: Int, end: Int, text: String): Boolean {
        val before = current.substring(0, start)
        val insert = TakeDecoder.join(before, text)
        val set = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, before + insert + current.substring(end))
        }
        if (!node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, set)) return false
        val cursor = start + insert.length
        node.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, Bundle().apply {
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, cursor)
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, cursor)
        })
        return true
    }

    /**
     * Android 12+ shows "<app> pasted from your clipboard" on every paste from another app's clip,
     * so every floating-mic insert triggers it (1.000, Daniel 2026-10-24: "definitely going to get
     * on everyone's nerves"). Apps can't suppress it: the switch is the secure setting
     * clipboard_show_access_notifications, which needs WRITE_SECURE_SETTINGS; the only way round it
     * is SET_TEXT, dropped in 0.9.1 for jumping fields and lost line breaks. So, once, a long toast
     * says where to turn it off; the Floating mic screen has a button to Privacy settings.
     */
    private fun clipboardTip() {
        if (android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.S || Prefs.clipboardTipShown(this)) return
        Prefs.setClipboardTipShown(this)
        main.postDelayed({ Toast.makeText(this, R.string.bubble_clipboard_tip, Toast.LENGTH_LONG).show() }, CLIPBOARD_TIP_DELAY_MS)
    }

    /** No field took [text]: keep it for the Insert button, and on the clipboard. */
    private fun hold(text: String) {
        val first = pending == null
        pending = pending?.let { it + TakeDecoder.join(it, text) } ?: text
        copy(pending!!)
        if (first) toast(getString(R.string.bubble_held))     // once, not again for every segment
        render()
    }

    /** Insert: the held text into whatever field has focus now, at its cursor. */
    private fun insertPending() {
        val text = pending ?: return
        val node = focusedField()?.takeIf { !it.isPassword }
            ?: return toast(getString(R.string.bubble_tap_field))
        if (!insertInto(node, text, firstPart = true)) return toast(getString(R.string.bubble_on_clipboard))
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
        val wanted = !Prefs.bubbleOnlyTyping(this) || editableFocused || stuck
        val show = wanted || state != State.IDLE || waiting
        r.visibility = if (show) View.VISIBLE else View.GONE
        r.background = if (open || waiting) barBg.apply { cornerRadius = dp(Prefs.bubbleSize(this@FloatingMicService)).toFloat() } else null
        for (c in takeControls) c.visibility = if (open) View.VISIBLE else View.GONE
        for (c in pendingControls) c.visibility = if (waiting) View.VISIBLE else View.GONE
        grip.visibility = if (open || waiting) View.VISIBLE else View.GONE
        // A take or a held transcript shows the full mic and bar; the dot comes back after. An
        // upward bar is placed from its measured height, so opening or closing it re-places too.
        if (mini() != placedMini || expanded() != placedExpanded) place()
        barBg.alpha = if (Prefs.bubbleBarClear(this)) 0 else Prefs.bubbleBarAlpha(this) * 255 / 100
        val iconStyle = Prefs.bubbleIcon(this)
        micBg.setColor(when {
            open && flashing() -> getColor(R.color.bubble_retake)
            open -> getColor(R.color.bubble_recording)
            iconStyle != Prefs.ICON_MIC -> getColor(R.color.hebrish_green)
            else -> Prefs.bubbleColor(this)
        })
        icon.setImageResource(when {
            open -> R.drawable.ic_stop
            iconStyle == Prefs.ICON_LOGO -> R.drawable.ic_bubble_h
            iconStyle == Prefs.ICON_AYIN -> R.drawable.ic_bubble_ayin
            else -> R.drawable.ic_mic
        })
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
     * Retake is otherwise too quick to see (the timer just goes back to 0:00): for [FLASH_MS] the
     * mic and the bar turn amber, the bar says "New take", and the mic's icon spins back once (the
     * ↺ of the Retake button), with or without sounds. render() keeps the mic amber while [flashing].
     */
    private fun flashRetake() {
        flashUntil = android.os.SystemClock.uptimeMillis() + FLASH_MS
        barBg.setColor(getColor(R.color.bubble_retake))
        timer.setText(R.string.bubble_new_take)
        icon.animate().cancel()
        icon.rotation = 0f
        icon.animate().rotation(-360f).setDuration(500).withEndAction { icon.rotation = 0f }
        main.postDelayed({
            if (flashing()) return@postDelayed
            barBg.setColor(getColor(R.color.ime_bg))
            shownSeconds = -1
            render()
        }, FLASH_MS)
    }

    private fun flashing() = android.os.SystemClock.uptimeMillis() < flashUntil

    private fun showTime() {
        if (flashing()) return
        val secs = recorder?.seconds ?: return
        if (secs == shownSeconds && state == State.RECORDING) return
        shownSeconds = secs
        timer.text = getString(if (state == State.PAUSED) R.string.bubble_paused_time else R.string.bubble_time, secs / 60, secs % 60)
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
        /** Widest the mic source chip gets; [Mic.shortLabel] already cuts long names. */
        const val SOURCE_MAX_DP = 110
        /** Widest the chip gets in a bar along the edge, so the column stays narrow. */
        const val SOURCE_ALONG_DP = 72
        /** A bar button at full size (Prefs.bubbleBarScale 100), and its padding round the icon. */
        const val BUTTON_DP = 44
        const val BUTTON_PAD_DP = 10
        /** Backdrop opacity (0..255) behind each control in a clear bar: mostly opaque. */
        const val BACKDROP_ALPHA = 230
        /** After Android's own clipboard toast, so the tip is not hidden behind it. */
        const val CLIPBOARD_TIP_DELAY_MS = 2500L
        /** Most nodes [findFocusedEditable] visits per search. */
        const val MAX_NODES = 1500
    }
}
