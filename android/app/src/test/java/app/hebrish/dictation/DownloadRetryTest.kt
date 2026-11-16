package app.hebrish.dictation

import app.hebrish.core.DownloadRetry
import app.hebrish.core.ModelStore
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.io.IOException
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.security.MessageDigest
import java.util.concurrent.ConcurrentLinkedQueue
import kotlin.concurrent.thread

/** Download robustness (2026-11-16): the retry decisions, and downloadFiles against a server that drops the connection. */
class DownloadRetryTest {
    @get:Rule val tmp = TemporaryFolder()

    // --- Which errors are retried ---

    @Test fun transientErrors() {
        assertTrue(DownloadRetry.transient(SocketTimeoutException("read timed out")))
        assertTrue(DownloadRetry.transient(UnknownHostException("cdn.hebrish.app")))
        assertTrue(DownloadRetry.transient(java.net.SocketException("Connection reset")))
        assertTrue(DownloadRetry.transient(java.net.ConnectException("refused")))
        assertTrue(DownloadRetry.transient(javax.net.ssl.SSLException("handshake")))
        assertTrue(DownloadRetry.transient(DownloadRetry.ClosedEarly("a")))
        for (c in listOf(408, 429, 500, 502, 503, 504)) assertTrue("$c", DownloadRetry.transient(DownloadRetry.HttpError(c, "a")))
    }

    @Test fun permanentErrors() {
        for (c in listOf(400, 401, 403, 404, 410, 416)) assertFalse("$c", DownloadRetry.transient(DownloadRetry.HttpError(c, "a")))
        assertFalse(DownloadRetry.transient(ModelStore.NotPublished("u")))
        assertFalse(DownloadRetry.transient(DownloadRetry.ChecksumMismatch("a")))
        assertFalse(DownloadRetry.transient(DownloadRetry.NoSpace("full")))
        assertFalse(DownloadRetry.transient(DownloadRetry.LocalFileError("disk")))
        assertFalse(DownloadRetry.transient(DownloadRetry.GaveUp("x", null)))
        assertFalse(DownloadRetry.transient(InterruptedException("cancelled")))
        assertFalse(DownloadRetry.transient(IllegalStateException()))
    }

    @Test fun backoffSchedule() {
        assertEquals(listOf(2000L, 4000L, 8000L, 15000L, 30000L, 30000L, 30000L), (0..6).map { DownloadRetry.backoffMs(it) })
        assertEquals(2000L, DownloadRetry.backoffMs(-1))
    }

    // --- The give-up budget ---

    private val policy = DownloadRetry.Policy(noProgressMs = 600_000, offlineMs = 1_800_000)

    @Test fun budgetRunsOutWithoutProgress() {
        val b = DownloadRetry.Budget(policy, 0)
        assertFalse(b.exhausted(600_000))
        assertTrue(b.exhausted(600_001))
    }

    @Test fun progressResetsBudget() {
        val b = DownloadRetry.Budget(policy, 0)
        b.progress(500_000)
        assertFalse(b.exhausted(1_000_000))
        assertTrue(b.exhausted(1_100_001))
    }

    @Test fun offlineTimeDoesNotCountAsNoProgress() {
        val b = DownloadRetry.Budget(policy, 0)
        b.offline(100_000)
        assertFalse(b.exhausted(1_000_000))          // offline: the no-progress clock is paused
        assertFalse(b.offlineTooLong(1_000_000))
        b.online(1_000_000)                          // 900 s offline are forgiven
        assertFalse(b.exhausted(1_400_000))
        assertTrue(b.exhausted(1_500_001))
    }

    @Test fun offlineHasItsOwnLimit() {
        val b = DownloadRetry.Budget(policy, 0)
        b.offline(0)
        b.offline(1_000_000)                          // a second call keeps the stretch's start
        assertFalse(b.offlineTooLong(1_800_000))
        assertTrue(b.offlineTooLong(1_800_001))
    }

    // --- downloadFiles against a local server ---

    /** What the fake server does with one request: given the Range start, write a raw response. */
    private fun interface Reply { fun write(s: Socket, from: Long) }

    private val replies = ConcurrentLinkedQueue<Reply>()
    private val ranges = ConcurrentLinkedQueue<Long>()
    private val server = ServerSocket(0)
    private val body = ByteArray(300_000) { (it * 31 % 251).toByte() }

    init {
        thread(isDaemon = true) {
            while (!server.isClosed) {
                val s = runCatching { server.accept() }.getOrNull() ?: break
                s.use {
                    val head = generateSequence { readLine(s) }.takeWhile { it.isNotEmpty() }.toList()
                    val from = head.firstOrNull { it.startsWith("Range:", true) }
                        ?.substringAfter("bytes=")?.substringBefore('-')?.toLong() ?: 0L
                    ranges.add(from)
                    (replies.poll() ?: full).write(s, from)
                }
            }
        }
    }

    @After fun close() = server.close()

    private fun readLine(s: Socket): String {
        val sb = StringBuilder()
        while (true) {
            val c = s.getInputStream().read()
            if (c < 0 || c == '\n'.code) break
            if (c != '\r'.code) sb.append(c.toChar())
        }
        return sb.toString()
    }

    private fun send(s: Socket, from: Long, upTo: Int) {
        val out = s.getOutputStream()
        val status = if (from > 0) "206 Partial Content" else "200 OK"
        out.write("HTTP/1.1 $status\r\nContent-Length: ${body.size - from}\r\nConnection: close\r\n\r\n".toByteArray())
        out.write(body, from.toInt(), upTo - from.toInt())
        out.flush()
    }

    private val full = Reply { s, from -> send(s, from, body.size) }
    /** Sends up to [upTo] of the body and then drops the connection (the length promised more). */
    private fun dropAt(upTo: Int) = Reply { s, from -> send(s, from, upTo) }
    private fun status(code: Int) = Reply { s, _ ->
        s.getOutputStream().write("HTTP/1.1 $code X\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".toByteArray())
    }

    private fun sha(b: ByteArray) = MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }
    private val file = ModelStore.ModelFile("model.onnx", body.size.toLong(), sha(body))
    private val url = "http://127.0.0.1:${server.localPort}/model.onnx"

    /** Fake time: sleeping advances it, nothing really waits. */
    private class FakeTime {
        var now = 0L
        val slept = mutableListOf<Long>()
    }

    private fun hooks(t: FakeTime, online: () -> Boolean = { true }, waits: MutableList<DownloadRetry.Wait?> = mutableListOf()) =
        DownloadRetry.Hooks(online = online, onWait = { waits.add(it) }, policy = policy,
            clock = { t.now }, sleep = { t.now += it; t.slept.add(it) })

    @Test fun resumesAfterDroppedConnections() {
        replies.addAll(listOf(dropAt(100_000), dropAt(180_000), full))
        val t = FakeTime()
        val waits = mutableListOf<DownloadRetry.Wait?>()
        var last = 0L
        ModelStore.downloadFiles(tmp.root, listOf(file), { url }, { false }, hooks(t, waits = waits)) { last = it }
        assertArrayEquals(body, File(tmp.root, "model.onnx").readBytes())
        assertFalse(File(tmp.root, "model.onnx.part").exists())
        assertEquals(listOf(0L, 100_000L, 180_000L), ranges.toList())   // each retry resumed from the .part
        assertEquals(body.size.toLong(), last)
        assertTrue(waits.first() is DownloadRetry.Wait.Retrying)
        assertEquals(null, waits.last())                                   // "retrying" cleared once bytes flowed
    }

    @Test fun serverErrorsAreRetriedWithBackoff() {
        replies.addAll(listOf(status(503), status(503), status(429), full))
        val t = FakeTime()
        ModelStore.downloadFiles(tmp.root, listOf(file), { url }, { false }, hooks(t)) {}
        assertArrayEquals(body, File(tmp.root, "model.onnx").readBytes())
        assertEquals(2000L + 4000L + 8000L, t.slept.sum())
    }

    @Test fun notFoundIsNotRetried() {
        replies.add(status(404))
        try {
            ModelStore.downloadFiles(tmp.root, listOf(file), { url }, { false }, hooks(FakeTime())) {}
            fail()
        } catch (e: DownloadRetry.HttpError) {
            assertEquals(404, e.code)
        }
        assertEquals(1, ranges.size)
    }

    @Test fun checksumMismatchIsNotRetried() {
        val bad = file.copy(sha256 = "0".repeat(64))
        try {
            ModelStore.downloadFiles(tmp.root, listOf(bad), { url }, { false }, hooks(FakeTime())) {}
            fail()
        } catch (e: DownloadRetry.ChecksumMismatch) {}
        assertEquals(1, ranges.size)
        assertFalse(File(tmp.root, "model.onnx.part").exists())
    }

    @Test fun waitsForNetworkWithoutSpendingAttempts() {
        val t = FakeTime()
        var polls = 0
        val waits = mutableListOf<DownloadRetry.Wait?>()
        ModelStore.downloadFiles(tmp.root, listOf(file), { url }, { false }, hooks(t, online = { ++polls > 5 }, waits = waits)) {}
        assertArrayEquals(body, File(tmp.root, "model.onnx").readBytes())
        assertEquals(1, ranges.size)                                      // no request while offline
        assertTrue(waits.first() is DownloadRetry.Wait.Offline)
        assertEquals(null, waits.last())
    }

    @Test fun givesUpAfterTenMinutesWithoutProgress() {
        repeat(200) { replies.add(status(503)) }
        val t = FakeTime()
        try {
            ModelStore.downloadFiles(tmp.root, listOf(file), { url }, { false }, hooks(t)) {}
            fail()
        } catch (e: DownloadRetry.GaveUp) {
            assertTrue(e.cause is DownloadRetry.HttpError)
        }
        assertTrue(t.now in 600_000L..640_000L)
    }

    @Test fun cancelStopsDuringBackoff() {
        replies.add(dropAt(50_000))
        val t = FakeTime()
        var cancel = false
        val h = DownloadRetry.Hooks(policy = policy, clock = { t.now }, sleep = { t.now += it; cancel = true })
        try {
            ModelStore.downloadFiles(tmp.root, listOf(file), { url }, { cancel }, h) {}
            fail()
        } catch (e: InterruptedException) {}
        assertEquals(250L, t.now)                                          // stopped at the first 250 ms step
        assertEquals(50_000L, File(tmp.root, "model.onnx.part").length()) // kept for the next try
    }

    @Test fun defaultHooksStillDownload() {
        // The signature the Hebrish Keyboard and older callers use: no hooks.
        ModelStore.downloadFiles(tmp.root, listOf(file), { url }, { false }) {}
        assertArrayEquals(body, File(tmp.root, "model.onnx").readBytes())
    }

    @Test fun cannotTellIfOnlineCountsAsOnline() {
        assertTrue(DownloadRetry.Hooks(online = { throw SecurityException() }).isOnline())
        assertTrue(DownloadRetry.Hooks().isOnline())
        assertFalse(DownloadRetry.Hooks(online = { false }).isOnline())
    }

    @Test fun ioExceptionClassesAreIOExceptions() {
        // Callers that catch IOException (and show e.message) keep working.
        val all: List<Exception> = listOf(DownloadRetry.HttpError(500, "a"), DownloadRetry.ChecksumMismatch("a"),
            DownloadRetry.NoSpace("a"), DownloadRetry.LocalFileError("a"), DownloadRetry.GaveUp("a", null))
        assertTrue(all.all { it is IOException })
    }
}
