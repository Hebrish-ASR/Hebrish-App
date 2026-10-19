package com.danielrosehill.parlance

import android.content.Context
import android.os.Handler
import android.os.Looper

/**
 * Holds the one download or move in progress so it survives the setup screen being recreated.
 * Both report through [Status.Running]; only one runs at a time. Also holds the result of the
 * last update check per model ([latest]).
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
    /** The model and version being downloaded, for the progress label. */
    @Volatile var target: Pair<Catalogue.Model, ModelStore.Manifest?>? = null
        private set
    var listener: ((Status) -> Unit)? = null

    /** What each model's HF `main` held at its last successful check, by model id. */
    private val latestById = java.util.concurrent.ConcurrentHashMap<String, ModelStore.Manifest>()
    fun latest(id: String): ModelStore.Manifest? = latestById[id]
    @Volatile var checking = false
        private set
    @Volatile var checkError: String? = null
        private set

    /** Automatic checks run at most this often; the button forces one. */
    private const val CHECK_EVERY_MS = 6 * 60 * 60 * 1000L

    /** Refreshes the catalogue, then looks for a newer version of the selected model. */
    fun check(ctx: Context, force: Boolean = false) {
        val app = ctx.applicationContext
        if (checking) return
        val model = Catalogue.selected(app)
        if (!force && latestById[model.id] != null && System.currentTimeMillis() - Prefs.lastCheck(app) < CHECK_EVERY_MS) return
        checking = true
        checkError = null
        publish(status)
        Thread {
            try {
                Catalogue.refresh(app)
                val m = Catalogue.selected(app)
                latestById[m.id] = ModelStore.checkLatest(app, m)
                Prefs.setLastCheck(app, System.currentTimeMillis())
            } catch (e: Exception) {
                checkError = e.message ?: e.javaClass.simpleName
            } finally {
                checking = false
                publish(status)
            }
        }.start()
    }

    /** A different version of the selected model is on HF and the current one is installed. */
    fun updateAvailable(ctx: Context): ModelStore.Manifest? {
        val model = Catalogue.selected(ctx)
        val l = latestById[model.id] ?: return null
        val cur = ModelStore.installed(ctx, model) ?: return null
        return if (ModelStore.isReady(ctx) && !l.sameWeights(cur)) l else null
    }

    /** First download of the selected model: the newest on HF, or the bundled one if HF can't be asked. */
    fun start(ctx: Context) = install(ctx, Catalogue.selected(ctx), null)

    /** Downloads the selected model's latest version; the current one keeps working until it verifies. */
    fun update(ctx: Context) {
        val model = Catalogue.selected(ctx)
        install(ctx, model, latestById[model.id] ?: return)
    }

    private fun install(ctx: Context, model: Catalogue.Model, m: ModelStore.Manifest?) {
        val guess = m ?: latestById[model.id] ?: ModelStore.installed(ctx, model)
        run(ctx, moving = false, total = guess?.totalBytes ?: 0L) { app, report ->
            target = model to guess
            val chosen = m ?: latestById[model.id]
                ?: runCatching { ModelStore.checkLatest(app, model).also { latestById[model.id] = it } }.getOrNull()
                ?: ModelStore.installed(app, model)
                ?: throw java.io.IOException("Couldn't reach Hugging Face to find ${model.name}")
            target = model to chosen
            ModelStore.download(app, model, chosen, { cancel }, report)
            // Only now that every file is verified: switch over, then delete the old weights.
            Transcriber.unload()
            Prefs.setInstalledManifest(app, model.id, chosen.toJson())
            ModelStore.pruneOld(app, model)
        }
    }

    /**
     * Switches the model location to [to] (null = app storage). Every model ready at the old
     * location is moved there, unless a ready copy is already present at [to] (e.g. put there by
     * another app or an earlier install), which is simply used.
     */
    fun relocate(ctx: Context, to: String?) {
        val from = Prefs.modelRoot(ctx)
        if (from == to || status is Status.Running) return
        val app = ctx.applicationContext
        val toMove = ModelStore.readyModels(app, from).filter { !ModelStore.isReady(app, to, it) }
        if (toMove.isEmpty()) {
            Transcriber.unload()
            Prefs.setModelRoot(app, to)
            publish(Status.Idle)
            return
        }
        val total = toMove.sumOf { ModelStore.installed(app, it)!!.totalBytes }
        run(app, moving = true, total = total) { a, report ->
            Transcriber.unload()
            var offset = 0L
            for (model in toMove) {
                ModelStore.move(a, model, from, to, offset, { cancel }, report)
                offset += ModelStore.installed(a, model)!!.totalBytes
            }
            Prefs.setModelRoot(a, to)
        }
    }

    private fun run(ctx: Context, moving: Boolean, total: Long, job: (Context, (Long) -> Unit) -> Unit) {
        if (status is Status.Running) return
        val app = ctx.applicationContext
        cancel = false
        this.moving = moving
        target = null
        publish(Status.Running(0, total))
        Thread {
            var last = 0L
            try {
                job(app) { done ->
                    val t = if (moving) total else target?.second?.totalBytes ?: total
                    if (done - last > 2_000_000 || done == t) {
                        last = done
                        publish(Status.Running(done, t))
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

    /** Forgets a failed download, so it isn't reported against a model picked afterwards. */
    fun clearFailure() {
        if (status is Status.Failed) publish(Status.Idle)
    }

    private fun publish(s: Status) {
        status = s
        main.post { listener?.invoke(s) }
    }
}
