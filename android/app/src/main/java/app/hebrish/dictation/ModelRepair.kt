package app.hebrish.dictation

import app.hebrish.core.*
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * A downloaded model whose files no longer match their manifest (a power cut right after an
 * update, 2026-11-26: docs/debug-log/2026-11-26-truncated-encoder-after-power-loss.md) is
 * downloaded again instead of leaving the keyboard on "Model not downloaded". Only the damaged
 * files are fetched ([ModelStore.downloadFiles] keeps those at the right size). Port of the
 * desktop's `_redownload_damaged` (1.047). docs/maintaining.md, "Damaged models are downloaded again".
 */
object ModelRepair {
    private const val TAG = "HebrishRepair"

    /** Main thread. Starts the download if [model] is damaged and nothing else is downloading; true if it did. */
    fun run(ctx: Context, model: Catalogue.Model = Catalogue.selected(ctx), background: Boolean = false): Boolean {
        val app = ctx.applicationContext
        if (ModelDownload.status is ModelDownload.Status.Running || ModelDownload.moving) return false
        val bad = ModelStore.damaged(app, model)
        if (bad.isEmpty()) return false
        Log.w(TAG, "${model.id} damaged (${bad.joinToString()}): downloading again")
        UpdateNotices.post(app, UpdateNotices.MODEL_DAMAGED * 1000 + Math.floorMod(model.id.hashCode(), 1000),
            app.getString(R.string.model_damaged_title, model.name),
            app.getString(R.string.model_damaged_text, bad.joinToString()), Intent(app, ModelsActivity::class.java))
        if (background && ModelDownload.latest(model.id) != null) ModelDownload.update(app, model, background = true)
        else ModelDownload.download(app, model)
        return true
    }
}
