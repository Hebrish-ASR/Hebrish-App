package app.hebrish.dictation

import android.content.Context
import android.graphics.Rect
import android.os.Bundle
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityNodeInfo.AccessibilityAction
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView

/**
 * The standing mic order on the Controls screen (1.018): one row per [MicKind], reordered by
 * dragging its handle. This view takes the whole gesture, because moving a child that holds the
 * touch would cancel it. TalkBack users get Move up / Move down actions on each row.
 */
class MicOrderView(ctx: Context, private val changed: (List<MicKind>) -> Unit) : LinearLayout(ctx) {
    private val handles = HashMap<View, View>()
    private var dragged: View? = null
    private var startY = 0f
    private val hit = Rect()

    init { orientation = VERTICAL }

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun order() = (0 until childCount).map { getChildAt(it).tag as MicKind }

    /** Shows [order]; [status] gives each kind's second line (what is connected). */
    fun show(order: List<MicKind>, status: (MicKind) -> String) {
        if (dragged != null) return
        removeAllViews()
        handles.clear()
        for (kind in order) addView(row(kind, status(kind)))
    }

    private fun row(kind: MicKind, status: String): View {
        val color = context.getColor(R.color.brand_ink)
        val name = context.getString(Mic.kindName(kind))
        val row = LinearLayout(context).apply {
            tag = kind
            orientation = HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = dp(56)
            setBackgroundColor(context.getColor(R.color.brand_bg))
            contentDescription = "$name. $status"
            accessibilityDelegate = moves
            isFocusable = true
        }
        row.addView(ImageView(context).apply {
            setImageResource(Mic.icon(kind))
            setColorFilter(color)
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }, LayoutParams(dp(24), dp(24)).apply { marginEnd = dp(14) })
        row.addView(LinearLayout(context).apply {
            orientation = VERTICAL
            addView(TextView(context).apply { text = name; setTextColor(color); textSize = 16f })
            addView(TextView(context).apply { text = status; setTextColor(color); alpha = 0.7f; textSize = 13f })
        }, LayoutParams(0, LayoutParams.WRAP_CONTENT, 1f))
        val handle = ImageView(context).apply {
            setImageResource(R.drawable.ic_drag)
            setColorFilter(color)
            setPadding(dp(12), dp(12), 0, dp(12))
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }
        row.addView(handle, LayoutParams(dp(48), dp(48)))
        handles[row] = handle
        return row
    }

    private val moves = object : View.AccessibilityDelegate() {
        override fun onInitializeAccessibilityNodeInfo(host: View, info: AccessibilityNodeInfo) {
            super.onInitializeAccessibilityNodeInfo(host, info)
            val i = indexOfChild(host)
            if (i > 0) info.addAction(AccessibilityAction(R.id.mic_move_up, context.getString(R.string.controls_mic_move_up)))
            if (i < childCount - 1) info.addAction(AccessibilityAction(R.id.mic_move_down, context.getString(R.string.controls_mic_move_down)))
        }

        override fun performAccessibilityAction(host: View, action: Int, args: Bundle?): Boolean {
            val to = indexOfChild(host) + when (action) {
                R.id.mic_move_up -> -1
                R.id.mic_move_down -> 1
                else -> return super.performAccessibilityAction(host, action, args)
            }
            if (to !in 0 until childCount) return false
            move(host, to)
            changed(order())
            return true
        }
    }

    private fun move(row: View, to: Int) {
        removeView(row)
        addView(row, to)
    }

    private fun handleAt(e: MotionEvent): View? {
        for (i in 0 until childCount) {
            val row = getChildAt(i)
            val handle = handles[row] ?: continue
            handle.getHitRect(hit)
            hit.offset(row.left, row.top)
            if (hit.contains(e.x.toInt(), e.y.toInt())) return row
        }
        return null
    }

    override fun onInterceptTouchEvent(e: MotionEvent) = e.actionMasked == MotionEvent.ACTION_DOWN && handleAt(e) != null

    override fun onTouchEvent(e: MotionEvent): Boolean {
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                val row = handleAt(e) ?: return false
                dragged = row
                startY = e.y
                row.elevation = dp(6).toFloat()
                row.performHapticFeedback(android.view.HapticFeedbackConstants.CLOCK_TICK)
                // The Controls screen scrolls; it must not take this gesture.
                parent?.requestDisallowInterceptTouchEvent(true)
            }
            MotionEvent.ACTION_MOVE -> dragged?.let { drag(it, e.y) }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> dragged?.let {
                dragged = null
                it.translationY = 0f
                it.elevation = 0f
                changed(order())
            }
        }
        return dragged != null
    }

    /** Follows the finger, swapping with a neighbour once the row is halfway over it. */
    private fun drag(row: View, y: Float) {
        val i = indexOfChild(row)
        var dy = y - startY
        val below = getChildAt(i + 1)
        val above = getChildAt(i - 1)
        if (below != null && dy > below.height / 2f) {
            move(row, i + 1)
            startY += below.height
            dy -= below.height
            row.performHapticFeedback(android.view.HapticFeedbackConstants.CLOCK_TICK)
        } else if (above != null && dy < -above.height / 2f) {
            move(row, i - 1)
            startY -= above.height
            dy += above.height
            row.performHapticFeedback(android.view.HapticFeedbackConstants.CLOCK_TICK)
        }
        row.translationY = dy
    }
}
