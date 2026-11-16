package app.hebrish.dictation

import app.hebrish.core.*
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.os.SystemClock
import android.util.Log

/**
 * Keeps a model download the user started alive with the screen off or the app left (2026-11-16,
 * "downloads keep timing out" on a Pixel): a foreground service of type `dataSync` with an ongoing,
 * low-importance progress notification (tap opens Models; Cancel stops the download), plus a
 * partial wake lock and a Wi-Fi lock held only while it runs. The download itself is still
 * [ModelDownload]'s thread; this only holds the process up. Driven by [ModelDownload.keepAlive]
 * ([install]), so `core` and Hebrish Keyboard are unaffected. Background updates (B-107, a
 * JobScheduler job) never start it: a job may not start a foreground service.
 * If notifications aren't allowed the service still runs (the notification is just not shown).
 * android/docs/maintaining.md, "Download robustness".
 */
class DownloadService : Service() {
    companion object {
        private const val TAG = "HebrishDownload"
        private const val CHANNEL = "downloads"
        private const val ID = 4110
        private const val ACTION_CANCEL = "app.hebrish.dictation.download.CANCEL"
        /** Wake lock ceiling: a safety net if the service is somehow never stopped. */
        private const val WAKE_MAX_MS = 6 * 60 * 60 * 1000L

        private var instance: DownloadService? = null

        /** Sets [ModelDownload.keepAlive]. Idempotent; call before any user-started download. */
        fun install() {
            ModelDownload.keepAlive = { ctx, alive -> sync(ctx, alive) }
        }

        /** Main thread. Starts, refreshes or stops the service to match [alive]. */
        private fun sync(ctx: Context, alive: Boolean) {
            val live = instance
            when {
                alive && live != null -> live.show(false)
                // Only for a running user download; a handover alone never starts it (the app may be in the background).
                alive && ModelDownload.status is ModelDownload.Status.Running ->
                    runCatching { ctx.startForegroundService(Intent(ctx, DownloadService::class.java)) }
                        .onFailure { Log.w(TAG, "couldn't start the download service; the download runs without it", it) }
                !alive && live != null -> live.stopSelf()
            }
        }
    }

    private var wake: PowerManager.WakeLock? = null
    private var wifi: WifiManager.WifiLock? = null
    private var lastShown = 0L

    override fun onCreate() {
        super.onCreate()
        instance = this
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // startForeground first, whatever happens next: startForegroundService requires it within seconds.
        val n = notification()
        if (Build.VERSION.SDK_INT >= 29) startForeground(ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        else startForeground(ID, n)
        if (intent?.action == ACTION_CANCEL) ModelDownload.cancel()
        val s = ModelDownload.status
        if (s !is ModelDownload.Status.Running || ModelDownload.moving || ModelDownload.background) {
            stopSelf()
            return START_NOT_STICKY
        }
        lock()
        return START_NOT_STICKY
    }

    /**
     * Android 15+: a dataSync service gets 6 h in 24 h; then this is called and it must stop at once.
     * The download thread carries on while the app is in front; the `.part` files resume otherwise.
     */
    override fun onTimeout(startId: Int, fgsType: Int) {
        Log.w(TAG, "dataSync time limit reached; stopping the foreground service")
        stopSelf()
    }

    override fun onDestroy() {
        instance = null
        unlock()
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }

    private fun lock() {
        if (wake == null) runCatching {
            wake = getSystemService(PowerManager::class.java)
                .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "Hebrish:modelDownload")
                .apply { setReferenceCounted(false); acquire(WAKE_MAX_MS) }
        }.onFailure { Log.w(TAG, "no wake lock", it) }
        if (wifi == null) runCatching {
            // HIGH_PERF keeps Wi-Fi out of power save with the screen off; LOW_LATENCY only works with
            // the screen on. Deprecated on recent Android, where it may do nothing: harmless then.
            @Suppress("DEPRECATION")
            wifi = getSystemService(WifiManager::class.java)
                .createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "Hebrish:modelDownload")
                .apply { setReferenceCounted(false); acquire() }
        }.onFailure { Log.w(TAG, "no Wi-Fi lock", it) }
    }

    private fun unlock() {
        runCatching { wake?.takeIf { it.isHeld }?.release() }
        runCatching { wifi?.takeIf { it.isHeld }?.release() }
        wake = null
        wifi = null
    }

    /** Redraws the notification, at most once a second unless the state changed ([force]). */
    private fun show(force: Boolean) {
        val now = SystemClock.elapsedRealtime()
        val waiting = (ModelDownload.status as? ModelDownload.Status.Running)?.waiting != null
        if (!force && !waiting && now - lastShown < 1000) return
        lastShown = now
        runCatching { getSystemService(NotificationManager::class.java).notify(ID, notification()) }
    }

    private fun notification(): Notification {
        val nm = getSystemService(NotificationManager::class.java)
        if (nm.getNotificationChannel(CHANNEL) == null)
            nm.createNotificationChannel(NotificationChannel(CHANNEL, getString(R.string.download_channel), NotificationManager.IMPORTANCE_LOW))
        val flags = PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        val open = PendingIntent.getActivity(this, 0, Intent(this, ModelsActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), flags)
        val cancel = PendingIntent.getService(this, 1, Intent(this, DownloadService::class.java).setAction(ACTION_CANCEL), flags)
        val s = ModelDownload.status as? ModelDownload.Status.Running
        val t = ModelDownload.target
        val name = listOfNotNull(t?.first?.name, t?.second?.label?.takeIf { it.isNotEmpty() }).joinToString(" ")
        val b = Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle(getString(R.string.download_notif_title, name))
            .setContentIntent(open)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setCategory(Notification.CATEGORY_PROGRESS)
            .addAction(Notification.Action.Builder(null, getString(R.string.tm_cancel), cancel).build())
        if (s != null) {
            b.setContentText(downloadWaitLine(this, s.waiting)
                ?: getString(R.string.download_notif_progress, s.done / 1_000_000, s.total / 1_000_000))
            if (s.total > 0) b.setProgress(1000, (s.done * 1000 / s.total).toInt(), false) else b.setProgress(0, 0, true)
        }
        return b.build()
    }
}

/** "Connection lost: retrying in 8 s…" / "Waiting for a connection…" for [w], or null when bytes are flowing. */
fun downloadWaitLine(ctx: Context, w: DownloadRetry.Wait?): String? = when (w) {
    null -> null
    is DownloadRetry.Wait.Offline -> ctx.getString(R.string.download_waiting_network)
    is DownloadRetry.Wait.Retrying -> ctx.getString(R.string.download_retrying, (w.delayMs / 1000).toInt())
}
