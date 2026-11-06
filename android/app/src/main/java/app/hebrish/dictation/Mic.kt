package app.hebrish.dictation

import android.content.Context
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.os.Build
import android.os.SystemClock
import app.hebrish.core.Recorder

/**
 * Which microphone a take uses. The standing preference is an order of mic *types*
 * ([MicOrder], Prefs.micOrder, set on the Controls screen): the first type with a mic connected
 * wins. A source chip's picker overrides that for the session ([choose]). Transcription Mode
 * keeps its own choice, Prefs.tmMic: [AUTO] (follow the order) or a device key from [key].
 *
 * USB mics need no permission beyond RECORD_AUDIO: Android's own USB audio stack exposes them as
 * ordinary input devices, so `setPreferredDevice` reaches them like any other mic.
 *
 * A classic Bluetooth headset mic (TYPE_BLUETOOTH_SCO) only carries audio while the phone holds
 * a call-audio link to it, so [route] opens that link (setCommunicationDevice on Android 12+,
 * startBluetoothSco before) and [release] closes it after the take. LE Audio headsets
 * (TYPE_BLE_HEADSET) need the same on Android 12+. The link drops the headset's music quality
 * while it is open: that is Bluetooth, not this app. (I: written 2026-10-20 from the Android
 * docs; not yet tried with a headset.)
 */
object Mic {
    const val AUTO = "auto"

    private fun am(ctx: Context) = ctx.getSystemService(AudioManager::class.java)

    /** Microphones that can be chosen now. */
    fun inputs(ctx: Context): List<AudioDeviceInfo> =
        am(ctx).getDevices(AudioManager.GET_DEVICES_INPUTS).filter { it.type in CHOOSABLE }
            .distinctBy { key(it) }

    /** Stable id for a device across reconnects (device ids change): type + product name. */
    fun key(d: AudioDeviceInfo) = "${d.type}:${d.productName}"

    fun isBluetooth(d: AudioDeviceInfo) = d.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO || d.type == TYPE_BLE_HEADSET

    fun kind(d: AudioDeviceInfo): MicKind? = kind(d.type)

    private fun kind(type: Int): MicKind? = when (type) {
        in USB -> MicKind.USB
        AudioDeviceInfo.TYPE_BLUETOOTH_SCO, TYPE_BLE_HEADSET -> MicKind.BLUETOOTH
        in WIRED -> MicKind.WIRED
        AudioDeviceInfo.TYPE_BUILTIN_MIC -> MicKind.PHONE
        else -> null
    }

    fun icon(kind: MicKind?) = when (kind) {
        MicKind.USB -> R.drawable.ic_mic_usb
        MicKind.BLUETOOTH -> R.drawable.ic_mic_bluetooth
        MicKind.WIRED -> R.drawable.ic_mic_wired
        MicKind.PHONE -> R.drawable.ic_mic_phone
        null -> R.drawable.ic_mic
    }

    /** The icon for a chip naming [d]; null is the system default, the phone's mic. */
    fun icon(d: AudioDeviceInfo?) = icon(if (d == null) MicKind.PHONE else kind(d))

    fun kindName(kind: MicKind) = when (kind) {
        MicKind.USB -> R.string.mic_kind_usb
        MicKind.BLUETOOTH -> R.string.mic_kind_bluetooth
        MicKind.WIRED -> R.string.mic_kind_wired
        MicKind.PHONE -> R.string.mic_kind_phone
    }

    /**
     * The standing order. Until one is saved, a mic picked under the old single choice
     * (Prefs.oldMicChoice, up to 1.017) goes first, so an update doesn't change someone's mic.
     */
    fun order(ctx: Context): List<MicKind> {
        Prefs.micOrder(ctx)?.let { return MicOrder.parse(it) }
        val old = Prefs.oldMicChoice(ctx).substringBefore(':').toIntOrNull()?.let { kind(it) }
        return if (old == null) MicOrder.DEFAULT else MicOrder.promote(MicOrder.DEFAULT, old)
    }

    /** Saves the standing order; it replaces any one-off choice. */
    fun setOrder(ctx: Context, order: List<MicKind>) {
        Prefs.setMicOrder(ctx, MicOrder.encode(order))
        session = null
    }

    /** Connected mics, best first: what a source chip's picker offers. */
    fun choices(ctx: Context): List<AudioDeviceInfo> = MicOrder.rank(inputs(ctx), order(ctx)) { kind(it) }

    /**
     * One-off choice from a source chip's picker: a device [key], or null to follow the order.
     * Held in memory for the session, which ends after [MicOrder.SESSION_MS] with no take, when
     * the app's process ends, or when the order is changed. Services live for days, so "until the
     * process ends" alone would quietly turn it into a standing choice.
     */
    @Volatile private var session: String? = null
    @Volatile private var sessionUsed = 0L

    private fun sessionChoice(): String? = session?.takeIf {
        MicOrder.sessionLive(sessionUsed, SystemClock.elapsedRealtime())
    }

    /** Uses [d] for this session, or just follows the order if the order would pick it anyway. */
    fun choose(ctx: Context, d: AudioDeviceInfo) {
        session = key(d).takeIf { it != choices(ctx).firstOrNull()?.let(::key) }
        sessionUsed = SystemClock.elapsedRealtime()
    }

    /** The mic the next take should use, or null if Android lists none we can name. */
    fun preferred(ctx: Context, choice: String = sessionChoice() ?: AUTO): AudioDeviceInfo? {
        val all = choices(ctx)
        if (choice != AUTO) all.firstOrNull { key(it) == choice }?.let { return it }
        // Following the order, or the chosen mic isn't connected right now.
        return all.firstOrNull()
    }

    /** Picks the mic for [r]'s next start and opens a Bluetooth link if it needs one. */
    fun prepare(ctx: Context, r: Recorder) {
        if (sessionChoice() != null) sessionUsed = SystemClock.elapsedRealtime()
        val d = preferred(ctx)
        r.preferredDevice = d
        if (d != null && isBluetooth(d)) route(ctx, d)
    }

    /** Opens the Bluetooth link for [d] when it needs one (Transcription Mode's own mic choice). */
    fun routeFor(ctx: Context, d: AudioDeviceInfo?) {
        if (d != null && isBluetooth(d)) route(ctx, d)
    }

    @Suppress("DEPRECATION")
    private fun route(ctx: Context, d: AudioDeviceInfo) {
        val am = am(ctx)
        runCatching {
            if (Build.VERSION.SDK_INT >= 31) {
                // The communication device is an output; pick the one on the same headset.
                val out = am.availableCommunicationDevices.firstOrNull { it.address == d.address && isBluetooth(it) }
                    ?: am.availableCommunicationDevices.firstOrNull { isBluetooth(it) }
                if (out != null) am.setCommunicationDevice(out)
            } else {
                am.startBluetoothSco()
                am.isBluetoothScoOn = true
            }
            routed = true
        }
    }

    @Volatile private var routed = false

    /** Closes the Bluetooth link [prepare] opened, if any. Call when the take ends. */
    @Suppress("DEPRECATION")
    fun release(ctx: Context) {
        if (!routed) return
        routed = false
        val am = am(ctx)
        runCatching {
            if (Build.VERSION.SDK_INT >= 31) am.clearCommunicationDevice()
            else { am.isBluetoothScoOn = false; am.stopBluetoothSco() }
        }
    }

    /** Name for Try's status line: "Bluetooth: Pixel Buds", "Phone mic". */
    fun label(ctx: Context, d: AudioDeviceInfo?): String = when {
        d == null || d.type == AudioDeviceInfo.TYPE_BUILTIN_MIC -> ctx.getString(R.string.mic_builtin)
        isBluetooth(d) -> ctx.getString(R.string.mic_bluetooth, d.productName)
        d.type in WIRED -> ctx.getString(R.string.mic_wired)
        d.type in USB -> ctx.getString(R.string.mic_usb, d.productName)
        else -> d.productName.toString()
    }

    /**
     * Compact name for the floating mic's source chip (0.7.2): "BT Pixel Bu…", "Internal". Long
     * Bluetooth names used to stretch the bar and push Retake and Discard along.
     */
    fun shortLabel(ctx: Context, d: AudioDeviceInfo?): String = when {
        d == null || d.type == AudioDeviceInfo.TYPE_BUILTIN_MIC -> ctx.getString(R.string.mic_internal)
        isBluetooth(d) -> ctx.getString(R.string.mic_bt_short, clip(d.productName.toString()))
        d.type in WIRED -> ctx.getString(R.string.mic_wired_short)
        else -> ctx.getString(R.string.mic_usb_short, clip(d.productName.toString()))
    }

    private fun clip(name: String) = if (name.length <= SHORT_NAME) name else name.take(SHORT_NAME - 1).trimEnd() + "…"

    /**
     * The mic Android gave [r] instead of the one it was asked for, or null if it gave the right
     * one. setPreferredDevice is only a request, and a silent fallback looks like the mic being
     * ignored. Bluetooth is skipped: its link can still be opening when the take starts (1.008).
     */
    fun substitute(r: Recorder): AudioDeviceInfo? {
        val want = r.preferredDevice ?: return null
        val got = r.routedDevice ?: return null
        return got.takeIf { !isBluetooth(want) && it.id != want.id && key(it) != key(want) }
    }

    /** Every input Android reports, usable or not: the Controls screen's check for a mic that won't show. */
    fun report(ctx: Context): String = am(ctx).getDevices(AudioManager.GET_DEVICES_INPUTS)
        .joinToString(", ") { "${it.productName} (type ${it.type})" }

    /** Longest device name [shortLabel] shows before cutting it with "…". */
    private const val SHORT_NAME = 10

    /** AudioDeviceInfo.TYPE_BLE_HEADSET (API 31), spelled out so this compiles against older stubs. */
    private const val TYPE_BLE_HEADSET = 26
    private val USB = setOf(AudioDeviceInfo.TYPE_USB_DEVICE, AudioDeviceInfo.TYPE_USB_HEADSET, AudioDeviceInfo.TYPE_USB_ACCESSORY)
    private val WIRED = setOf(AudioDeviceInfo.TYPE_WIRED_HEADSET, AudioDeviceInfo.TYPE_LINE_ANALOG, AudioDeviceInfo.TYPE_LINE_DIGITAL, AudioDeviceInfo.TYPE_AUX_LINE)
    private val CHOOSABLE = USB + WIRED + setOf(AudioDeviceInfo.TYPE_BUILTIN_MIC, AudioDeviceInfo.TYPE_BLUETOOTH_SCO, TYPE_BLE_HEADSET)
}
