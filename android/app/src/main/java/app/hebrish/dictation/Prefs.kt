package app.hebrish.dictation

import android.content.Context
import android.content.SharedPreferences

object Prefs {
    private fun sp(ctx: Context) = ctx.getSharedPreferences("prefs", Context.MODE_PRIVATE)

    /** Start recording as soon as the voice keyboard opens (e.g. from HeliBoard's mic key). */
    fun autoStart(ctx: Context) = sp(ctx).getBoolean("auto_start", true)
    fun setAutoStart(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("auto_start", v).apply()

    /** Switch back to the previous keyboard after inserting a transcript. */
    fun autoReturn(ctx: Context) = sp(ctx).getBoolean("auto_return", true)
    fun setAutoReturn(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("auto_return", v).apply()

    /** Back (key or gesture) switches to the regular keyboard instead of only hiding this one. */
    fun backSwitches(ctx: Context) = sp(ctx).getBoolean("back_switches", true)
    fun setBackSwitches(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("back_switches", v).apply()

    /** IME id the keyboard key returns to; null = automatic (see VoiceImeService.switchBack). */
    fun returnIme(ctx: Context): String? = sp(ctx).getString("return_ime", null)
    fun setReturnIme(ctx: Context, v: String?) = sp(ctx).edit().putString("return_ime", v).apply()

    /** The last system default keyboard that wasn't this one, noted whenever setup opens. */
    fun lastOtherIme(ctx: Context): String? = sp(ctx).getString("last_other_ime", null)
    fun setLastOtherIme(ctx: Context, v: String) = sp(ctx).edit().putString("last_other_ime", v).apply()

    /** The most recent transcript, for Insert last when it could not be typed into a field. */
    fun lastTranscript(ctx: Context): String? = sp(ctx).getString("last_transcript", null)
    fun setLastTranscript(ctx: Context, v: String) = sp(ctx).edit().putString("last_transcript", v).apply()

    // Floating mic (FloatingMicService). Keys start with "bubble_": the service re-places itself on any change.
    const val SIDE_LEFT = "left"
    const val SIDE_RIGHT = "right"

    /** Screen edge the floating mic is parked on. */
    fun bubbleSide(ctx: Context): String = sp(ctx).getString("bubble_side", SIDE_RIGHT) ?: SIDE_RIGHT
    fun setBubbleSide(ctx: Context, v: String) = sp(ctx).edit().putString("bubble_side", v).apply()

    /** Height of the floating mic: 0 = top of the screen, 1 = bottom. */
    fun bubbleY(ctx: Context) = sp(ctx).getFloat("bubble_y", 0.6f)
    fun setBubbleY(ctx: Context, v: Float) = sp(ctx).edit().putFloat("bubble_y", v).apply()

    /** Diameter of the floating mic in dp (one of [BUBBLE_SIZES]). */
    fun bubbleSize(ctx: Context) = sp(ctx).getInt("bubble_size", BUBBLE_SIZES[1])
    fun setBubbleSize(ctx: Context, v: Int) = sp(ctx).edit().putInt("bubble_size", v).apply()
    val BUBBLE_SIZES = intArrayOf(44, 56, 68)

    /** Show the floating mic only while a text field has focus (otherwise always, and during a take). */
    fun bubbleOnlyTyping(ctx: Context) = sp(ctx).getBoolean("bubble_only_typing", false)
    fun setBubbleOnlyTyping(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("bubble_only_typing", v).apply()

    fun listen(ctx: Context, l: SharedPreferences.OnSharedPreferenceChangeListener) = sp(ctx).registerOnSharedPreferenceChangeListener(l)
    fun unlisten(ctx: Context, l: SharedPreferences.OnSharedPreferenceChangeListener) = sp(ctx).unregisterOnSharedPreferenceChangeListener(l)
}
