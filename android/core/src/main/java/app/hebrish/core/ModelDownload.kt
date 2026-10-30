package app.hebrish.core

import android.content.Context
import android.os.Handler
import android.os.Looper

/**
 * Holds the one download or move in progress so it survives the setup screen being recreated.
 * Both report through [Status.Running]; only one runs at a time. Further downloads wait in a
 * queue ([download], [downloadAll]) and start when the current one finishes. Any model can be
 * downloaded, not only the selected one. Also holds the result of the last update check per
 * model ([latest]).
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
    /** Model whose download last failed, so the failure is shown against the right model. */
    @Volatile var failedId: String? = null
        private set
    /** Models waiting for the current download to finish, in order. */
    private val queue = java.util.concurrent.ConcurrentLinkedQueue<Catalogue.Model>()
    fun queued(id: String) = queue.any { it.id == id }

    /** What each model's HF `main` held at its last successful check, by model id. */
    private val latestById = java.util.concurrent.ConcurrentHashMap<String, ModelStore.Manifest>()
    fun latest(id: String): ModelStore.Manifest? = latestById[id]
    @Volatile var checking = false
        private set
    @Volatile var checkError: String? = null
        private set

    /** Automatic checks run at most this often; the button forces one. */
    private const val CHECK_EVERY_MS = 6 * 60 * 60 * 1000L

    /** Refreshes the catalogue, then looks for newer versions of the selected and every downloaded model. */
    fun check(ctx: Context, force: Boolean = false) {
        val app = ctx.applicationContext
        if (checking) return
        val model = Catalogue.selected(app)
        if (!force && latestById[model.id] != null && System.currentTimeMillis() - ModelPrefs.lastCheck(app) < CHECK_EVERY_MS) return
        checking = true
        checkError = null
        publish(status)
        Thread {
            try {
                Catalogue.refresh(app)
                val sel = Catalogue.selected(app)
                latestById[sel.id] = ModelStore.checkLatest(app, sel)
                for (m in ModelStore.readyModels(app)) if (m.id != sel.id) {
                    runCatching { ModelStore.checkLatest(app, m) }.onSuccess { latestById[m.id] = it }
                }
                ModelPrefs.setLastCheck(app, System.currentTimeMillis())
            } catch (e: Exception) {
                checkError = e.message ?: e.javaClass.simpleName
            } finally {
                checking = false
                publish(status)
            }
        }.start()
    }

    /** A different version of [model] is published and the current one is installed. */
    fun updateAvailable(ctx: Context, model: Catalogue.Model = Catalogue.selected(ctx)): ModelStore.Manifest? {
        val l = latestById[model.id] ?: return null
        val cur = ModelStore.installed(ctx, model) ?: return null
        return if (ModelStore.isReady(ctx, model = model) && !l.sameWeights(cur)) l else null
    }

    /** First download of the selected model: the newest published, or the bundled one if the server can't be asked. */
    fun start(ctx: Context) = download(ctx, Catalogue.selected(ctx))

    /** Downloads [model] (newest version), or queues it behind the download in progress. */
    fun download(ctx: Context, model: Catalogue.Model) {
        if (!model.available || ModelStore.isReady(ctx, model = model)) return
        if (status is Status.Running) {
            if (target?.first?.id != model.id && !queued(model.id)) queue.add(model)
            publish(status)
            return
        }
        install(ctx, model, null)
    }

    /** Every available model that isn't on the phone yet, one after another. */
    fun downloadAll(ctx: Context) {
        for (m in Catalogue.get(ctx).models) download(ctx, m)
    }

    /** Downloads [model]'s latest version; the current one keeps working until it verifies. */
    fun update(ctx: Context, model: Catalogue.Model = Catalogue.selected(ctx)) {
        install(ctx, model, latestById[model.id] ?: return)
    }

    private fun install(ctx: Context, model: Catalogue.Model, m: ModelStore.Manifest?) {
        val guess = m ?: latestById[model.id] ?: ModelStore.installed(ctx, model)
        failedId = null
        run(ctx, moving = false, total = guess?.totalBytes ?: 0L, model = model) { app, report ->
            target = model to guess
            val chosen = m ?: latestById[model.id]
                ?: runCatching { ModelStore.checkLatest(app, model).also { latestById[model.id] = it } }.getOrNull()
                ?: ModelStore.installed(app, model)
                ?: throw java.io.IOException("Couldn't reach Hugging Face to find ${model.name}")
            target = model to chosen
            ModelStore.download(app, model, chosen, { cancel }, report)
            // Only now that every file is verified: switch over, then delete the old weights.
            if (Catalogue.selected(app).id == model.id) Transcriber.unload()
            ModelPrefs.setInstalledManifest(app, model.id, chosen.toJson())
            ModelStore.pruneOld(app, model)
        }
    }

    /**
     * Switches the model location to [to] (null = app storage). Every model ready at the old
     * location is moved there, unless a ready copy is already present at [to] (e.g. put there by
     * another app or an earlier install), which is simply used.
     */
    fun relocate(ctx: Context, to: String?) {
        val from = ModelPrefs.modelRoot(ctx)
        if (from == to || status is Status.Running) return
        val app = ctx.applicationContext
        val toMove = ModelStore.readyModels(app, from).filter { !ModelStore.isReady(app, to, it) }
        if (toMove.isEmpty()) {
            Transcriber.unload()
            ModelPrefs.setModelRoot(app, to)
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
            ModelPrefs.setModelRoot(a, to)
        }
    }

    private fun run(ctx: Context, moving: Boolean, total: Long, model: Catalogue.Model? = null,
                    job: (Context, (Long) -> Unit) -> Unit) {
        if (status is Status.Running) return
        val app = ctx.applicationContext
        cancel = false
        this.moving = moving
        target = model?.let { it to null }
        publish(Status.Running(0, total))
        Thread {
            var last = 0L
            var lastAt = 0L
            try {
                job(app) { done ->
                    val t = if (moving) total else target?.second?.totalBytes ?: total
                    // Every 2 MB and at most 5 times a second: each one redraws every model card,
                    // and on fast Wi-Fi 2 MB alone meant several redraws a second (up to 1.008).
                    val now = android.os.SystemClock.elapsedRealtime()
                    if ((done - last > 2_000_000 && now - lastAt >= 200) || done == t) {
                        last = done
                        lastAt = now
                        publish(Status.Running(done, t))
                    }
                }
                publish(Status.Done)
                // Next in the queue, if any; it is started from the main thread like any other.
                queue.poll()?.let { next -> main.post { download(app, next) } }
            } catch (e: InterruptedException) {
                queue.clear()
                publish(Status.Idle)
            } catch (e: Exception) {
                failedId = target?.first?.id
                queue.clear()
                publish(Status.Failed(e.message ?: e.javaClass.simpleName))
            }
        }.start()
    }

    /** Stops the running download and empties the queue. */
    fun cancel() {
        queue.clear()
        cancel = true
    }

    /** Takes a waiting model out of the queue. */
    fun unqueue(model: Catalogue.Model) {
        queue.removeAll { it.id == model.id }
        publish(status)
    }

    /** Forgets a failed download, so it isn't reported against a model picked afterwards. */
    fun clearFailure() {
        if (status is Status.Failed) publish(Status.Idle)
    }

    private fun publish(s: Status) {
        status = s
        main.post { listener?.invoke(s) }
    }
}
