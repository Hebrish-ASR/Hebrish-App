package com.danielrosehill.codeswitchvoice

import android.content.Context
import android.os.Handler
import android.os.Looper

/**
 * Holds the one download or move in progress so it survives the setup screen being recreated.
 * Both report through [Status.Running]; only one runs at a time. Also holds the result of the
 * last update check ([latest]).
 */
object ModelDownload {
    sealed class Status {
        object Idle : Status()
        data class Running(val done: Long, val total: Long) : Status()
        object Done : Status()
        data class Failed(val message: String) : Status()
    }

    private val main = Handler(Looper.getMainLooper())
    @Volatile var status: Status = Status.Idle
        private set
    @Volatile private var cancel = false
    /** True while the running job is a move rather than a download. */
    @Volatile var moving = false
        private set
    /** The model being downloaded, for the progress label. */
    @Volatile var target: ModelStore.Manifest? = null
        private set
    var listener: ((Status) -> Unit)? = null

    /** What HF `main` held at the last successful check; null before one. */
    @Volatile var latest: ModelStore.Manifest? = null
        private set
    @Volatile var checking = false
        private set
    @Volatile var checkError: String? = null
        private set

    /** Automatic checks run at most this often; the button forces one. */
    private const val CHECK_EVERY_MS = 6 * 60 * 60 * 1000L

    /** Looks for a newer model on HF in the background. */
    fun check(ctx: Context, force: Boolean = false) {
        val app = ctx.applicationContext
        if (checking) return
        if (!force && latest != null && System.currentTimeMillis() - Prefs.lastCheck(app) < CHECK_EVERY_MS) return
        checking = true
        checkError = null
        publish(status)
        Thread {
            try {
                latest = ModelStore.checkLatest()
                Prefs.setLastCheck(app, System.currentTimeMillis())
            } catch (e: Exception) {
                checkError = e.message ?: e.javaClass.simpleName
            } finally {
                checking = false
                publish(status)
            }
        }.start()
    }

    /** A different model is on HF and the current one is installed (otherwise it's a first download). */
    fun updateAvailable(ctx: Context): ModelStore.Manifest? {
        val l = latest ?: return null
        val cur = ModelStore.installed(ctx)
        return if (ModelStore.isReady(ctx) && !l.sameWeights(cur)) l else null
    }

    /** First download: the newest model on HF, or the one this APK ships with if HF can't be asked. */
    fun start(ctx: Context) = install(ctx, null)

    /** Downloads [latest]; the current model keeps working until the new one is verified. */
    fun update(ctx: Context) {
        install(ctx, latest ?: return)
    }

    private fun install(ctx: Context, m: ModelStore.Manifest?) {
        val guess = m ?: latest ?: ModelStore.installed(ctx)
        run(ctx, moving = false, manifest = guess) { app, report ->
            val chosen = m ?: latest ?: runCatching { ModelStore.checkLatest().also { latest = it } }.getOrNull() ?: ModelStore.installed(app)
            target = chosen
            ModelStore.download(app, chosen, { cancel }, report)
            // Only now that every file is verified: switch over, then delete the old weights.
            Transcriber.unload()
            Prefs.setInstalledManifest(app, chosen.toJson())
            ModelStore.pruneOld(app)
        }
    }

    /**
     * Switches the model location to [to] (null = app storage). A model already ready at the
     * old location is moved there; one already present at [to] (e.g. put there by another app
     * or an earlier install) is simply used.
     */
    fun relocate(ctx: Context, to: String?) {
        val from = Prefs.modelRoot(ctx)
        if (from == to || status is Status.Running) return
        val app = ctx.applicationContext
        if (!ModelStore.isReady(app, from) || ModelStore.isReady(app, to)) {
            Transcriber.unload()
            Prefs.setModelRoot(app, to)
            publish(Status.Idle)
            return
        }
        run(app, moving = true, manifest = ModelStore.installed(app)) { a, report ->
            Transcriber.unload()
            ModelStore.move(a, from, to, { cancel }, report)
            Prefs.setModelRoot(a, to)
        }
    }

    private fun run(ctx: Context, moving: Boolean, manifest: ModelStore.Manifest, job: (Context, (Long) -> Unit) -> Unit) {
        if (status is Status.Running) return
        val app = ctx.applicationContext
        cancel = false
        this.moving = moving
        target = manifest
        publish(Status.Running(0, manifest.totalBytes))
        Thread {
            var last = 0L
            try {
                job(app) { done ->
                    val total = target?.totalBytes ?: manifest.totalBytes
                    if (done - last > 2_000_000 || done == total) {
                        last = done
                        publish(Status.Running(done, total))
                    }
                }
                publish(Status.Done)
            } catch (e: InterruptedException) {
                publish(Status.Idle)
            } catch (e: Exception) {
                publish(Status.Failed(e.message ?: e.javaClass.simpleName))
            }
        }.start()
    }

    fun cancel() { cancel = true }

    private fun publish(s: Status) {
        status = s
        main.post { listener?.invoke(s) }
    }
}
