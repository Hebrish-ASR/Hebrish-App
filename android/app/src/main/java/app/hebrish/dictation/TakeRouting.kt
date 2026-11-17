package app.hebrish.dictation

/**
 * Where the voice keyboard puts a take's text while it is being recorded (I-4 Live draft, B-13
 * Shakshuka streaming; android/docs/maintaining.md, "Shakshuka streaming"). Pure, so it is unit-tested
 * (TakeRoutingTest).
 *
 * Since 2026-11-17 (Daniel: Android follows the setting, as the desktop does) a streaming model
 * (Shakshuka) types words during the take only with Type as you go on; before that it always did.
 */
enum class TakeRouting {
    /** Nothing goes in until Stop; the whole take goes in then. */
    AT_STOP,
    /** Each piece goes in as soon as it is decoded (Type as you go; Shakshuka: as words are released). */
    TYPED,
    /** Live draft (I-4): the open phrase shown as composing text, each phrase committed at its pause. */
    PHRASE_DRAFT,
    /** Shakshuka with Live draft and Type as you go off: the streamed words so far as composing text, committed at Stop. */
    STREAM_DRAFT;

    /** The decoder hands pieces over as they are decoded ([app.hebrish.core.TakeDecoder] `onText`). */
    val pieces: Boolean get() = this == TYPED || this == PHRASE_DRAFT

    companion object {
        /**
         * [hebrew]: the take goes to the Hebrew model (no draft: LiveDraft re-decodes with the main
         * model). [streams]: the selected dictation model streams (Shakshuka) and the take is not Hebrew.
         */
        fun keyboard(hebrew: Boolean, streams: Boolean, typeAsYouGo: Boolean, liveDraft: Boolean): TakeRouting = when {
            liveDraft && !hebrew && !streams -> PHRASE_DRAFT
            typeAsYouGo -> TYPED
            liveDraft && streams -> STREAM_DRAFT
            else -> AT_STOP
        }
    }
}
