package app.hebrish.dictation

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * B-106 (Daniel, 2026-11-13, R-2026-11-13-3): the `fdroid` build updates itself. Once the user
 * allows "Install unknown apps" for Hebrish (Setup), a periodic job ([UpdateJobs.APP]) runs [run]:
 * read cdn.hebrish.app/downloads/latest.json, download a newer APK into the app's cache, check its
 * size and SHA-256 against the manifest, and install it with a PackageInstaller session. On
 * Android 12+ the session asks for no user action, so a self-update goes through silently; when
 * Android still asks (Android 9 to 11, or another store owns updates on 14+), a notification opens
 * the confirmation. Never while a take is open ([TakeGuard]). The "Check for updates now" button on
 * Install and updates runs the same path in the foreground. docs/maintaining.md, "App updates in
 * the background (B-106)".
 */
object AppUpdates {
    const val MANIFEST = "https://cdn.hebrish.app/downloads/latest.json"
    private const val TAG = "HebrishUpdate"
    const val ACTION_STATUS = "app.hebrish.dictation.update.STATUS"
    const val EXTRA_MANUAL = "manual"
    const val EXTRA_VERSION = "version"

    enum class Kind { UP_TO_DATE, INSTALLING, POSTPONED, NEEDS_PERMISSION, MISMATCH, FAILED, OFF }
    data class Outcome(val kind: Kind, val version: String? = null, val error: String? = null)

    private val main = Handler(Looper.getMainLooper())
    @Volatile private var running = false
    /** The Install and updates screen, while open: progress and results of a check (main thread). */
    var listener: ((String) -> Unit)? = null

    /** "Install unknown apps" is allowed for Hebrish (Android 8+; minSdk is 28). */
    fun permitted(ctx: Context): Boolean = Channel.selfUpdate &&
        runCatching { ctx.packageManager.canRequestPackageInstalls() }.getOrDefault(false)

    fun backgroundOn(ctx: Context): Boolean =
        Channel.selfUpdate && AppUpdateRules.backgroundOn(Prefs.appAutoUpdate(ctx), permitted(ctx))

    /** Settings' "Install unknown apps" page for this app. */
    fun permissionIntent(ctx: Context) = Intent(android.provider.Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
        android.net.Uri.parse("package:${ctx.packageName}"))

    fun say(msg: String) = main.post { listener?.invoke(msg) }

    /** Blocking; call on a worker thread. [manual]: the button (skips the switch and the take check, reports progress). */
    fun run(ctx: Context, manual: Boolean): Outcome {
        val app = ctx.applicationContext
        if (!Channel.selfUpdate) return Outcome(Kind.OFF)
        if (!manual && !backgroundOn(app)) return Outcome(Kind.OFF)
        if (running) return Outcome(Kind.POSTPONED)
        running = true
        return try {
            check(app, manual)
        } catch (e: Exception) {
            Log.w(TAG, "update failed", e)
            Outcome(Kind.FAILED, error = e.message ?: e.javaClass.simpleName)
        } finally {
            running = false
        }
    }

    private fun check(app: Context, manual: Boolean): Outcome {
        val r = AppUpdateRules.parse(get(MANIFEST)) ?: return Outcome(Kind.FAILED, error = "unreadable latest.json")
        if (!AppUpdateRules.isNewer(r.version, BuildConfig.VERSION_NAME)) return Outcome(Kind.UP_TO_DATE, r.version)
        if (!permitted(app)) return Outcome(Kind.NEEDS_PERMISSION, r.version)
        if (!manual && TakeGuard.busy()) return Outcome(Kind.POSTPONED, r.version)
        if (manual) say(app.getString(R.string.appupdate_downloading, r.version))
        val apk = fetch(app, r) ?: return Outcome(Kind.MISMATCH, r.version)
        // Checked again: the download takes a while, and a take may have started meanwhile.
        if (!manual && TakeGuard.busy()) return Outcome(Kind.POSTPONED, r.version)
        install(app, apk, r.version, manual)
        return Outcome(Kind.INSTALLING, r.version)
    }

    private fun get(url: String): String {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 15_000
        conn.readTimeout = 15_000
        conn.useCaches = false
        try {
            if (conn.responseCode != HttpURLConnection.HTTP_OK) throw java.io.IOException("HTTP ${conn.responseCode} for latest.json")
            return conn.inputStream.bufferedReader().use { it.readText() }
        } finally {
            conn.disconnect()
        }
    }

    /**
     * The APK in cache/updates/, verified, or null when what arrived doesn't match the manifest
     * (deleted). A verified file from an earlier, postponed run is reused after hashing it again.
     */
    private fun fetch(app: Context, r: AppUpdateRules.Release): File? {
        val dir = File(app.cacheDir, "updates").apply { mkdirs() }
        val target = File(dir, "Hebrish-${r.version}.apk")
        dir.listFiles()?.forEach { if (it.name != target.name) it.delete() }
        if (target.length() == r.size && AppUpdateRules.verify(target.length(), sha256(target), r) == AppUpdateRules.Verdict.OK) return target
        target.delete()
        val part = File(dir, target.name + ".part")
        val md = MessageDigest.getInstance("SHA-256")
        var n = 0L
        val conn = URL(r.url).openConnection() as HttpURLConnection
        conn.connectTimeout = 20_000
        conn.readTimeout = 30_000
        conn.instanceFollowRedirects = true
        try {
            if (conn.responseCode != HttpURLConnection.HTTP_OK) throw java.io.IOException("HTTP ${conn.responseCode} for the APK")
            conn.inputStream.use { input ->
                FileOutputStream(part).use { out ->
                    val buf = ByteArray(1 shl 16)
                    while (true) {
                        val k = input.read(buf)
                        if (k < 0) break
                        n += k
                        if (n > r.size) break
                        md.update(buf, 0, k)
                        out.write(buf, 0, k)
                    }
                }
            }
        } finally {
            conn.disconnect()
        }
        val verdict = AppUpdateRules.verify(n, AppUpdateRules.hex(md.digest()), r)
        if (verdict != AppUpdateRules.Verdict.OK) {
            Log.w(TAG, "download of ${r.version} rejected: $verdict ($n bytes)")
            part.delete()
            return null
        }
        if (!part.renameTo(target)) throw java.io.IOException("couldn't keep the download")
        return target
    }

    private fun sha256(f: File): String {
        val md = MessageDigest.getInstance("SHA-256")
        f.inputStream().use { input ->
            val buf = ByteArray(1 shl 16)
            while (true) {
                val k = input.read(buf)
                if (k < 0) break
                md.update(buf, 0, k)
            }
        }
        return AppUpdateRules.hex(md.digest())
    }

    /** One PackageInstaller session for the verified APK; the result arrives at [AppUpdateReceiver]. */
    private fun install(app: Context, apk: File, version: String, manual: Boolean) {
        val pi = app.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL).apply {
            setAppPackageName(app.packageName)
            setSize(apk.length())
            // Android 12+: no confirmation for an app updating itself, when the system allows it.
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
        }
        val id = pi.createSession(params)
        val session = pi.openSession(id)
        try {
            apk.inputStream().use { input ->
                session.openWrite("base.apk", 0, apk.length()).use { out ->
                    input.copyTo(out, 1 shl 16)
                    session.fsync(out)
                }
            }
            val status = Intent(app, AppUpdateReceiver::class.java).setAction(ACTION_STATUS)
                .putExtra(EXTRA_MANUAL, manual).putExtra(EXTRA_VERSION, version)
            // Mutable: the system adds the status extras. The intent is explicit, so this is allowed on 12+;
            // the flag is ignored below 12, where every PendingIntent is mutable.
            val pending = PendingIntent.getBroadcast(app, id, status, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE)
            Prefs.setAppUpdateInstalling(app, version)
            if (manual) say(app.getString(R.string.appupdate_installing, version))
            session.commit(pending.intentSender)
        } catch (e: Exception) {
            runCatching { session.abandon() }
            throw e
        } finally {
            session.close()
        }
    }

    /** The new version is running: say so once (from MY_PACKAGE_REPLACED or STATUS_SUCCESS, whichever comes first). */
    fun announce(ctx: Context) {
        val v = Prefs.appUpdateInstalling(ctx) ?: return
        if (v != BuildConfig.VERSION_NAME) return
        Prefs.setAppUpdateInstalling(ctx, null)
        UpdateNotices.cancel(ctx, UpdateNotices.APP_CONFIRM)
        UpdateNotices.post(ctx, UpdateNotices.APP_UPDATED, ctx.getString(R.string.appupdate_done, v), null, null)
        File(ctx.cacheDir, "updates").deleteRecursively()
    }

    /** Text for a manual check's result on Install and updates. */
    fun describe(ctx: Context, o: Outcome): String = when (o.kind) {
        Kind.UP_TO_DATE -> ctx.getString(R.string.appupdate_up_to_date, BuildConfig.VERSION_NAME)
        Kind.INSTALLING -> ctx.getString(R.string.appupdate_installing, o.version)
        Kind.POSTPONED -> ctx.getString(R.string.appupdate_busy)
        Kind.NEEDS_PERMISSION -> ctx.getString(R.string.appupdate_needs_permission, o.version)
        Kind.MISMATCH -> ctx.getString(R.string.appupdate_mismatch)
        Kind.FAILED -> ctx.getString(R.string.appupdate_failed, o.error ?: "")
        Kind.OFF -> ""
    }
}

/**
 * The install session's result ([AppUpdates.ACTION_STATUS]) and MY_PACKAGE_REPLACED (the new
 * version's first start: post "Hebrish updated", put the jobs back). Never throws.
 */
class AppUpdateReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        try {
            when (intent.action) {
                Intent.ACTION_MY_PACKAGE_REPLACED -> {
                    AppUpdates.announce(ctx)
                    UpdateJobs.sync(ctx)
                }
                AppUpdates.ACTION_STATUS -> status(ctx, intent)
            }
        } catch (t: Throwable) {
            Log.w("HebrishUpdate", "receiver failed", t)
        }
    }

    private fun status(ctx: Context, intent: Intent) {
        val manual = intent.getBooleanExtra(AppUpdates.EXTRA_MANUAL, false)
        val version = intent.getStringExtra(AppUpdates.EXTRA_VERSION) ?: ""
        when (val s = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                val confirm: Intent? = if (Build.VERSION.SDK_INT >= 33) intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java)
                    else @Suppress("DEPRECATION") intent.getParcelableExtra(Intent.EXTRA_INTENT)
                if (confirm == null) return
                // From the button, with the screen in front: show Android's prompt straight away.
                // From the background, never start an activity: a notification opens it instead.
                val shown = manual && AppUpdates.listener != null &&
                    runCatching { ctx.startActivity(confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }.isSuccess
                if (!shown) UpdateNotices.post(ctx, UpdateNotices.APP_CONFIRM, ctx.getString(R.string.appupdate_confirm_title, version),
                    ctx.getString(R.string.appupdate_confirm_text), confirm)
                if (manual) AppUpdates.say(ctx.getString(R.string.appupdate_confirm))
            }
            PackageInstaller.STATUS_SUCCESS -> AppUpdates.announce(ctx)
            else -> {
                val msg = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE) ?: "status $s"
                Log.w("HebrishUpdate", "install of $version failed: $msg")
                Prefs.setAppUpdateInstalling(ctx, null)
                if (manual) AppUpdates.say(ctx.getString(R.string.appupdate_failed, msg))
            }
        }
    }
}
