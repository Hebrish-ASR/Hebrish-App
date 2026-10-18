package com.danielrosehill.codeswitchvoice

import android.content.Context
import android.os.Handler
import android.os.Looper

/**
 * Holds the one download or move in progress so it survives the setup screen being recreated.
 * Both report through [Status.Running]; only one runs at a time.
 */
object ModelDownload {
    sealed class Status {
        object Idle : Status()
        data class Running(val done: Long) : Status()
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
    var listener: ((Status) -> Unit)? = null

    fun start(ctx: Context) = run(ctx, moving = false) { app, report ->
        ModelStore.pruneOld(app)
        ModelStore.download(app, { cancel }, report)
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
        run(app, moving = true) { a, report ->
            Transcriber.unload()
            ModelStore.move(a, from, to, { cancel }, report)
            Prefs.setModelRoot(a, to)
        }
    }

    private fun run(ctx: Context, moving: Boolean, job: (Context, (Long) -> Unit) -> Unit) {
        if (status is Status.Running) return
        val app = ctx.applicationContext
        cancel = false
        this.moving = moving
        publish(Status.Running(0))
        Thread {
            var last = 0L
            try {
                job(app) { done ->
                    if (done - last > 2_000_000 || done == ModelStore.totalBytes) {
                        last = done
                        publish(Status.Running(done))
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
