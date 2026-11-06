package app.hebrish.dictation

import android.graphics.drawable.GradientDrawable
import android.media.AudioDeviceInfo
import android.view.View
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout

/**
 * The row of mic icons that opens from a source chip (1.018): one round button per connected mic,
 * best first, the one in use filled. The floating mic and the keyboard both use it.
 */
object MicPicker {
    /** How long an untouched picker stays open before going back to the chip. */
    const val OPEN_MS = 6000L

    /** Fills [row]. [wire] lets the caller add its own touch handling to each button. */
    fun fill(row: LinearLayout, current: AudioDeviceInfo?, sizePx: Int, wire: (View) -> Unit = {}, onPick: (AudioDeviceInfo) -> Unit) {
        val ctx = row.context
        val pad = sizePx / 5
        val gap = sizePx / 12
        row.removeAllViews()
        for (d in Mic.choices(ctx)) {
            val inUse = current?.let { Mic.key(it) } == Mic.key(d) || (current == null && Mic.kind(d) == MicKind.PHONE)
            val b = ImageButton(ctx).apply {
                setImageResource(Mic.icon(Mic.kind(d)))
                setColorFilter(ctx.getColor(R.color.ime_text))
                scaleType = ImageView.ScaleType.FIT_CENTER
                contentDescription = Mic.label(ctx, d)
                isSelected = inUse
                setPadding(pad, pad, pad, pad)
                background = GradientDrawable().apply {
                    shape = GradientDrawable.OVAL
                    if (inUse) setColor(ctx.getColor(R.color.ime_key)) else setColor(android.graphics.Color.TRANSPARENT)
                    setStroke(maxOf(1, sizePx / 24), ctx.getColor(R.color.ime_key))
                }
                setOnClickListener { onPick(d) }
            }
            wire(b)
            row.addView(b, LinearLayout.LayoutParams(sizePx, sizePx).apply { setMargins(gap, gap, gap, gap) })
        }
    }
}
