package app.hebrish.dictation

import app.hebrish.dictation.TakeRouting.AT_STOP
import app.hebrish.dictation.TakeRouting.PHRASE_DRAFT
import app.hebrish.dictation.TakeRouting.STREAM_DRAFT
import app.hebrish.dictation.TakeRouting.TYPED
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The voice keyboard's routing (TakeRouting.keyboard): Shakshuka follows Type as you go since 2026-11-17. */
class TakeRoutingTest {
    private fun r(hebrew: Boolean = false, streams: Boolean = false, typeAsYouGo: Boolean = false, liveDraft: Boolean = false) =
        TakeRouting.keyboard(hebrew, streams, typeAsYouGo, liveDraft)

    // Shakshuka (streams)
    @Test fun streamingWithEverythingOffWaitsForStop() = assertEquals(AT_STOP, r(streams = true))
    @Test fun streamingTypesWithTypeAsYouGo() = assertEquals(TYPED, r(streams = true, typeAsYouGo = true))
    @Test fun streamingDraftsWithLiveDraftOnly() = assertEquals(STREAM_DRAFT, r(streams = true, liveDraft = true))
    @Test fun streamingTypeAsYouGoBeatsTheDraft() = assertEquals(TYPED, r(streams = true, typeAsYouGo = true, liveDraft = true))

    // Offline models (Sabich), unchanged
    @Test fun offlineAtStop() = assertEquals(AT_STOP, r())
    @Test fun offlineTyped() = assertEquals(TYPED, r(typeAsYouGo = true))
    @Test fun offlinePhraseDraft() = assertEquals(PHRASE_DRAFT, r(liveDraft = true))
    @Test fun offlinePhraseDraftWithTypeAsYouGo() = assertEquals(PHRASE_DRAFT, r(typeAsYouGo = true, liveDraft = true))

    // Hebrew takes: no draft
    @Test fun hebrewIgnoresLiveDraft() = assertEquals(AT_STOP, r(hebrew = true, liveDraft = true))
    @Test fun hebrewTyped() = assertEquals(TYPED, r(hebrew = true, typeAsYouGo = true, liveDraft = true))

    @Test fun piecesOnlyWhenTextGoesInDuringTheTake() {
        assertTrue(TYPED.pieces)
        assertTrue(PHRASE_DRAFT.pieces)
        assertFalse(STREAM_DRAFT.pieces)
        assertFalse(AT_STOP.pieces)
    }
}
