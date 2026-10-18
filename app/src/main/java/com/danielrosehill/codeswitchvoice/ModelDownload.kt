package com.danielrosehill.codeswitchvoice

import android.content.Context
import android.os.Handler
import android.os.Looper

/** Holds the one download in progress so it survives the setup screen being recreated. */
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
    var listener: ((Status) -> Unit)? = null

    fun start(ctx: Context) {
        if (status is Status.Running) return
        val app = ctx.applicationContext
        cancel = false
        publish(Status.Running(0))
        Thread {
            var last = 0L
            try {
                ModelStore.pruneOld(app)
                ModelStore.download(app, { cancel }) { done ->
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
