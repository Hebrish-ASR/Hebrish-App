package app.hebrish.dictation

import android.content.Context
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.os.Build
import app.hebrish.core.Recorder

/**
 * Which microphone a take uses. Prefs.micChoice is [AUTO] (the default) or a device key from
 * [key]. Automatic always prefers a Bluetooth headset mic when one is connected, then a wired or
 * USB headset, then the phone's own mic.
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

    /** The mic the next take should use, or null for the system default (the phone's mic). */
    fun preferred(ctx: Context): AudioDeviceInfo? {
        val all = inputs(ctx)
        val choice = Prefs.micChoice(ctx)
        if (choice != AUTO) all.firstOrNull { key(it) == choice }?.let { return it }
        // Automatic, or the chosen mic isn't connected right now.
        return all.firstOrNull { isBluetooth(it) }
            ?: all.firstOrNull { it.type in HEADSETS }
    }

    /** Picks the mic for [r]'s next start and opens a Bluetooth link if it needs one. */
    fun prepare(ctx: Context, r: Recorder) {
        val d = preferred(ctx)
        r.preferredDevice = d
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

    /** Name for the keyboard's and Try's status line: "Bluetooth: Pixel Buds", "Phone mic". */
    fun label(ctx: Context, d: AudioDeviceInfo?): String = when {
        d == null || d.type == AudioDeviceInfo.TYPE_BUILTIN_MIC -> ctx.getString(R.string.mic_builtin)
        isBluetooth(d) -> ctx.getString(R.string.mic_bluetooth, d.productName)
        d.type == AudioDeviceInfo.TYPE_WIRED_HEADSET -> ctx.getString(R.string.mic_wired)
        d.type == AudioDeviceInfo.TYPE_USB_HEADSET || d.type == AudioDeviceInfo.TYPE_USB_DEVICE -> ctx.getString(R.string.mic_usb, d.productName)
        else -> d.productName.toString()
    }

    /**
     * Compact name for the floating mic's source chip (0.7.2): "BT Pixel Bu…", "Internal". Long
     * Bluetooth names used to stretch the bar and push Retake and Discard along.
     */
    fun shortLabel(ctx: Context, d: AudioDeviceInfo?): String = when {
        d == null || d.type == AudioDeviceInfo.TYPE_BUILTIN_MIC -> ctx.getString(R.string.mic_internal)
        isBluetooth(d) -> ctx.getString(R.string.mic_bt_short, clip(d.productName.toString()))
        d.type == AudioDeviceInfo.TYPE_WIRED_HEADSET -> ctx.getString(R.string.mic_wired_short)
        else -> ctx.getString(R.string.mic_usb_short, clip(d.productName.toString()))
    }

    private fun clip(name: String) = if (name.length <= SHORT_NAME) name else name.take(SHORT_NAME - 1).trimEnd() + "…"

    /**
     * The floating mic's source chip was tapped while [current] records: switch between the
     * phone's mic and Automatic (Bluetooth first). Saved as Prefs.micChoice, so the next take and
     * the Controls screen agree. False when there is nothing to switch to (internal is in use and
     * no headset is connected).
     */
    fun toggle(ctx: Context, current: AudioDeviceInfo?): Boolean {
        val internal = current == null || current.type == AudioDeviceInfo.TYPE_BUILTIN_MIC
        if (internal) {
            if (inputs(ctx).none { isBluetooth(it) || it.type in HEADSETS }) return false
            Prefs.setMicChoice(ctx, AUTO)
        } else {
            val phone = inputs(ctx).firstOrNull { it.type == AudioDeviceInfo.TYPE_BUILTIN_MIC } ?: return false
            Prefs.setMicChoice(ctx, key(phone))
        }
        return true
    }

    /** Longest device name [shortLabel] shows before cutting it with "…". */
    private const val SHORT_NAME = 10

    /** AudioDeviceInfo.TYPE_BLE_HEADSET (API 31), spelled out so this compiles against older stubs. */
    private const val TYPE_BLE_HEADSET = 26
    private val HEADSETS = setOf(AudioDeviceInfo.TYPE_WIRED_HEADSET, AudioDeviceInfo.TYPE_USB_HEADSET, AudioDeviceInfo.TYPE_USB_DEVICE)
    private val CHOOSABLE = HEADSETS + setOf(AudioDeviceInfo.TYPE_BUILTIN_MIC, AudioDeviceInfo.TYPE_BLUETOOTH_SCO, TYPE_BLE_HEADSET)
}
