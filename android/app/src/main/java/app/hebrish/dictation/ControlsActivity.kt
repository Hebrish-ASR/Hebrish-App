package app.hebrish.dictation

import android.content.SharedPreferences
import android.media.AudioDeviceCallback
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.text.InputType
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.TextView

/**
 * Sound, microphone and buttons (0.6.0): pips and buzzes for start / stop / retake / discard
 * ([Feedback]), which microphone takes use ([Mic]; Automatic = Bluetooth first), and control
 * from outside the app ([Remote]): keys bound per action, learned from the next key press,
 * and the broadcast intents other apps can send. Intent reference: docs/external-control.md.
 * 1.004: an on/off switch for bound keys (off: none are taken, bindings kept), Clear all, and
 * saved sets of bindings by name (Use replaces the current ones; [Remote.saveProfile]).
 */
class ControlsActivity : Page(), SharedPreferences.OnSharedPreferenceChangeListener {
    private lateinit var mics: RadioGroup
    private lateinit var micNow: TextView
    private lateinit var bubbleWarning: TextView
    private val keyLabels = mutableMapOf<Remote.Action, TextView>()
    private var profileList: LinearLayout? = null
    private var profileName: EditText? = null
    private val micKeys = mutableMapOf<Int, String>()
    private val am by lazy { getSystemService(AudioManager::class.java) }
    private val devices = object : AudioDeviceCallback() {
        override fun onAudioDevicesAdded(added: Array<out AudioDeviceInfo>) = renderMics()
        override fun onAudioDevicesRemoved(removed: Array<out AudioDeviceInfo>) = renderMics()
    }

    override fun build() {
        heading(R.string.controls_sound)
        switch(R.string.controls_beeps, { Prefs.beeps(this) }, { Prefs.setBeeps(this, it) })
        small(R.string.controls_beeps_hint)
        row().also { r ->
            button(R.string.controls_test_start, r) { Feedback.preview(Feedback.Cue.START) }
            button(R.string.controls_test_stop, r) { Feedback.preview(Feedback.Cue.STOP) }
            button(R.string.controls_test_retake, r) { Feedback.preview(Feedback.Cue.RESTART) }
        }
        switch(R.string.controls_vibrate, { Prefs.vibrate(this) }, { Prefs.setVibrate(this, it) })

        heading(R.string.controls_mic)
        text(R.string.controls_mic_body)
        mics = RadioGroup(this)
        column.addView(mics)
        mics.setOnCheckedChangeListener { _, id -> micKeys[id]?.let { if (it != Prefs.micChoice(this)) Prefs.setMicChoice(this, it) } }
        micNow = text(top = 8)
        small(R.string.controls_mic_hint)

        heading(R.string.controls_buttons)
        text(R.string.controls_buttons_body)
        bubbleWarning = text(R.string.controls_needs_bubble, top = 8)
        // The Play build can't see hardware keys (no flagRequestFilterKeyEvents): intents only there.
        if (Channel.hardwareKeys) {
            switch(R.string.controls_keys_on, { Prefs.keysOn(this) }, { Prefs.setKeysOn(this, it) })
            small(R.string.controls_keys_on_hint)
        }
        if (Channel.hardwareKeys) for (a in Remote.Action.entries) {
            subheading(actionName(a))
            val r = row()
            keyLabels[a] = TextView(this).apply { setPadding(0, 0, dp(12), 0) }.also {
                r.addView(it, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            }
            button(R.string.controls_learn, r) { Prefs.setLearning(this, a) }
            button(R.string.controls_clear, r) { Prefs.setKeyFor(this, a, 0); if (Prefs.learning(this) == a.name) Prefs.setLearning(this, null) }
        }
        if (Channel.hardwareKeys) {
            button(R.string.controls_clear_all) { Remote.clearAll(this) }
            subheading(R.string.controls_profiles)
            small(R.string.controls_profiles_body)
            val r = row()
            profileName = EditText(this).apply {
                setHint(R.string.controls_profile_name)
                isSingleLine = true
                inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
            }.also { r.addView(it, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)) }
            button(R.string.controls_profile_save, r) { saveProfile() }
            profileList = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }.also { column.addView(it) }
            small(R.string.controls_buttons_hint)
        }

        heading(R.string.controls_intents)
        text(R.string.controls_intents_body)
        text(Remote.Action.entries.joinToString("\n") { it.intent }).setTextIsSelectable(true)
        small(R.string.controls_intents_hint)
    }

    override fun onResume() {
        super.onResume()
        Prefs.listen(this, this)
        am.registerAudioDeviceCallback(devices, null)
        render()
    }

    override fun onPause() {
        super.onPause()
        Prefs.unlisten(this, this)
        am.unregisterAudioDeviceCallback(devices)
        // Leaving the screen ends learning, so a key isn't grabbed later by surprise.
        if (Prefs.learning(this) != null) Prefs.setLearning(this, null)
    }

    override fun onSharedPreferenceChanged(sp: SharedPreferences?, key: String?) {
        if (key?.startsWith("key_") == true || key == "mic_choice") render()
    }

    private fun actionName(a: Remote.Action) = when (a) {
        Remote.Action.TOGGLE -> R.string.action_toggle
        Remote.Action.START -> R.string.action_start
        Remote.Action.STOP -> R.string.action_stop
        Remote.Action.RESTART -> R.string.action_restart
        Remote.Action.PAUSE -> R.string.action_pause
        Remote.Action.DISCARD -> R.string.action_discard
    }

    private fun render() {
        renderMics()
        val learning = Prefs.learning(this)
        for ((a, label) in keyLabels) {
            val code = Prefs.keyFor(this, a)
            label.text = when {
                learning == a.name -> getString(R.string.controls_press_key)
                code != 0 -> getString(R.string.controls_key, Remote.keyName(code))
                else -> getString(R.string.controls_no_key)
            }
        }
        bubbleWarning.visibility = if (Setup.bubbleOn(this)) View.GONE else View.VISIBLE
        renderProfiles()
    }

    private fun saveProfile() {
        val field = profileName ?: return
        val name = field.text.toString().trim()
        // Up to 1.008 Save with no name did nothing at all.
        if (name.isEmpty()) { field.error = getString(R.string.controls_profile_need_name); return }
        if (Remote.Action.entries.all { Prefs.keyFor(this, it) == 0 }) return toast(getString(R.string.controls_profile_empty))
        Remote.saveProfile(this, name)
        field.setText("")
        toast(getString(R.string.controls_profile_saved, name))
    }

    /** One line per saved set: its name and keys, then Use and Delete. */
    private fun renderProfiles() {
        val list = profileList ?: return
        list.removeAllViews()
        val names = Remote.profileNames(this)
        if (names.isEmpty()) text(getString(R.string.controls_profiles_none), list, 8)
        for (name in names) {
            val summary = Remote.profileSummary(this, name) { getString(actionName(it)) }.ifEmpty { getString(R.string.controls_no_key) }
            text("$name\n$summary", list, 12)
            val r = row(list)
            button(R.string.controls_profile_use, r) {
                Remote.useProfile(this, name)
                toast(getString(R.string.controls_profile_used, name))
            }
            button(R.string.controls_profile_delete, r) { Remote.deleteProfile(this, name) }
        }
    }

    private fun toast(msg: String) = android.widget.Toast.makeText(this, msg, android.widget.Toast.LENGTH_SHORT).show()

    /** Automatic first, then every connected mic; a chosen mic that is disconnected stays listed. */
    private fun renderMics() {
        mics.setOnCheckedChangeListener(null)
        mics.removeAllViews()
        micKeys.clear()
        val choice = Prefs.micChoice(this)
        fun add(key: String, label: String) {
            val id = View.generateViewId()
            micKeys[id] = key
            mics.addView(RadioButton(this).apply { this.id = id; text = label })
            if (key == choice) mics.check(id)
        }
        add(Mic.AUTO, getString(R.string.controls_mic_auto))
        val inputs = Mic.inputs(this)
        for (d in inputs) add(Mic.key(d), Mic.label(this, d))
        if (choice != Mic.AUTO && inputs.none { Mic.key(it) == choice }) add(choice, getString(R.string.controls_mic_gone, choice.substringAfter(':')))
        mics.setOnCheckedChangeListener { _, id -> micKeys[id]?.let { if (it != Prefs.micChoice(this)) Prefs.setMicChoice(this, it) } }
        micNow.text = getString(R.string.controls_mic_next, Mic.label(this, Mic.preferred(this)))
    }
}
