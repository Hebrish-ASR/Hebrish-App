package app.hebrish.dictation

/** The kinds of microphone a user ranks. A device's kind comes from [Mic.kind]. */
enum class MicKind { USB, BLUETOOTH, WIRED, PHONE }

/**
 * The standing microphone preference (1.018): every [MicKind], best first, saved as
 * "USB,BLUETOOTH,WIRED,PHONE" in Prefs.micOrder. No Android types here, so it is unit-tested.
 */
object MicOrder {
    /** A mic someone plugged in is the deliberate choice, so USB leads. */
    val DEFAULT = listOf(MicKind.USB, MicKind.BLUETOOTH, MicKind.WIRED, MicKind.PHONE)

    /** How long a one-off mic choice lasts with no take: see [Mic.choose]. */
    const val SESSION_MS = 30 * 60 * 1000L

    /** Reads a saved order. Unknown names are dropped and missing kinds join at the end, in [DEFAULT] order. */
    fun parse(saved: String?): List<MicKind> {
        val named = saved.orEmpty().split(',').mapNotNull { n -> MicKind.values().firstOrNull { it.name == n.trim() } }.distinct()
        return named + DEFAULT.filter { it !in named }
    }

    fun encode(order: List<MicKind>) = order.joinToString(",") { it.name }

    /** [order] with [kind] moved to the front: an older saved mic becomes the top of the list. */
    fun promote(order: List<MicKind>, kind: MicKind) = listOf(kind) + order.filter { it != kind }

    /** [items] sorted by [order] (stable, so same-kind devices keep Android's order); no kind goes last. */
    fun <T> rank(items: List<T>, order: List<MicKind>, kind: (T) -> MicKind?): List<T> =
        items.sortedBy { i -> kind(i)?.let { order.indexOf(it) } ?: order.size }

    /**
     * What a source chip's tap moves to: the item after the current one, going round. With none
     * current (the mic in use was unplugged) it is the first. Null only for an empty list.
     */
    fun <T> next(items: List<T>, isCurrent: (T) -> Boolean): T? =
        if (items.isEmpty()) null else items[(items.indexOfFirst(isCurrent) + 1) % items.size]

    /** Whether a one-off choice last used at [usedAt] still holds at [now]. */
    fun sessionLive(usedAt: Long, now: Long) = now - usedAt in 0 until SESSION_MS
}
