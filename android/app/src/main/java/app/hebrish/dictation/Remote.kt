package app.hebrish.dictation

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.view.KeyEvent

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
 * press the service sees is bound to that action.
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
}
