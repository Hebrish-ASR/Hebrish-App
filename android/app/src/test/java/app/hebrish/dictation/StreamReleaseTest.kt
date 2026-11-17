package app.hebrish.dictation

import app.hebrish.core.StreamRelease
import org.junit.Assert.assertEquals
import org.junit.Test

/** The desktop's "phrase" release rule, ported for Shakshuka on Android (B-13). */
class StreamReleaseTest {
    @Test fun holdsAWordStillGrowing() {
        val r = StreamRelease()
        assertEquals("", r.next("Reminder ask Av", last = false, now = 0))
        assertEquals("", r.next("Reminder ask Avi for", last = false, now = 500))
    }

    @Test fun releasesUpToASentenceMarkAtOnce() {
        val r = StreamRelease()
        assertEquals("Hello there.", r.next("Hello there. How a", last = false, now = 0))
        assertEquals("", r.next("Hello there. How are", last = false, now = 300))
    }

    @Test fun clauseMarkNeedsEnoughWords() {
        val r = StreamRelease()
        assertEquals("", r.next("Yes, I think", last = false, now = 0))
        assertEquals("Yes, I think we should go,", r.next("Yes, I think we should go, but", last = false, now = 100))
    }

    @Test fun aPauseReleasesEverything() {
        val r = StreamRelease()
        assertEquals("", r.next("send it to Avi", last = false, now = 0))
        assertEquals("send it to Avi", r.next("send it to Avi", last = false, now = 900))
        // the next release starts with its space; nothing is released twice
        assertEquals(" tomorrow.", r.next("send it to Avi tomorrow. And", last = false, now = 1000))
    }

    @Test fun longRunReleasesWholeWordsKeepingTwoBack() {
        val r = StreamRelease()
        assertEquals("", r.next("one two three four", last = false, now = 0))
        assertEquals("one two three", r.next("one two three four fiv", last = false, now = 2600))
    }

    @Test fun stopReleasesTheRest() {
        val r = StreamRelease()
        assertEquals("", r.next("one two", last = false, now = 0))
        assertEquals("one two three", r.next("one two three", last = true, now = 100))
        assertEquals("one two three", r.sent)
    }

    @Test fun aRevisedResultReleasesNothingMore() {
        val r = StreamRelease()
        assertEquals("Hello.", r.next("Hello. W", last = false, now = 0))
        assertEquals("", r.next("Hullo. World.", last = true, now = 100))
    }
}
