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

    /**
     * Long takes: insert each segment's text as soon as it is decoded (TakeDecoder's onText),
     * instead of all of it at Stop. Discard then only drops what hasn't gone in yet.
     */
    fun typeAsYouGo(ctx: Context) = sp(ctx).getBoolean("type_as_you_go", false)
    fun setTypeAsYouGo(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("type_as_you_go", v).apply()

    /** The microphone prompt has been shown once (SetupActivity: after a refusal, App info is the only way). */
    fun micAsked(ctx: Context) = sp(ctx).getBoolean("mic_asked", false)
    fun setMicAsked(ctx: Context) = sp(ctx).edit().putBoolean("mic_asked", true).apply()

    // Sound, microphone and buttons (ControlsActivity; Feedback, Mic, Remote). 0.6.0.

    /** Short pips when a take starts, stops, restarts or is discarded (Feedback). Off by default. */
    fun beeps(ctx: Context) = sp(ctx).getBoolean("beeps", false)
    fun setBeeps(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("beeps", v).apply()

    /** A short buzz at the same moments. On by default. */
    fun vibrate(ctx: Context) = sp(ctx).getBoolean("vibrate", true)
    fun setVibrate(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("vibrate", v).apply()

    /** Mic.AUTO (Bluetooth first) or a Mic.key of a chosen microphone. */
    fun micChoice(ctx: Context): String = sp(ctx).getString("mic_choice", Mic.AUTO) ?: Mic.AUTO
    fun setMicChoice(ctx: Context, v: String) = sp(ctx).edit().putString("mic_choice", v).apply()

    /** Key code bound to a remote action, or 0 (KEYCODE_UNKNOWN) for none. */
    fun keyFor(ctx: Context, a: Remote.Action) = sp(ctx).getInt("key_" + a.name, 0)
    fun setKeyFor(ctx: Context, a: Remote.Action, keyCode: Int) = sp(ctx).edit().putInt("key_" + a.name, keyCode).apply()

    /** While set, the next hardware key FloatingMicService sees is bound to this action (its name). */
    fun learning(ctx: Context): String? = sp(ctx).getString("key_learning", null)
    fun setLearning(ctx: Context, a: Remote.Action?) = sp(ctx).edit().putString("key_learning", a?.name).apply()

    /**
     * Floating mic: treat short text with no real cursor as the field's placeholder and replace
     * it (WhatsApp reports "Message" as the field's text). On by default; FloatingMicService.isPlaceholder.
     */
    fun clearPlaceholder(ctx: Context) = sp(ctx).getBoolean("clear_placeholder", true)
    fun setClearPlaceholder(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("clear_placeholder", v).apply()

    // Floating mic (FloatingMicService). Keys start with "bubble_": the service re-places itself on any change.
    const val SIDE_LEFT = "left"
    const val SIDE_RIGHT = "right"
    /** Anywhere: no snapping to an edge; the horizontal place is [bubbleX]. */
    const val SIDE_FREE = "free"

    /** Screen edge the floating mic is parked on, or [SIDE_FREE]. */
    fun bubbleSide(ctx: Context): String = sp(ctx).getString("bubble_side", SIDE_RIGHT) ?: SIDE_RIGHT
    fun setBubbleSide(ctx: Context, v: String) = sp(ctx).edit().putString("bubble_side", v).apply()

    /** Horizontal place when [SIDE_FREE]: 0 = left edge, 1 = right edge. */
    fun bubbleX(ctx: Context) = sp(ctx).getFloat("bubble_x", 0.9f)
    fun setBubbleX(ctx: Context, v: Float) = sp(ctx).edit().putFloat("bubble_x", v.coerceIn(0f, 1f)).apply()

    /** Gap between the mic and the edge it is parked on, in dp. */
    fun bubbleEdge(ctx: Context) = sp(ctx).getInt("bubble_edge", 6)
    fun setBubbleEdge(ctx: Context, v: Int) = sp(ctx).edit().putInt("bubble_edge", v.coerceIn(0, EDGE_MAX)).apply()
    const val EDGE_MAX = 48

    /** Opacity of the idle mic in percent; a take in progress is always fully opaque. */
    fun bubbleAlpha(ctx: Context) = sp(ctx).getInt("bubble_alpha", 85)
    fun setBubbleAlpha(ctx: Context, v: Int) = sp(ctx).edit().putInt("bubble_alpha", v.coerceIn(ALPHA_MIN, 100)).apply()
    const val ALPHA_MIN = 25

    /** Opacity of the bar's background during a take, in percent; the mic and buttons stay opaque. */
    fun bubbleBarAlpha(ctx: Context) = sp(ctx).getInt("bubble_bar_alpha", 100)
    fun setBubbleBarAlpha(ctx: Context, v: Int) = sp(ctx).edit().putInt("bubble_bar_alpha", v.coerceIn(BAR_ALPHA_MIN, 100)).apply()
    const val BAR_ALPHA_MIN = 20

    /** Colour of the idle mic (ARGB), one of [BUBBLE_COLORS]; during a take it is always red. */
    fun bubbleColor(ctx: Context) = sp(ctx).getInt("bubble_color", BUBBLE_COLORS[0])
    fun setBubbleColor(ctx: Context, v: Int) = sp(ctx).edit().putInt("bubble_color", v).apply()
    /** Hebrish blue (R.color.accent, the 0.4.0 colour), Hebrish green, purple, orange, slate, black. No red: that means recording. */
    val BUBBLE_COLORS = listOf(0xFF24527A, 0xFF0F6B5C, 0xFF6A3FA0, 0xFFB35400, 0xFF4A4F57, 0xFF111214).map { it.toInt() }

    /** Height of the floating mic: 0 = top of the screen, 1 = bottom. */
    fun bubbleY(ctx: Context) = sp(ctx).getFloat("bubble_y", 0.6f)
    fun setBubbleY(ctx: Context, v: Float) = sp(ctx).edit().putFloat("bubble_y", v.coerceIn(0f, 1f)).apply()

    /** Diameter of the floating mic in dp, [SIZE_MIN]..[SIZE_MAX] (0.3.0 offered only 44, 56 and 68). */
    fun bubbleSize(ctx: Context) = sp(ctx).getInt("bubble_size", 56).coerceIn(SIZE_MIN, SIZE_MAX)
    fun setBubbleSize(ctx: Context, v: Int) = sp(ctx).edit().putInt("bubble_size", v.coerceIn(SIZE_MIN, SIZE_MAX)).apply()
    const val SIZE_MIN = 36
    const val SIZE_MAX = 96

    /** Show the floating mic only while a text field has focus (otherwise always, and during a take). */
    fun bubbleOnlyTyping(ctx: Context) = sp(ctx).getBoolean("bubble_only_typing", false)
    fun setBubbleOnlyTyping(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("bubble_only_typing", v).apply()

    fun listen(ctx: Context, l: SharedPreferences.OnSharedPreferenceChangeListener) = sp(ctx).registerOnSharedPreferenceChangeListener(l)
    fun unlisten(ctx: Context, l: SharedPreferences.OnSharedPreferenceChangeListener) = sp(ctx).unregisterOnSharedPreferenceChangeListener(l)
}
