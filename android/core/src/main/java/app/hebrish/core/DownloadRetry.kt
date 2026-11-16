package app.hebrish.core

import java.io.IOException

/**
 * Retry rules for [ModelStore.downloadFiles] (2026-11-16): a dropped connection, a timeout or a
 * server hiccup no longer fails the download. The `.part` file stays, the loop backs off and
 * resumes the same file with a Range request; with no network at all it waits for one. It gives up
 * only after [Policy.noProgressMs] without a single new byte (any progress resets it), or after
 * [Policy.offlineMs] in one stretch without a network. Pure Kotlin, so the decisions are unit-tested
 * on the JVM (DownloadRetryTest). android/docs/maintaining.md, "Download robustness".
 */
object DownloadRetry {
    /** An HTTP status other than 200/206 (404 is [ModelStore.NotPublished] for manifests). */
    class HttpError(val code: Int, file: String) : IOException("HTTP $code for $file")
    /** The full file arrived and its SHA-256 is wrong: retrying the same bytes won't help. */
    class ChecksumMismatch(file: String) : IOException("Checksum mismatch for $file; deleted, try again")
    /** Not enough free space for what is left to download. */
    class NoSpace(message: String) : IOException(message)
    /** Writing or renaming a local file failed (disk full, folder gone): not the network's fault. */
    class LocalFileError(message: String, cause: Throwable? = null) : IOException(message, cause)
    /** The server ended the body before the file was complete, without an error. */
    class ClosedEarly(file: String) : IOException("Connection closed early for $file")
    /** The retry budget ran out; [cause] is the last error. */
    class GaveUp(message: String, cause: Throwable?) : IOException(message, cause)

    /** True for errors worth retrying from the `.part` file. */
    fun transient(e: Throwable): Boolean = when (e) {
        is InterruptedException -> false
        is ModelStore.NotPublished -> false
        is ChecksumMismatch, is NoSpace, is LocalFileError, is GaveUp -> false
        is HttpError -> e.code == 408 || e.code == 429 || e.code in 500..599
        // Everything else from the connection: SocketTimeoutException, UnknownHostException,
        // ConnectException, SocketException ("connection reset"), SSLException, ProtocolException,
        // EOFException, ClosedEarly. Local file errors are wrapped in LocalFileError before they get here.
        is IOException -> true
        else -> false
    }

    /** Wait before retry number [attempt] (0-based): 2, 4, 8, 15, then 30 s. */
    fun backoffMs(attempt: Int): Long = BACKOFF_S[attempt.coerceIn(0, BACKOFF_S.size - 1)] * 1000L
    private val BACKOFF_S = longArrayOf(2, 4, 8, 15, 30)

    data class Policy(
        /** Give up after this long without a new byte while there is a network. */
        val noProgressMs: Long = 10 * 60 * 1000L,
        /** Give up after this long in one stretch without a network. */
        val offlineMs: Long = 30 * 60 * 1000L,
        /** How often to look for a network while waiting for one. */
        val offlinePollMs: Long = 2000L,
    )

    /** What the download is waiting for, for the progress line; null = bytes are flowing. */
    sealed class Wait {
        /** Retry [attempt] (1-based) after [reason], due in [delayMs]. */
        data class Retrying(val attempt: Int, val reason: String, val delayMs: Long) : Wait()
        /** No network: waiting for one. */
        object Offline : Wait() { override fun toString() = "Offline" }
    }

    /**
     * Hooks for one download. Defaults: assume a network, report nothing, real time and sleep.
     * [online] null = can't tell (e.g. no ACCESS_NETWORK_STATE): treated as online, so only backoff.
     */
    class Hooks(
        val online: (() -> Boolean)? = null,
        val onWait: (Wait?) -> Unit = {},
        val policy: Policy = Policy(),
        val clock: () -> Long = { System.nanoTime() / 1_000_000 },
        val sleep: (Long) -> Unit = { Thread.sleep(it) },
    ) {
        fun isOnline() = online?.let { runCatching(it).getOrDefault(true) } ?: true

        /** Sleeps [ms] in short steps, throwing [InterruptedException] as soon as [cancelled] says so. */
        fun pause(ms: Long, cancelled: () -> Boolean) {
            var left = ms
            while (left > 0) {
                if (cancelled()) throw InterruptedException("cancelled")
                val step = minOf(left, 250L)
                sleep(step)
                left -= step
            }
            if (cancelled()) throw InterruptedException("cancelled")
        }
    }

    /**
     * The give-up clock for one file. Time without a network does not count against
     * [Policy.noProgressMs]; it has its own limit, [Policy.offlineMs], per stretch.
     */
    class Budget(private val policy: Policy, now: Long) {
        private var lastProgress = now
        private var offlineSince = -1L

        fun progress(now: Long) { lastProgress = now }
        /** Without new bytes for too long (online time only). */
        fun exhausted(now: Long) = offlineSince < 0 && now - lastProgress > policy.noProgressMs
        fun offline(now: Long) { if (offlineSince < 0) offlineSince = now }
        /** Back online: the offline stretch is not held against the no-progress budget. */
        fun online(now: Long) {
            if (offlineSince >= 0) lastProgress += now - offlineSince
            offlineSince = -1L
        }
        fun offlineTooLong(now: Long) = offlineSince >= 0 && now - offlineSince > policy.offlineMs
    }
}
