package com.danielrosehill.parlance

import android.content.Context

object Prefs {
    private fun sp(ctx: Context) = ctx.getSharedPreferences("prefs", Context.MODE_PRIVATE)

    /** Start recording as soon as the voice keyboard opens (e.g. from HeliBoard's mic key). */
    fun autoStart(ctx: Context) = sp(ctx).getBoolean("auto_start", true)
    fun setAutoStart(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("auto_start", v).apply()

    /** Switch back to the previous keyboard after inserting a transcript. */
    fun autoReturn(ctx: Context) = sp(ctx).getBoolean("auto_return", true)
    fun setAutoReturn(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("auto_return", v).apply()

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

    /** Back (key or gesture) switches to the regular keyboard instead of only hiding this one. */
    fun backSwitches(ctx: Context) = sp(ctx).getBoolean("back_switches", true)
    fun setBackSwitches(ctx: Context, v: Boolean) = sp(ctx).edit().putBoolean("back_switches", v).apply()

    /** IME id the keyboard key returns to; null = automatic (see VoiceImeService.switchBack). */
    fun returnIme(ctx: Context): String? = sp(ctx).getString("return_ime", null)
    fun setReturnIme(ctx: Context, v: String?) = sp(ctx).edit().putString("return_ime", v).apply()

    /** The last system default keyboard that wasn't this one, noted whenever setup opens. */
    fun lastOtherIme(ctx: Context): String? = sp(ctx).getString("last_other_ime", null)
    fun setLastOtherIme(ctx: Context, v: String) = sp(ctx).edit().putString("last_other_ime", v).apply()

    /** The most recent transcript, for Insert last when it could not be typed into a field. */
    fun lastTranscript(ctx: Context): String? = sp(ctx).getString("last_transcript", null)
    fun setLastTranscript(ctx: Context, v: String) = sp(ctx).edit().putString("last_transcript", v).apply()
}
