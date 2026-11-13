package app.hebrish.dictation

import app.hebrish.core.*
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.util.Log

/**
 * B-107 (Daniel, 2026-11-13, R-2026-11-13-4): new weights for the models on the phone arrive
 * without opening the app. The periodic job [UpdateJobs.MODELS] (every ~6 h, Wi-Fi only unless
 * the user says otherwise) runs [run]: the same [ModelDownload.check] and [ModelDownload.update]
 * as the Models screen (pinned revision, per-file SHA-256, free-space check, pruneOld), for
 * installed models only, one after another. The download may run during a take; the switch-over
 * waits for it ([ModelDownload.holdSwap] = [TakeGuard.busy]). Afterwards a quiet notification
 * says "Sabich updated to v3.1". Every build, Play included (weights are data, not code).
 * docs/maintaining.md, "Model updates in the background (B-107)".
 */
object ModelUpdates {
    private const val TAG = "HebrishUpdate"

    /** Blocking; call on a worker thread. True asks the job to retry soon (something was in the way). */
    fun run(ctx: Context): Boolean {
        val app = ctx.applicationContext
        if (!Prefs.modelAutoUpdate(app)) return false
        if (Prefs.modelWifiOnly(app) && metered(app)) return false
        // A download the user started (or a folder move) is running: leave it alone, try later.
        if (ModelDownload.status is ModelDownload.Status.Running || ModelDownload.moving) return true
        ModelDownload.holdSwap = { TakeGuard.busy() }

        onMain { ModelDownload.check(app, force = true) }
        if (!waitWhile(CHECK_TIMEOUT_MS) { ModelDownload.checking }) return true
        ModelDownload.checkError?.let { Log.w(TAG, "model check failed: $it"); return true }

        val installed = ModelStore.readyModels(app)
        val sel = Catalogue.selected(app)
        // The selected model first: it is the one dictation uses.
        val order = installed.sortedBy { if (it.id == sel.id) 0 else 1 }
        var retry = false
        for (m in order) {
            val next = ModelDownload.updateAvailable(app, m) ?: continue
            if (ModelDownload.status is ModelDownload.Status.Running) { retry = true; break }
            Log.i(TAG, "background update of ${m.id} to ${next.version}")
            onMain { ModelDownload.update(app, m) }
            // update() sets Running before it returns (on the main thread, done by now); wait for the download and switch-over.
            waitWhile(Long.MAX_VALUE) { ModelDownload.status is ModelDownload.Status.Running }
            val now = ModelStore.installed(app, m)
            if (now != null && now.sameWeights(next)) {
                val label = next.label.ifEmpty { next.version }
                UpdateNotices.post(app, UpdateNotices.MODEL_UPDATED * 1000 + Math.floorMod(m.id.hashCode(), 1000),
                    app.getString(R.string.modelupdate_done, m.name, label), null, Intent(app, ModelsActivity::class.java))
            } else {
                Log.w(TAG, "background update of ${m.id} did not finish: ${ModelDownload.status}")
                // The Models screen would otherwise show a failure the user didn't start; the .part files resume next time.
                onMain { ModelDownload.clearFailure() }
                retry = true
                break
            }
        }
        return retry
    }

    private fun metered(ctx: Context): Boolean =
        runCatching { ctx.getSystemService(ConnectivityManager::class.java).isActiveNetworkMetered }.getOrDefault(true)

    private fun onMain(block: () -> Unit) {
        val done = java.util.concurrent.CountDownLatch(1)
        android.os.Handler(android.os.Looper.getMainLooper()).post { try { block() } finally { done.countDown() } }
        done.await(10, java.util.concurrent.TimeUnit.SECONDS)
    }

    /** Sleeps while [cond] holds, up to [ms]; false on timeout. */
    private fun waitWhile(ms: Long, cond: () -> Boolean): Boolean {
        val start = System.currentTimeMillis()
        while (cond()) {
            if (System.currentTimeMillis() - start > ms) return false
            Thread.sleep(500)
        }
        return true
    }

    private const val CHECK_TIMEOUT_MS = 2 * 60 * 1000L
}
