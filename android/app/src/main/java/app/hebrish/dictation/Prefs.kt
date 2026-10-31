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

    /** Accepted the floating mic's accessibility disclosure (0.8.0, [FloatingMicConsentActivity]). */
    fun a11yConsent(ctx: Context) = sp(ctx).getBoolean("a11y_consent", false)
    fun setA11yConsent(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("a11y_consent", v).apply()

    /** IME id the keyboard key returns to; null = automatic (see VoiceImeService.switchBack). */
    fun returnIme(ctx: Context): String? = sp(ctx).getString("return_ime", null)
    fun setReturnIme(ctx: Context, v: String?) = sp(ctx).edit().putString("return_ime", v).apply()

    /** The last system default keyboard that wasn't this one, noted whenever setup opens. */
    fun lastOtherIme(ctx: Context): String? = sp(ctx).getString("last_other_ime", null)
    fun setLastOtherIme(ctx: Context, v: String) = sp(ctx).edit().putString("last_other_ime", v).apply()

    /** The most recent transcript, for Insert last when it could not be typed into a field. */
    fun lastTranscript(ctx: Context): String? = sp(ctx).getString("last_transcript", null)
    fun setLastTranscript(ctx: Context, v: String) = sp(ctx).edit().putString("last_transcript", v).apply()

    /** The one-time tip about Android's "pasted from your clipboard" notice has been shown (1.000). */
    fun clipboardTipShown(ctx: Context) = sp(ctx).getBoolean("clipboard_tip_shown", false)
    fun setClipboardTipShown(ctx: Context) = sp(ctx).edit().putBoolean("clipboard_tip_shown", true).apply()

    /**
     * Long takes: insert each segment's text as soon as it is decoded (TakeDecoder's onText),
     * instead of all of it at Stop. Discard then only drops what hasn't gone in yet.
     */
    fun typeAsYouGo(ctx: Context) = sp(ctx).getBoolean("type_as_you_go", false)
    fun setTypeAsYouGo(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("type_as_you_go", v).apply()

    /** Keep every take in [History] (0.8.1). On by default, as on desktop (D-2026-10-22-13). */
    fun keepHistory(ctx: Context) = sp(ctx).getBoolean("keep_history", true)
    fun setKeepHistory(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("keep_history", v).apply()

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
    /** Transcription Mode (R-2026-10-24-5): its own mic (Mic.key or Mic.AUTO), gain in dB, level meter shown. */
    fun tmMic(ctx: Context): String = sp(ctx).getString("tm_mic", Mic.AUTO) ?: Mic.AUTO
    fun setTmMic(ctx: Context, v: String) = sp(ctx).edit().putString("tm_mic", v).apply()
    fun tmGainDb(ctx: Context) = sp(ctx).getInt("tm_gain_db", 0)
    fun setTmGainDb(ctx: Context, v: Int) = sp(ctx).edit().putInt("tm_gain_db", v).apply()
    fun tmShowMeter(ctx: Context) = sp(ctx).getBoolean("tm_show_meter", true)
    fun setTmShowMeter(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("tm_show_meter", v).apply()
    /** Transcription Mode keeps recording in the background (I-15; Setup's optional step). Off by default. */
    fun tmBackground(ctx: Context) = sp(ctx).getBoolean("tm_background", false)
    fun setTmBackground(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("tm_background", v).apply()
    /** Transcription Mode's Paragraphs setting (B-44a): ParagraphMode.key, or null until chosen ([ParagraphMode.get]). */
    fun tmParagraphs(ctx: Context): String? = sp(ctx).getString("tm_paragraphs", null)
    fun setTmParagraphs(ctx: Context, v: String) = sp(ctx).edit().putString("tm_paragraphs", v).apply()
    /** The installed paragraph-break model's manifest (ParagraphStore.Installed JSON), or null. */
    fun paragraphModel(ctx: Context): String? = sp(ctx).getString("paragraph_model", null)
    fun setParagraphModel(ctx: Context, v: String?) = sp(ctx).edit().putString("paragraph_model", v).apply()
    /** Transcription Mode's Clean up (B-40a; desktop `tm_cleanup`): run the clean-up model on each finished take. Off by default. */
    fun tmCleanup(ctx: Context) = sp(ctx).getBoolean("tm_cleanup", false)
    fun setTmCleanup(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("tm_cleanup", v).apply()
    /** The chosen clean-up model (a catalogue `addons` id), or null for the catalogue's default (CleanupStore.chosen). */
    fun cleanupChoice(ctx: Context): String? = sp(ctx).getString("cleanup_choice", null)
    fun setCleanupChoice(ctx: Context, v: String) = sp(ctx).edit().putString("cleanup_choice", v).apply()
    /** An installed clean-up model (CleanupStore.Installed JSON) by add-on id, or null. */
    fun cleanupModel(ctx: Context, id: String): String? = sp(ctx).getString("cleanup_model_$id", null)
    fun setCleanupModel(ctx: Context, id: String, v: String?) = sp(ctx).edit().putString("cleanup_model_$id", v).apply()
    /** The transcripts folder (B-74a): a Storage Access Framework tree URI with a persisted grant (TranscriptFolder), or null. */
    fun transcriptsTree(ctx: Context): String? = sp(ctx).getString("transcripts_tree", null)
    fun setTranscriptsTree(ctx: Context, v: String?) = sp(ctx).edit().putString("transcripts_tree", v).apply()
    /** Give saved transcripts a title (B-75a; desktop `titles`), when the title model is downloaded. On by default, as on desktop. */
    fun titles(ctx: Context) = sp(ctx).getBoolean("titles", true)
    fun setTitles(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("titles", v).apply()
    /** Longest title in characters (desktop `title_max_chars`); no setting on Android yet. */
    fun titleMaxChars(ctx: Context) = Titles.limit(sp(ctx).getInt("title_max_chars", Titles.MAX_CHARS))
    fun micChoice(ctx: Context): String = sp(ctx).getString("mic_choice", Mic.AUTO) ?: Mic.AUTO
    fun setMicChoice(ctx: Context, v: String) = sp(ctx).edit().putString("mic_choice", v).apply()

    /** Key code bound to a remote action, or 0 (KEYCODE_UNKNOWN) for none. */
    fun keyFor(ctx: Context, a: Remote.Action) = sp(ctx).getInt("key_" + a.name, 0)
    fun setKeyFor(ctx: Context, a: Remote.Action, keyCode: Int) = sp(ctx).edit().putInt("key_" + a.name, keyCode).apply()

    /**
     * Bound keys are taken at all (1.004). Off: FloatingMicService takes no key, so the remote works
     * in other apps, and the bindings stay stored. Learn still works while off. On by default.
     */
    fun keysOn(ctx: Context) = sp(ctx).getBoolean("key_bindings_on", true)
    fun setKeysOn(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("key_bindings_on", v).apply()

    /** Saved sets of bindings (1.004, Remote.saveProfile): JSON {name: {ACTION: keyCode}}, on this phone only. */
    fun keyProfiles(ctx: Context): String = sp(ctx).getString("key_profiles", "{}") ?: "{}"
    fun setKeyProfiles(ctx: Context, v: String) = sp(ctx).edit().putString("key_profiles", v).apply()

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

    /**
     * Screen edge the floating mic is parked on, or [SIDE_FREE]. Left by default since 1.000 (Daniel,
     * 2026-10-24); a value saved by an earlier drag or choice is kept.
     */
    fun bubbleSide(ctx: Context): String = sp(ctx).getString("bubble_side", SIDE_LEFT) ?: SIDE_LEFT
    fun setBubbleSide(ctx: Context, v: String) = sp(ctx).edit().putString("bubble_side", v).apply()

    /** Horizontal place when [SIDE_FREE]: 0 = left edge, 1 = right edge. */
    fun bubbleX(ctx: Context) = sp(ctx).getFloat("bubble_x", 0.1f)
    fun setBubbleX(ctx: Context, v: Float) = sp(ctx).edit().putFloat("bubble_x", v.coerceIn(0f, 1f)).apply()

    /** Gap between the mic and the edge it is parked on, in dp. */
    fun bubbleEdge(ctx: Context) = sp(ctx).getInt("bubble_edge", 6)
    fun setBubbleEdge(ctx: Context, v: Int) = sp(ctx).edit().putInt("bubble_edge", v.coerceIn(0, EDGE_MAX)).apply()
    const val EDGE_MAX = 48

    /** Opacity of the idle mic in percent; a take in progress is always fully opaque. */
    fun bubbleAlpha(ctx: Context) = sp(ctx).getInt("bubble_alpha", 85)
    fun setBubbleAlpha(ctx: Context, v: Int) = sp(ctx).edit().putInt("bubble_alpha", v.coerceIn(ALPHA_MIN, 100)).apply()
    /** 1 % since 1.000 (was 25): Daniel wanted every opacity control to go "all the way down". */
    const val ALPHA_MIN = 1

    /** Opacity of the bar's background during a take, in percent; the mic and buttons stay opaque. */
    fun bubbleBarAlpha(ctx: Context) = sp(ctx).getInt("bubble_bar_alpha", 100)
    fun setBubbleBarAlpha(ctx: Context, v: Int) = sp(ctx).edit().putInt("bubble_bar_alpha", v.coerceIn(BAR_ALPHA_MIN, 100)).apply()
    const val BAR_ALPHA_MIN = 1

    /** Colour of the idle mic (ARGB), one of [BUBBLE_COLORS]; during a take it is always red. */
    fun bubbleColor(ctx: Context) = sp(ctx).getInt("bubble_color", BUBBLE_COLORS[0])
    fun setBubbleColor(ctx: Context, v: Int) = sp(ctx).edit().putInt("bubble_color", v).apply()
    /** Hebrish blue (R.color.accent, the 0.4.0 colour), Hebrish green, purple, orange, slate, black. No red: that means recording. */
    val BUBBLE_COLORS = listOf(0xFF24527A, 0xFF0F6B5C, 0xFF6A3FA0, 0xFFB35400, 0xFF4A4F57, 0xFF111214).map { it.toInt() }

    /** Height of the floating mic: 0 = top of the screen, 1 = bottom. */
    fun bubbleY(ctx: Context) = sp(ctx).getFloat("bubble_y", 0.6f)
    fun setBubbleY(ctx: Context, v: Float) = sp(ctx).edit().putFloat("bubble_y", v.coerceIn(0f, 1f)).apply()

    /**
     * Diameter of the floating mic in dp, [SIZE_MIN]..[SIZE_MAX] (0.3.0 offered only 44, 56 and 68).
     * Default 44 since 1.000 (was 56; Daniel: "the default should also be smaller").
     */
    fun bubbleSize(ctx: Context) = sp(ctx).getInt("bubble_size", 44).coerceIn(SIZE_MIN, SIZE_MAX)
    fun setBubbleSize(ctx: Context, v: Int) = sp(ctx).edit().putInt("bubble_size", v.coerceIn(SIZE_MIN, SIZE_MAX)).apply()
    /** 20 dp since 1.000 (was 36): about the smallest a finger still hits. */
    const val SIZE_MIN = 20
    const val SIZE_MAX = 96

    /**
     * Size of the bar's buttons and text during a take, in percent of the full size (1.000):
     * smaller covers less of what you are writing. The mic itself keeps [bubbleSize].
     */
    fun bubbleBarScale(ctx: Context) = sp(ctx).getInt("bubble_bar_scale", 80).coerceIn(BAR_SCALE_MIN, 100)
    fun setBubbleBarScale(ctx: Context, v: Int) = sp(ctx).edit().putInt("bubble_bar_scale", v.coerceIn(BAR_SCALE_MIN, 100)).apply()
    const val BAR_SCALE_MIN = 50

    /**
     * Clear bar (1.000): no bar background at all; each button, the timer and the mic chip sit on
     * their own mostly opaque backdrop, so the text under the bar shows between them.
     */
    fun bubbleBarClear(ctx: Context) = sp(ctx).getBoolean("bubble_bar_clear", false)
    fun setBubbleBarClear(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("bubble_bar_clear", v).apply()

    /** The bar opens across the screen, towards the middle (0.4.0 to 0.10.0). */
    const val BAR_ACROSS = "across"
    /** The bar opens along the edge the mic is on, up or down towards the middle: a narrow strip. */
    const val BAR_ALONG = "along"
    /**
     * Which way the bar opens during a take (1.000). Along the edge by default: it covers a
     * narrow strip at the side instead of a line across the text (Daniel, 2026-10-24: "the expansion
     * happens in the least obtrusive part of the screen").
     */
    fun bubbleBarDirection(ctx: Context): String = sp(ctx).getString("bubble_bar_direction", BAR_ALONG) ?: BAR_ALONG
    fun setBubbleBarDirection(ctx: Context, v: String) = sp(ctx).edit().putString("bubble_bar_direction", v).apply()

    const val ICON_MIC = "mic"
    /** The H of the Hebrish mark on Hebrish green. */
    const val ICON_LOGO = "logo"
    /** The Hebrew letter ayin (the first letter of עבריש) on Hebrish green. */
    const val ICON_AYIN = "ayin"
    /** What the idle mic shows (1.000). [ICON_LOGO] and [ICON_AYIN] are always on Hebrish green; [bubbleColor] is for [ICON_MIC]. */
    fun bubbleIcon(ctx: Context): String = sp(ctx).getString("bubble_icon", ICON_MIC) ?: ICON_MIC
    fun setBubbleIcon(ctx: Context, v: String) = sp(ctx).edit().putString("bubble_icon", v).apply()

    /** Show the floating mic only while a text field has focus (otherwise always, and during a take). */
    fun bubbleOnlyTyping(ctx: Context) = sp(ctx).getBoolean("bubble_only_typing", false)
    fun setBubbleOnlyTyping(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("bubble_only_typing", v).apply()

    /**
     * The floating mic is minimised (0.7.7): double-tap the idle mic to shrink it to a small dot
     * ([MINI_DIVISOR] of its size), tap the dot to bring it back. Kept across restarts.
     */
    fun bubbleMinimised(ctx: Context) = sp(ctx).getBoolean("bubble_minimised", false)
    fun setBubbleMinimised(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("bubble_minimised", v).apply()
    const val MINI_DIVISOR = 3
    /** Smallest the minimised dot gets, in dp, so it can still be found and hit. */
    const val MINI_MIN = 16

    fun listen(ctx: Context, l: SharedPreferences.OnSharedPreferenceChangeListener) = sp(ctx).registerOnSharedPreferenceChangeListener(l)
    fun unlisten(ctx: Context, l: SharedPreferences.OnSharedPreferenceChangeListener) = sp(ctx).unregisterOnSharedPreferenceChangeListener(l)
}
