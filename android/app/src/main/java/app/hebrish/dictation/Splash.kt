package app.hebrish.dictation

import android.app.Activity
import android.os.Build
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.animation.PathInterpolator
import android.widget.FrameLayout
import android.widget.ImageView

/**
 * Opening the app: the mark turns once round, then the home screen fades in (Daniel, 2026-11-07:
 * "the logo kind of just turns round for a second"). The desktop's twin is ui/splash.py: same turn
 * and timing.
 *
 * Android 12+ always shows its own splash screen, so the turn runs on that screen's icon
 * (AppTheme.Launch in values-v31 sets the icon and background) and there is one splash, not two.
 * Android 9 to 11 have none, so a cover with the same drawable does the same thing.
 */
object Splash {
    private const val SPIN_MS = 900L
    private const val FADE_MS = 220L
    private const val ICON_DP = 288               // the size Android 12+ gives a splash icon with no background

    /** Call from onCreate, before the first frame. [root] is the screen's top view. */
    fun play(activity: Activity, root: ViewGroup) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            activity.splashScreen.setOnExitAnimationListener { view ->
                val icon = view.iconView
                if (icon == null) view.remove() else spin(icon) { fade(view) { view.remove() } }
            }
            return
        }
        val size = (ICON_DP * activity.resources.displayMetrics.density).toInt()
        val icon = ImageView(activity).apply { setImageResource(R.drawable.splash_mark) }
        val cover = FrameLayout(activity).apply {
            setBackgroundColor(activity.getColor(R.color.brand_bg))
            isClickable = true                    // taps don't reach the screen underneath
            addView(icon, FrameLayout.LayoutParams(size, size, Gravity.CENTER))
        }
        root.addView(cover, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        spin(icon) { fade(cover) { root.removeView(cover) } }
    }

    private fun spin(icon: View, then: () -> Unit) {
        icon.animate().rotationBy(360f).setDuration(SPIN_MS)
            .setInterpolator(PathInterpolator(0.65f, 0f, 0.35f, 1f))   // ease in and out
            .withEndAction(then).start()
    }

    private fun fade(view: View, then: () -> Unit) {
        view.animate().alpha(0f).setDuration(FADE_MS).withEndAction(then).start()
    }
}
