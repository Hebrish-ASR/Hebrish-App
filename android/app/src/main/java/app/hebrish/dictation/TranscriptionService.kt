package app.hebrish.dictation

import app.hebrish.core.*
import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import java.io.File

/**
 * Transcription Mode's recording, held for the whole process rather than by the screen (I-15,
 * Daniel 2026-10-24), so it can carry on in the background. [TranscriptionActivity] drives it and
 * redraws from it; [TranscriptionService] keeps the process in the foreground while it records.
 */
object Recording {
    private val ui = Handler(Looper.getMainLooper())
    /** Redraw the screen, if it is open. Main thread. */
    var listener: (() -> Unit)? = null
    /** Last message for the screen's status line (mic lost, limit reached); cleared when shown. */
    var notice: Int = 0
    lateinit var app: Context

    val tape = Tape(onLimit = { ui.post { limit() } })
    /** A stopped recording waiting for Transcribe. */
    var held: File? = null

    /** The take reached Tape.MAX_SECONDS (stop, keep it for Transcribe) or the mic went away (pause). */
    private fun limit() {
        if (!tape.active) return
        if (tape.seconds >= Tape.MAX_SECONDS) {
            held = tape.stop() ?: held
            notice = R.string.tm_limit
        } else {
            tape.pause()
            notice = R.string.tm_mic_lost
        }
        Mic.release(app)
        changed()
    }

    /** After any change: the notification follows, and the screen redraws. */
    fun changed() {
        TranscriptionService.sync(app)
        listener?.invoke()
    }

    fun pauseOrResume(ctx: Context) {
        if (!tape.active) return
        if (tape.paused) {
            val d = Mic.preferred(ctx, Prefs.tmMic(ctx))
            tape.preferredDevice = d
            Mic.routeFor(ctx, d)
            runCatching { tape.resume() }.onFailure { notice = R.string.tm_mic_lost }
        } else {
            tape.pause()
            Mic.release(ctx)
        }
        changed()
    }

    fun stop(ctx: Context) {
        held = tape.stop() ?: held
        Mic.release(ctx)
        changed()
    }

    /** Background recording is on and, on Android 13+, notifications are allowed (for its controls). */
    fun background(ctx: Context) = Prefs.tmBackground(ctx) && notificationsAllowed(ctx)

    fun notificationsAllowed(ctx: Context) = Build.VERSION.SDK_INT < 33 ||
        ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
}

/**
 * A foreground service of type `microphone` while Transcription Mode records with background
 * recording on: Android keeps the mic open with the screen off or another app in front only for
 * such a service, and only if it was started while the app was in front (it is: from Record).
 * The notification shows the elapsed time and has Pause/Resume and Stop; tapping it opens the
 * screen. Holds no state: everything is in [Recording].
 */
class TranscriptionService : Service() {
    companion object {
        private const val CHANNEL = "transcription"
        private const val ID = 41
        private const val ACTION_PAUSE = "app.hebrish.dictation.tm.PAUSE"
        private const val ACTION_STOP = "app.hebrish.dictation.tm.STOP"

        /** Start, refresh or stop the service to match [Recording]. Main thread. */
        fun sync(ctx: Context) {
            val t = Recording.tape
            val running = t.active && Recording.background(ctx)
            val i = Intent(ctx, TranscriptionService::class.java)
            val live = instance
            when {
                // Already in the foreground: just redraw. A second startForegroundService from the
                // background (the mic dropped with the screen off) could be refused on Android 12+.
                running && live != null -> live.show()
                running -> runCatching { ctx.startForegroundService(i) }
                else -> ctx.stopService(i)
            }
        }

        private var instance: TranscriptionService? = null
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Recording.app = applicationContext
        when (intent?.action) {
            ACTION_PAUSE -> Recording.pauseOrResume(this)
            ACTION_STOP -> Recording.stop(this)
        }
        if (!Recording.tape.active) {
            stopSelf()
            return START_NOT_STICKY
        }
        val n = notification()
        if (Build.VERSION.SDK_INT >= 29) startForeground(ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
        else startForeground(ID, n)
        return START_NOT_STICKY
    }

    private fun show() {
        if (!Recording.tape.active) return stopSelf()
        getSystemService(NotificationManager::class.java).notify(ID, notification())
    }

    override fun onDestroy() {
        instance = null
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }

    private fun notification(): Notification {
        val nm = getSystemService(NotificationManager::class.java)
        if (nm.getNotificationChannel(CHANNEL) == null)
            nm.createNotificationChannel(NotificationChannel(CHANNEL, getString(R.string.tm_channel), NotificationManager.IMPORTANCE_LOW))
        val t = Recording.tape
        val flags = PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        fun action(a: String) = PendingIntent.getService(this, a.hashCode(), Intent(this, TranscriptionService::class.java).setAction(a), flags)
        val open = PendingIntent.getActivity(this, 0, Intent(this, TranscriptionActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), flags)
        return Notification.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_mic)
            .setContentTitle(getString(if (t.paused) R.string.tm_notif_paused else R.string.tm_notif_recording))
            .setContentIntent(open)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setCategory(Notification.CATEGORY_SERVICE)
            // A running clock while recording; the time so far while paused.
            .setUsesChronometer(!t.paused)
            .setWhen(System.currentTimeMillis() - t.seconds * 1000L)
            .setShowWhen(!t.paused)
            .setContentText(if (t.paused) TranscriptionActivity.clock(t.seconds.toFloat()) else null)
            .addAction(Notification.Action.Builder(null, getString(if (t.paused) R.string.tm_resume else R.string.tm_pause), action(ACTION_PAUSE)).build())
            .addAction(Notification.Action.Builder(null, getString(R.string.tm_stop), action(ACTION_STOP)).build())
            .build()
    }
}
