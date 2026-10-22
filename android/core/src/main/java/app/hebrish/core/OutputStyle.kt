package app.hebrish.core

import android.content.Context

/**
 * How transcripts are written out, applied by [TakeDecoder] to every piece of text it hands over,
 * so the keyboard, the floating mic and the Try screen all get it (0.7.5). Same SharedPreferences
 * file as [ModelPrefs].
 */
object OutputStyle {
    private fun sp(ctx: Context) = ctx.getSharedPreferences("prefs", Context.MODE_PRIVATE)

    /** ALL CAPS: everything is typed in capitals. Just for fun (Daniel, 2026-10-22). */
    fun allCaps(ctx: Context) = sp(ctx).getBoolean("all_caps", false)
    fun setAllCaps(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("all_caps", v).apply()

    /** [text] as it should be typed. uppercase() is locale-independent (no Turkish dotted İ). */
    fun apply(text: String, allCaps: Boolean): String = if (allCaps) text.uppercase() else text
}
