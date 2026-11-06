package app.hebrish.dictation

import org.junit.Assert.assertEquals
import org.junit.Test

class SentencesTest {
    private fun afterDelete(s: String) = s.dropLast(lastSentenceLength(s))

    @Test fun removesTheLastSentenceAndItsSpace() = assertEquals("One.", afterDelete("One. Two three."))
    @Test fun unfinishedSentence() = assertEquals("One.", afterDelete("One. Two three"))
    @Test fun trailingSpace() = assertEquals("One.", afterDelete("One. Two three. "))
    @Test fun questionMark() = assertEquals("Really?", afterDelete("Really? Yes."))
    @Test fun decimalIsNotABoundary() = assertEquals("One.", afterDelete("One. It costs 3.5 shekels."))
    @Test fun hebrew() = assertEquals("\u05E9\u05DC\u05D5\u05DD.", afterDelete("\u05E9\u05DC\u05D5\u05DD. \u05DE\u05D4 \u05E9\u05DC\u05D5\u05DE\u05DA?"))
    @Test fun keepsAParagraphBreak() = assertEquals("One.\n\n", afterDelete("One.\n\nTwo three."))
    @Test fun afterABreakTheParagraphAboveGoes() = assertEquals("Zero.", afterDelete("Zero. One.\n\n"))
    @Test fun onlySentence() = assertEquals("", afterDelete("Just this"))
    @Test fun blank() = assertEquals(0, lastSentenceLength(""))
    @Test fun onlySpaces() = assertEquals("", afterDelete("  "))
}
