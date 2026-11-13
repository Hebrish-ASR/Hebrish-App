package app.hebrish.dictation

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.util.Log
import java.util.Collections
import java.util.WeakHashMap
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Is anyone dictating right now? Background updates (B-106 app, B-107 models) never install or
 * switch weights while a take is open: the voice keyboard, the floating mic, Transcription Mode, or
 * a dictation box in the app (Try it, Notes). The services' flags live on the main thread, so
 * [busy] reads them there.
 */
object TakeGuard {
    private val main = Handler(Looper.getMainLooper())
    /** DictationPads with a take recording or transcribing; weak, so a pad whose screen died can't stick. */
    private val pads: MutableSet<Any> = Collections.synchronizedSet(Collections.newSetFromMap(WeakHashMap<Any, Boolean>()))

    fun pad(p: Any, open: Boolean) { if (open) pads.add(p) else pads.remove(p) }

    private fun busyHere(): Boolean = VoiceImeService.takeOpen || FloatingMicService.takeOpen ||
        pads.isNotEmpty() || (Recording.tape.active)

    /** Any thread. When the main thread doesn't answer within 5 s, counts as busy. */
    fun busy(): Boolean {
        if (Looper.myLooper() == Looper.getMainLooper()) return busyHere()
        var answer = true
        val done = CountDownLatch(1)
        main.post { answer = runCatching { busyHere() }.getOrDefault(true); done.countDown() }
        return if (done.await(5, TimeUnit.SECONDS)) answer else true
    }
}

/**
 * The two periodic background jobs (JobScheduler; the app has no WorkManager dependency):
 * [APP] checks for a new Hebrish APK (B-106, `fdroid` build only, with "Install unknown apps"
 * allowed and the switch on), [MODELS] for new model weights (B-107, every build, switch on).
 * [sync] schedules or cancels both to match the settings; it is called whenever the app opens,
 * a setting changes, or the app was updated (AppUpdateReceiver), and leaves a job that is already
 * scheduled as it is, so its period isn't restarted.
 */
object UpdateJobs {
    const val APP = 4106
    const val MODELS = 4107
    private const val TAG = "HebrishUpdate"
    private const val HOUR = 60 * 60 * 1000L

    fun sync(ctx: Context) {
        val app = ctx.applicationContext
        runCatching {
            ensure(app, APP, AppUpdates.backgroundOn(app), 12 * HOUR, JobInfo.NETWORK_TYPE_UNMETERED)
            val net = if (Prefs.modelWifiOnly(app)) JobInfo.NETWORK_TYPE_UNMETERED else JobInfo.NETWORK_TYPE_ANY
            ensure(app, MODELS, Prefs.modelAutoUpdate(app), 6 * HOUR, net)
        }.onFailure { Log.w(TAG, "scheduling failed", it) }
    }

    @Suppress("DEPRECATION")
    private fun ensure(ctx: Context, id: Int, on: Boolean, period: Long, network: Int) {
        val js = ctx.getSystemService(JobScheduler::class.java) ?: return
        val pending = js.getPendingJob(id)
        if (!on) {
            if (pending != null) js.cancel(id)
            return
        }
        if (pending != null && pending.networkType == network && pending.intervalMillis == period) return
        val info = JobInfo.Builder(id, ComponentName(ctx, UpdateJob::class.java))
            .setRequiredNetworkType(network)
            .setRequiresBatteryNotLow(true)
            .setPeriodic(period, 2 * HOUR)
            // Survives a restart; needs RECEIVE_BOOT_COMPLETED.
            .setPersisted(true)
            .build()
        js.schedule(info)
    }
}

/** Runs one job on a worker thread; never throws. */
class UpdateJob : JobService() {
    override fun onStartJob(params: JobParameters): Boolean {
        val app = applicationContext
        Thread {
            var again = false
            try {
                again = when (params.jobId) {
                    UpdateJobs.APP -> AppUpdates.run(app, manual = false).kind == AppUpdates.Kind.POSTPONED
                    UpdateJobs.MODELS -> ModelUpdates.run(app)
                    else -> false
                }
            } catch (t: Throwable) {
                Log.w("HebrishUpdate", "job ${params.jobId} failed", t)
            }
            // A postponed run (a take was open) asks for a retry with the system's backoff.
            jobFinished(params, again)
        }.start()
        return true
    }

    /** The system stopped the job (network gone, time up). Downloads resume next time. */
    override fun onStopJob(params: JobParameters): Boolean = true
}

/** The quiet notifications both updaters post: "Hebrish updated to X", "Sabich updated to vN", "Tap to install". */
object UpdateNotices {
    private const val CHANNEL = "updates"
    const val APP_UPDATED = 51
    const val APP_CONFIRM = 52
    const val MODEL_UPDATED = 53

    fun allowed(ctx: Context): Boolean {
        val nm = ctx.getSystemService(NotificationManager::class.java) ?: return false
        return Recording.notificationsAllowed(ctx) && nm.areNotificationsEnabled()
    }

    fun post(ctx: Context, id: Int, title: String, text: String?, tap: Intent?) {
        if (!allowed(ctx)) return
        runCatching {
            val nm = ctx.getSystemService(NotificationManager::class.java)
            if (nm.getNotificationChannel(CHANNEL) == null)
                nm.createNotificationChannel(NotificationChannel(CHANNEL, ctx.getString(R.string.updates_channel), NotificationManager.IMPORTANCE_LOW))
            val open = tap ?: Intent(ctx, MainActivity::class.java)
            val pi = PendingIntent.getActivity(ctx, id, open.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            val n = Notification.Builder(ctx, CHANNEL)
                .setSmallIcon(R.drawable.ic_mic)
                .setContentTitle(title)
                .apply { if (text != null) setContentText(text) }
                .setContentIntent(pi)
                .setAutoCancel(true)
                .build()
            nm.notify(id, n)
        }.onFailure { Log.w("HebrishUpdate", "notification failed", it) }
    }

    fun cancel(ctx: Context, id: Int) {
        runCatching { ctx.getSystemService(NotificationManager::class.java).cancel(id) }
    }
}
