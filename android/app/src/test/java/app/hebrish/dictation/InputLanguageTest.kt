package app.hebrish.dictation

import app.hebrish.dictation.InputLanguage.Decision
import app.hebrish.dictation.InputLanguage.Mode
import app.hebrish.dictation.InputLanguage.Source
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The per-take language decision (2026-11-16; docs/maintaining.md, "Hebrew model switching"). */
class InputLanguageTest {
    @Test fun hebrewTags() {
        for (t in listOf("he", "he-IL", "he_IL", "iw", "iw_IL", "IW", " he ")) assertTrue(t, InputLanguage.isHebrew(t))
        for (t in listOf(null, "", "en", "en-US", "hel", "hebrew", "iwx", "ar", "und")) assertFalse("$t", InputLanguage.isHebrew(t))
    }

    @Test fun toggleWinsOverEverything() {
        assertEquals(Decision(false, Source.TOGGLE), InputLanguage.decide(Mode.ENGLISH, "he", "he-IL", listOf("he")))
        assertEquals(Decision(true, Source.TOGGLE), InputLanguage.decide(Mode.HEBREW, "en-US", "en-US", listOf("en")))
    }

    @Test fun autoFollowsPreviousKeyboard() {
        assertEquals(Decision(true, Source.KEYBOARD_SUBTYPE), InputLanguage.decide(Mode.AUTO, "en-US", "he", emptyList()))
        assertEquals(Decision(true, Source.KEYBOARD_SUBTYPE), InputLanguage.decide(Mode.AUTO, null, "iw_IL", emptyList()))
        assertEquals(Decision(false, Source.KEYBOARD_SUBTYPE), InputLanguage.decide(Mode.AUTO, "en-US", "en-GB", listOf("he")))
    }

    @Test fun ownHebrewSubtypeCounts() {
        // Picked "Hebrew (voice)": Hebrew even when the previous keyboard is English.
        assertEquals(Decision(true, Source.OWN_SUBTYPE), InputLanguage.decide(Mode.AUTO, "he", "en-US", emptyList()))
    }

    @Test fun ownEnglishSubtypeSaysNothing() {
        // The English subtype is what a keyboard's mic key opens: fall through to the keyboard.
        assertEquals(Decision(true, Source.KEYBOARD_SUBTYPE), InputLanguage.decide(Mode.AUTO, "en-US", "he-IL", emptyList()))
    }

    @Test fun hintLocalesThenDefault() {
        assertEquals(Decision(true, Source.HINT_LOCALES), InputLanguage.decide(Mode.AUTO, "en-US", null, listOf("he-IL", "en-US")))
        assertEquals(Decision(true, Source.HINT_LOCALES), InputLanguage.decide(Mode.AUTO, null, "", listOf("und", "he")))
        assertEquals(Decision(false, Source.HINT_LOCALES), InputLanguage.decide(Mode.AUTO, null, "und", listOf("en-US")))
        assertEquals(Decision(false, Source.DEFAULT), InputLanguage.decide(Mode.AUTO, null, null, emptyList()))
    }

    @Test fun buttonCycles() {
        assertEquals(Mode.ENGLISH, InputLanguage.next(Mode.AUTO))
        assertEquals(Mode.HEBREW, InputLanguage.next(Mode.ENGLISH))
        assertEquals(Mode.AUTO, InputLanguage.next(Mode.HEBREW))
        assertEquals(Mode.ENGLISH, InputLanguage.parse(null))
        assertEquals(Mode.ENGLISH, InputLanguage.parse("nonsense"))
        assertEquals(Mode.HEBREW, InputLanguage.parse("HEBREW"))
    }
}
