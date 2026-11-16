package app.hebrish.dictation

import android.content.Context
import android.os.Build
import android.util.Log
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.view.inputmethod.InputMethodSubtype
import app.hebrish.core.Catalogue
import app.hebrish.core.ModelStore

/**
 * Which language a take is in, English or Hebrew (2026-11-16; docs/maintaining.md, "Hebrew model
 * switching"). Decided once at the start of each take. [decide] is pure (unit-tested in
 * InputLanguageTest); [forKeyboard] and [forApp] gather the Android signals for it.
 *
 * Auto, in order:
 * 1. This IME's own subtype is Hebrew: the user picked "Hebrish (Hebrew)" in the system picker.
 *    Its English subtype says nothing (it is the one keyboards' mic keys open), so it is skipped.
 * 2. The keyboard the user came from: `getLastInputMethodSubtype()` (the voice keyboard), or the
 *    current keyboard's subtype (floating mic, Try it, Notes: no previous keyboard there).
 * 3. The field's `EditorInfo.hintLocales` (API 24+): its first locale, a hint the app sets.
 * 4. English.
 */
object InputLanguage {
    enum class Mode { AUTO, ENGLISH, HEBREW }

    /** What decided a take: logged under [TAG] and kept for the status line. */
    enum class Source { TOGGLE, OWN_SUBTYPE, KEYBOARD_SUBTYPE, HINT_LOCALES, DEFAULT }

    data class Decision(val hebrew: Boolean, val source: Source)

    const val TAG = "HebrishLanguage"

    /** A BCP 47 tag or old-style locale ("he", "he-IL", "he_IL", "iw", "iw_IL") for Hebrew. */
    fun isHebrew(tag: String?): Boolean {
        val t = tag?.trim()?.lowercase() ?: return false
        val lang = t.substringBefore('-').substringBefore('_')
        return lang == "he" || lang == "iw"
    }

    /** A tag that names a language at all (an empty subtype locale doesn't). */
    private fun known(tag: String?) = !tag.isNullOrBlank() && tag.trim().lowercase() != "und"

    /**
     * Pure. [ownSubtype]: this IME's current subtype tag (null outside the IME); [keyboardSubtype]:
     * the previous (IME) or current (elsewhere) keyboard's subtype tag; [hintLocales]: the field's.
     */
    fun decide(mode: Mode, ownSubtype: String?, keyboardSubtype: String?, hintLocales: List<String>): Decision = when (mode) {
        Mode.ENGLISH -> Decision(false, Source.TOGGLE)
        Mode.HEBREW -> Decision(true, Source.TOGGLE)
        Mode.AUTO -> when {
            isHebrew(ownSubtype) -> Decision(true, Source.OWN_SUBTYPE)
            known(keyboardSubtype) -> Decision(isHebrew(keyboardSubtype), Source.KEYBOARD_SUBTYPE)
            hintLocales.firstOrNull { known(it) } != null -> Decision(isHebrew(hintLocales.first { known(it) }), Source.HINT_LOCALES)
            else -> Decision(false, Source.DEFAULT)
        }
    }

    /** The next state of the EN / עב button: Auto → English → Hebrew → Auto. */
    fun next(mode: Mode) = when (mode) {
        Mode.AUTO -> Mode.ENGLISH
        Mode.ENGLISH -> Mode.HEBREW
        Mode.HEBREW -> Mode.AUTO
    }

    fun parse(s: String?): Mode = Mode.values().firstOrNull { it.name == s } ?: Mode.AUTO

    /** A subtype's language: `languageTag` (API 24+), else the old `locale` string ("iw_IL"). */
    fun tagOf(s: InputMethodSubtype?): String? =
        s?.let { st -> st.languageTag.ifEmpty { null } ?: @Suppress("DEPRECATION") st.locale.ifEmpty { null } }

    private fun hints(info: EditorInfo?): List<String> {
        val l = info?.hintLocales ?: return emptyList()
        return (0 until l.size()).map { l[it].toLanguageTag() }
    }

    /** The voice keyboard: its own subtype, the keyboard it was opened from, the field's hint. */
    fun forKeyboard(ctx: Context, own: InputMethodSubtype?, info: EditorInfo?): Decision {
        val imm = ctx.getSystemService(InputMethodManager::class.java)
        val last = runCatching { tagOf(imm?.lastInputMethodSubtype) }.getOrNull()
        return decide(Prefs.inputLanguage(ctx), tagOf(own), last, hints(info)).also {
            Log.i(TAG, "keyboard take: ${if (it.hebrew) "he" else "en"} from ${it.source} (own=${tagOf(own)}, last=$last, hints=${hints(info)})")
        }
    }

    /**
     * No previous keyboard (floating mic, Try it, Notes): the system keyboard's current subtype.
     * When this IME is the current one, its own subtype counts as in [forKeyboard].
     */
    fun forApp(ctx: Context): Decision {
        val imm = ctx.getSystemService(InputMethodManager::class.java)
        val current = runCatching { tagOf(imm?.currentInputMethodSubtype) }.getOrNull()
        val ours = runCatching {
            android.provider.Settings.Secure.getString(ctx.contentResolver, android.provider.Settings.Secure.DEFAULT_INPUT_METHOD)
                ?.startsWith(ctx.packageName + "/") == true
        }.getOrDefault(false)
        return decide(Prefs.inputLanguage(ctx), if (ours) current else null, if (ours) null else current, emptyList()).also {
            Log.i(TAG, "app take: ${if (it.hebrew) "he" else "en"} from ${it.source} (current=$current, ours=$ours, sdk=${Build.VERSION.SDK_INT})")
        }
    }

    /**
     * The model for a take: the Hebrew model when [d] says Hebrew and it is downloaded, else null
     * (the selected dictation model). [missing] is set when Hebrew was wanted but isn't on the phone.
     */
    fun model(ctx: Context, d: Decision): Pair<Catalogue.Model?, Boolean> {
        if (!d.hebrew) return null to false
        val he = runCatching { Catalogue.forLanguage(ctx, "he") }.getOrNull() ?: return null to true
        return if (ModelStore.isReady(ctx, model = he)) he to false else null to true
    }
}
