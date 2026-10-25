package app.hebrish.dictation

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.view.KeyEvent
import org.json.JSONObject

/**
 * Control from outside the app: broadcast intents (Tasker, Key Mapper, MacroDroid, adb) and
 * buttons (a Bluetooth shutter remote, a keyboard, a headset or media remote). Both drive the
 * floating mic (FloatingMicService), the one part of the app that is always running, so the
 * floating mic must be on. Reference for users and integrators: docs/external-control.md.
 *
 * Actions ([Action.intent] is the broadcast action, e.g. `app.hebrish.dictation.action.TOGGLE`):
 * TOGGLE starts a take or stops and transcribes it; START, STOP, RESTART (throw the take away and
 * start again), PAUSE (pause or resume), DISCARD.
 *
 * Buttons: each action can be bound to one key code (Prefs.keyFor). FloatingMicService receives
 * hardware key events (flagRequestFilterKeyEvents) and consumes bound keys only; every other key
 * goes through untouched. "Learn" on the settings screen sets Prefs.learning, and the next key
 * press the service sees is bound to that action. Prefs.keysOn off (1.004) stops the service
 * taking any key while keeping the bindings, so the remote can be used for something else; the
 * bindings can also be saved as named sets and switched between ([saveProfile], [useProfile]).
 */
object Remote {
    enum class Action(val intent: String) {
        TOGGLE("app.hebrish.dictation.action.TOGGLE"),
        START("app.hebrish.dictation.action.START"),
        STOP("app.hebrish.dictation.action.STOP"),
        RESTART("app.hebrish.dictation.action.RESTART"),
        PAUSE("app.hebrish.dictation.action.PAUSE"),
        DISCARD("app.hebrish.dictation.action.DISCARD");

        companion object {
            fun ofIntent(a: String?) = entries.firstOrNull { it.intent == a }
        }
    }

    /** Registers [onAction] for every action's broadcast. Exported: any app may send them (that is the point). */
    fun register(ctx: Context, onAction: (Action) -> Unit): BroadcastReceiver {
        val r = object : BroadcastReceiver() {
            override fun onReceive(c: Context, i: Intent) { Action.ofIntent(i.action)?.let(onAction) }
        }
        val f = IntentFilter().apply { Action.entries.forEach { addAction(it.intent) } }
        if (Build.VERSION.SDK_INT >= 33) ctx.registerReceiver(r, f, Context.RECEIVER_EXPORTED)
        else ctx.registerReceiver(r, f)
        return r
    }

    /** The action bound to [keyCode], if any. */
    fun actionFor(ctx: Context, keyCode: Int) = Action.entries.firstOrNull { Prefs.keyFor(ctx, it) == keyCode }

    fun keyName(keyCode: Int): String = KeyEvent.keyCodeToString(keyCode).removePrefix("KEYCODE_")

    /** Unbinds every action (Clear all) and ends learning. The saved sets are kept. */
    fun clearAll(ctx: Context) {
        for (a in Action.entries) Prefs.setKeyFor(ctx, a, 0)
        Prefs.setLearning(ctx, null)
    }

    // Saved sets (1.004): the current bindings under a name, to switch between remotes or uses.
    // Stored in Prefs.keyProfiles on this phone only; a later backup or sync can carry that one key.

    private fun profiles(ctx: Context) = runCatching { JSONObject(Prefs.keyProfiles(ctx)) }.getOrElse { JSONObject() }

    /** Saved set names, A–Z. */
    fun profileNames(ctx: Context): List<String> = profiles(ctx).keys().asSequence().toList().sortedBy { it.lowercase() }

    /** The bound actions of a saved set, e.g. "Toggle: VOLUME_UP"; [label] names an action. */
    fun profileSummary(ctx: Context, name: String, label: (Action) -> String): String {
        val p = profiles(ctx).optJSONObject(name) ?: return ""
        return Action.entries.filter { p.optInt(it.name, 0) != 0 }.joinToString(", ") { "${label(it)}: ${keyName(p.getInt(it.name))}" }
    }

    /** Saves the current bindings as [name], replacing a set of that name. */
    fun saveProfile(ctx: Context, name: String) {
        val p = JSONObject()
        for (a in Action.entries) Prefs.keyFor(ctx, a).let { if (it != 0) p.put(a.name, it) }
        Prefs.setKeyProfiles(ctx, profiles(ctx).put(name, p).toString())
    }

    /** Replaces the current bindings with saved set [name]; actions it doesn't bind are cleared. */
    fun useProfile(ctx: Context, name: String) {
        val p = profiles(ctx).optJSONObject(name) ?: return
        for (a in Action.entries) Prefs.setKeyFor(ctx, a, p.optInt(a.name, 0))
        Prefs.setLearning(ctx, null)
    }

    fun deleteProfile(ctx: Context, name: String) =
        Prefs.setKeyProfiles(ctx, profiles(ctx).apply { remove(name) }.toString())
}
