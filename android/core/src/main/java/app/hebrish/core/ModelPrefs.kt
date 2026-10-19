package app.hebrish.core

import android.content.Context

/**
 * Model settings shared by every app that embeds the engine (Hebrish voice keyboard, Hebrish
 * Keyboard). Same SharedPreferences file and keys as the voice keyboard used before the engine
 * moved to `core/` (0.2.0), so existing installs keep their model.
 */
object ModelPrefs {
    private fun sp(ctx: Context) = ctx.getSharedPreferences("prefs", Context.MODE_PRIVATE)

    /**
     * Absolute path of a user-chosen folder for the model, or null for app-private storage.
     * Shared storage lets other on-device apps load the same files.
     */
    fun modelRoot(ctx: Context): String? = sp(ctx).getString("model_root", null)
    fun setModelRoot(ctx: Context, v: String?) = sp(ctx).edit().putString("model_root", v).apply()

    /** Catalogue id of the model the keyboard uses; null = the catalogue's default. */
    fun selectedModel(ctx: Context): String? = sp(ctx).getString("model_id", null)
    fun setSelectedModel(ctx: Context, v: String) = sp(ctx).edit().putString("model_id", v).apply()

    /** JSON of [model]'s last fully downloaded ModelStore.Manifest; null means its ModelStore.BUNDLED one. */
    fun installedManifest(ctx: Context, model: String): String? = sp(ctx).getString("installed_manifest_$model", null)
    fun setInstalledManifest(ctx: Context, model: String, v: String?) =
        sp(ctx).edit().putString("installed_manifest_$model", v).apply()

    /** The last catalogue fetched from catalogue_url that parsed; null = the bundled asset. */
    fun catalogueJson(ctx: Context): String? = sp(ctx).getString("catalogue", null)
    fun setCatalogueJson(ctx: Context, v: String) = sp(ctx).edit().putString("catalogue", v).apply()

    /** Wall-clock ms of the last successful update check. */
    fun lastCheck(ctx: Context) = sp(ctx).getLong("last_check", 0L)
    fun setLastCheck(ctx: Context, v: Long) = sp(ctx).edit().putLong("last_check", v).apply()
}
