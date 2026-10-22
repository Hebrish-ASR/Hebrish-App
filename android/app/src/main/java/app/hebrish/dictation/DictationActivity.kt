package app.hebrish.dictation

import app.hebrish.core.OutputStyle
import app.hebrish.core.Recorder

/** How takes behave in both the keyboard and the floating mic: long dictation, type as you go, ALL CAPS. */
class DictationActivity : Page() {
    override fun build() {
        heading(R.string.dictation_long_title)
        text(getString(R.string.dictation_long, Recorder.MAX_SEGMENTED_SECONDS / 60))
        switch(R.string.dictation_type_as_you_go, { Prefs.typeAsYouGo(this) }, { Prefs.setTypeAsYouGo(this, it) })
        small(R.string.dictation_type_as_you_go_hint)
        switch(R.string.dictation_all_caps, { OutputStyle.allCaps(this) }, { OutputStyle.setAllCaps(this, it) })
        small(R.string.dictation_all_caps_hint)

        heading(R.string.dictation_speed_title)
        text(R.string.dictation_speed)

        heading(R.string.dictation_missed_title)
        text(R.string.dictation_missed)
    }
}
