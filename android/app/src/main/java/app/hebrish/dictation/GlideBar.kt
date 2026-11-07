package app.hebrish.dictation

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Shader
import android.view.View
import android.view.animation.DecelerateInterpolator

/**
 * The download bar: a slim rounded track whose fill glides to each new value. A download reports
 * in jumps (2 MB, at most 5 times a second), so the fill eases towards the latest figure instead
 * of stepping there, and a soft sheen crosses it while it is on screen, so a stalled moment still
 * looks alive. The desktop's twin is ui/glidebar.py: keep the height, timings and colours the
 * same. With animations off in system settings both animators jump to their end.
 */
class GlideBar(context: Context) : View(context) {
    /** Where the fill is now, 0 to 1: pass it to [jumpTo] on a new bar to carry on from here. */
    var shown = 0f
        private set
    private var sheen = 0f
    private val track = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = context.getColor(R.color.brand_line) }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = context.getColor(R.color.brand_accent) }
    private val shine = Paint(Paint.ANTI_ALIAS_FLAG)
    private val rect = RectF()
    private val path = Path()
    private var glide: ValueAnimator? = null
    private val sheenAnim = ValueAnimator.ofFloat(0f, 1f).apply {
        duration = SHEEN_MS
        repeatCount = ValueAnimator.INFINITE
        addUpdateListener { sheen = it.animatedValue as Float; invalidate() }
    }

    fun jumpTo(fraction: Float) {
        glide?.cancel()
        shown = fraction.coerceIn(0f, 1f)
        invalidate()
    }

    /** Glides from wherever the fill is now to [fraction]. */
    fun glideTo(fraction: Float) {
        glide?.cancel()
        glide = ValueAnimator.ofFloat(shown, fraction.coerceIn(0f, 1f)).apply {
            duration = GLIDE_MS
            interpolator = DecelerateInterpolator(1.5f)
            addUpdateListener { shown = it.animatedValue as Float; invalidate() }
            start()
        }
    }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        sheenAnim.start()
    }

    override fun onDetachedFromWindow() {
        super.onDetachedFromWindow()
        glide?.cancel()
        sheenAnim.cancel()
    }

    override fun onDraw(canvas: Canvas) {
        val h = height.toFloat()
        val w = width.toFloat()
        val radius = h / 2
        rect.set(0f, 0f, w, h)
        canvas.drawRoundRect(rect, radius, radius, track)
        val end = w * shown
        if (end < h) return                       // too short to round: wait for the first few pixels
        rect.right = end
        canvas.drawRoundRect(rect, radius, radius, fill)
        val band = w * SHEEN_WIDTH
        val x = -band + (end + band) * sheen
        shine.shader = LinearGradient(x, 0f, x + band, 0f,
            intArrayOf(Color.TRANSPARENT, Color.argb(90, 255, 255, 255), Color.TRANSPARENT), null, Shader.TileMode.CLAMP)
        path.rewind()
        path.addRoundRect(rect, radius, radius, Path.Direction.CW)
        canvas.drawPath(path, shine)
    }

    private companion object {
        const val GLIDE_MS = 350L
        const val SHEEN_MS = 1600L
        const val SHEEN_WIDTH = 0.3f              // of the bar's width
    }
}
