package com.danielrosehill.codeswitchvoice

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

    /** JSON of the last fully downloaded ModelStore.Manifest; null means ModelStore.BUNDLED. */
    fun installedManifest(ctx: Context): String? = sp(ctx).getString("installed_manifest", null)
    fun setInstalledManifest(ctx: Context, v: String) = sp(ctx).edit().putString("installed_manifest", v).apply()

    /** Wall-clock ms of the last successful update check. */
    fun lastCheck(ctx: Context) = sp(ctx).getLong("last_check", 0L)
    fun setLastCheck(ctx: Context, v: Long) = sp(ctx).edit().putLong("last_check", v).apply()
}
