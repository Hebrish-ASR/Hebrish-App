package app.hebrish.dictation

import app.hebrish.core.TakeDecoder
import org.junit.Assert.assertEquals
import org.junit.Test

/** B-105 (TakeDecoder.withoutFinalStop) and the I-4 draft text (LiveDraft.draftText). */
class FinalStopTest {
    private fun drop(s: String) = TakeDecoder.withoutFinalStop(s)

    @Test fun dropsTheFinalFullStop() = assertEquals("Blue widgets", drop("Blue widgets."))
    @Test fun keepsFullStopsInside() = assertEquals("It works. Ship it", drop("It works. Ship it."))
    @Test fun keepsAnEllipsis() = assertEquals("Well...", drop("Well..."))
    @Test fun keepsTwoDots() = assertEquals("Hm..", drop("Hm.."))
    @Test fun keepsAQuestionMark() = assertEquals("Is it there?", drop("Is it there?"))
    @Test fun keepsAnExclamationMark() = assertEquals("Done!", drop("Done!"))
    @Test fun trailingSpaceBeforeTheStop() = assertEquals("Shelf 4", drop("Shelf 4. "))
    @Test fun aLoneHeldStopBecomesNothing() = assertEquals("", drop("."))
    @Test fun heldStopLeadStays() = assertEquals(". Next words", drop(". Next words."))
    @Test fun decimalInsideStays() = assertEquals("Version 3.5", drop("Version 3.5."))
    @Test fun nothingToDrop() = assertEquals("No stop", drop("No stop"))
    @Test fun empty() = assertEquals("", drop(""))
    @Test fun allCapsUnaffected() = assertEquals("SEARCH TERM", drop("SEARCH TERM."))

    @Test fun draftDropsFinalPunctuation() {
        assertEquals("I think we should go", LiveDraft.draftText("I think we should go."))
        assertEquals("Are you there", LiveDraft.draftText("Are you there?"))
        assertEquals("Stop", LiveDraft.draftText("Stop! "))
        assertEquals("One. Two", LiveDraft.draftText("One. Two."))
        assertEquals("", LiveDraft.draftText(""))
    }
}
