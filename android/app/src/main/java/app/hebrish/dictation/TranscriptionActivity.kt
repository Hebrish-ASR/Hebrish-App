package app.hebrish.dictation

import app.hebrish.core.*
import android.Manifest
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.text.format.DateFormat
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import java.io.File
import java.util.concurrent.Executors

/**
 * Transcription Mode (R-2026-10-24-5; desktop: the Transcription tab): record a long take with
 * [Tape] (its own mic, digital gain, a level meter that can be hidden, Record / Pause / Retake /
 * Stop / Transcribe), then transcribe it here in segments with [TakeDecoder].
 *
 * The recording itself is [Recording] (process-wide), so it can outlive this screen. With
 * background recording on (Setup's optional step, `Prefs.tmBackground` plus notifications on
 * Android 13+; I-15) [TranscriptionService] keeps it going with the screen off or another app in
 * front. Without it, the screen is kept on while recording and leaving it pauses (Android only
 * lets an app record in the foreground otherwise); the file stays and Resume carries on in it.
 * A recording not transcribed (the app was closed, the transcription failed or was cancelled) is
 * offered again at the top.
 *
 * Paragraphs (B-44a, D-2026-10-24-09, `shared/paragraphs.md`): None, Time-based (a break about
 * every [PARAGRAPH_S] of audio, at a segment boundary) or Paragraph model ([ParagraphModel], run
 * once on the whole take when it is transcribed). The take's pieces and their time-based breaks
 * are kept ([Take]), so changing the setting re-flows the transcript as long as the box still
 * holds exactly what the app wrote ([shown]); text the user edited is never replaced.
 *
 * Clean up (B-40a; desktop B-40): with a clean-up model downloaded ([CleanupStore]: stock S1-mini
 * by Superwhisper, or Daniel's fine-tune of it) and the switch on, the finished take is cleaned
 * once ([Cleanup], [CleanupModel]) on the same worker. Its paragraphs replace the Paragraphs
 * setting, which is used again if clean-up fails; failed parts keep their raw text.
 *
 * Save (B-74a; desktop B-74/B-78): writes the box as Markdown into the transcripts folder the user
 * picked ([TranscriptFolder], [Transcripts]): front matter, title, date, credit line, plus the raw
 * transcription and a JSON manifest. [Doc] is what Save needs about the transcript in the box.
 * With the title model downloaded and *Give saved transcripts a title* on (B-75a, [Titles]) the
 * title is written first on [paraWorker]; any failure saves without one.
 */
class TranscriptionActivity : Page() {
    private val ui = Handler(Looper.getMainLooper())
    private val tape get() = Recording.tape
    private var held: File?                  // stopped, waiting for Transcribe
        get() = Recording.held
        set(v) { Recording.held = v }
    private var leftover: File? = null
    private var decoding: File? = null
    @Volatile private var cancelled = false
    private var decoder: TakeDecoder? = null
    private var meterOn = true

    /** The take in the box: its pieces as decoded, each with its time-based break, so it can be re-flowed. */
    private class Take(val base: String) {
        val pieces = ArrayList<String>()
        val breaks = ArrayList<Boolean>()
        /** Decoding is over (the last piece is in). */
        var done = false
        /** The paragraph model's text for the take, once it has run. */
        var modelText: String? = null
        /** The paragraph model is running on it. */
        var modelRunning = false
        /** The clean-up model's text for the take, once it has cleaned at least one part. */
        var cleanText: String? = null
        /** The clean-up model is running on it. */
        var cleanRunning = false
    }
    private var take: Take? = null
    /** What the app last put in the box; the box is re-flowed or replaced only while it still holds exactly this. */
    private var shown: String? = null
    private var mode = ParagraphMode.TIME
    /** Runs the paragraph model, one job at a time; owns [paraModel]. */
    private val paraWorker = Executors.newSingleThreadExecutor()
    private var paraModel: ParagraphModel? = null
    private var paraModelDir: File? = null
    /** Clean up is switched on; [cleanOk]: this phone can run a clean-up model the catalogue offers. */
    private var cleanOn = false
    private var cleanOk = false
    /** The loaded clean-up model, kept between takes. [paraWorker] only. */
    private var cleanModel: CleanupModel? = null
    private var cleanModelFile: File? = null

    /**
     * The transcript in the box, for Save (desktop `_doc`): its time (the first part's), each
     * part's raw text (before clean-up and edits), speech models, audio seconds, source, clean-up
     * models, and what was last saved. Reset by Clear and by a take that starts in an empty box.
     */
    private class Doc(val whenMs: Long) {
        val raw = ArrayList<String>()
        val models = LinkedHashSet<String>()
        val cleanup = LinkedHashSet<String>()
        var seconds = 0.0
        var recorded = false
        var savedText: String? = null
        var savedPath: String? = null
    }
    private var doc: Doc? = null
    private var saving = false
    /** Save was pressed before a folder was chosen: save once the picker answers. */
    private var saveAfterPick = false

    private lateinit var leftoverBox: LinearLayout
    private lateinit var leftoverText: TextView
    private lateinit var micLine: TextView
    private lateinit var gainLabel: TextView
    private lateinit var meter: Meter
    private lateinit var meterText: TextView
    private lateinit var btnRec: Button
    private lateinit var btnRetake: Button
    private lateinit var btnStop: Button
    private lateinit var btnGo: Button
    private lateinit var btnDiscard: Button
    private lateinit var elapsed: TextView
    private lateinit var status: TextView
    private lateinit var progress: ProgressBar
    private lateinit var btnCancel: Button
    private lateinit var text: EditText
    private lateinit var paraLine: TextView
    private lateinit var paraProgress: ProgressBar
    private lateinit var cleanBox: LinearLayout
    private lateinit var cleanLine: TextView
    private lateinit var cleanProgress: ProgressBar
    private lateinit var saveLine: TextView
    private lateinit var titleBox: LinearLayout
    private lateinit var titleLine: TextView
    private lateinit var titleProgress: ProgressBar

    private val tick = object : Runnable {
        override fun run() {
            renderLevel()
            if (tape.active) {
                elapsed.text = (if (tape.paused) "❚❚ " else "● ") + clock(tape.seconds.toFloat())
                ui.postDelayed(this, 80)
            }
        }
    }

    override fun build() {
        Recording.app = applicationContext
        text(R.string.tm_intro, top = 8)

        leftoverBox = group().apply { setPadding(dp(14), dp(10), dp(14), dp(10)) }
        leftoverText = text(parent = leftoverBox, top = 0)
        row(leftoverBox).also { r ->
            button(R.string.tm_leftover_go, r) { leftover?.let { transcribe(it) } }
            button(R.string.tm_delete, r) { deleteLeftover() }
        }

        heading(R.string.tm_record)
        micLine = text(top = 4)
        button(R.string.tm_mic_change) { changeMic() }

        gainLabel = text(top = 12)
        slider(Tape.GAIN_MIN_DB, Tape.GAIN_MAX_DB, Prefs.tmGainDb(this), gainLabel,
            { getString(R.string.tm_gain, if (it == 0) "0 dB" else "%+d dB".format(it)) }) {
            Prefs.setTmGainDb(this, it)
            tape.gainDb = it.toFloat()
        }
        tape.gainDb = Prefs.tmGainDb(this).toFloat()

        meterOn = Prefs.tmShowMeter(this)
        switch(R.string.tm_show_level, { meterOn }, { on ->
            meterOn = on
            Prefs.setTmShowMeter(this, on)
            meter.visibility = if (on) View.VISIBLE else View.GONE
            meterText.visibility = meter.visibility
        })
        switch(R.string.tm_background, { Recording.background(this) }, { on -> setBackground(on) })
        // The level is read out by meterText below; the bars themselves are decorative.
        meter = Meter(this).apply { importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO }
        column.addView(meter, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(18)).apply { topMargin = dp(6) })
        meterText = text(top = 4).apply { setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f) }
        meter.visibility = if (meterOn) View.VISIBLE else View.GONE
        meterText.visibility = meter.visibility

        val controls = row().apply { (layoutParams as LinearLayout.LayoutParams).topMargin = dp(12) }
        btnRec = button(R.string.tm_record, controls) { recOrPause() }
        btnRetake = button(R.string.tm_retake, controls) { confirmDrop { tape.discard(); dropHeld(); Recording.changed(); recOrPause() } }
        btnStop = button(R.string.tm_stop, controls) { stopTape() }
        val controls2 = row().apply { (layoutParams as LinearLayout.LayoutParams).topMargin = dp(4) }
        btnGo = primary(button(R.string.tm_transcribe, controls2) { transcribeTape() })
        btnDiscard = button(R.string.tm_discard, controls2) { confirmDrop { tape.discard(); dropHeld(); Recording.changed(); sync() } }
        // Elapsed time: small and grey at the end of the controls, there when you look for it.
        elapsed = TextView(this).apply {
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            setTextColor(getColor(R.color.brand_muted))
            gravity = Gravity.END or Gravity.CENTER_VERTICAL
        }
        controls2.addView(elapsed, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f))

        status = text(top = 10).apply { setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f); setTextColor(getColor(R.color.brand_muted)) }
        val prow = row()
        progress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply { max = 1000 }
        prow.addView(progress, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply { gravity = Gravity.CENTER_VERTICAL })
        btnCancel = button(R.string.tm_cancel, prow) { cancelled = true; decoder?.cancel() }

        // Paragraphs (B-44a): one line with the current choice, Change opens the three values.
        mode = ParagraphMode.get(this)
        val pline = row().apply { gravity = Gravity.CENTER_VERTICAL; (layoutParams as LinearLayout.LayoutParams).topMargin = dp(10) }
        paraLine = TextView(this).apply { setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f) }
        pline.addView(paraLine, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        button(R.string.tm_para_change, pline) { chooseParagraphs() }
        paraProgress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply { max = 1000 }
        column.addView(paraProgress, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))

        // Clean up (B-40a): a switch and the chosen model, only on phones that can run one.
        cleanOn = Prefs.tmCleanup(this)
        cleanOk = CleanupStore.available(this)
        cleanBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        column.addView(cleanBox, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        switch(R.string.tm_cleanup, { cleanOn }, { on -> setCleanup(on) }, cleanBox)
        val cline = row(cleanBox).apply { gravity = Gravity.CENTER_VERTICAL }
        cleanLine = TextView(this).apply { setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f); setTextColor(getColor(R.color.brand_muted)) }
        cline.addView(cleanLine, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        button(R.string.tm_para_change, cline) { chooseCleanup() }
        cleanProgress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply { max = 1000 }
        cleanBox.addView(cleanProgress, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))

        text = EditText(this).apply {
            setHint(R.string.tm_text_hint)
            gravity = Gravity.TOP or Gravity.START
            minLines = 8
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE or
                android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
            importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO
        }
        column.addView(text, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(12) })
        row().also { r ->
            primary(button(R.string.tm_save, r) { save() })
            button(R.string.try_copy, r) { TextOut.copy(this, text.text) }
            button(R.string.try_share, r) { TextOut.share(this, text.text) }
            button(R.string.try_clear, r) { text.setText(""); doc = null }
        }

        // Save (B-74a) and titles (B-75a): where Save writes, and the title switch when the phone can run the model.
        val sline = row().apply { gravity = Gravity.CENTER_VERTICAL; (layoutParams as LinearLayout.LayoutParams).topMargin = dp(6) }
        saveLine = TextView(this).apply { setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f); setTextColor(getColor(R.color.brand_muted)) }
        sline.addView(saveLine, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        button(R.string.tm_folder, sline) { pickFolder() }
        titleBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        column.addView(titleBox, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        switch(R.string.tm_titles, { Prefs.titles(this) }, { on -> setTitles(on) }, titleBox)
        titleLine = TextView(this).apply { setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f); setTextColor(getColor(R.color.brand_muted)) }
        titleBox.addView(titleLine)
        titleProgress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply { max = 1000 }
        titleBox.addView(titleProgress, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))

        showMic()
        showLeftover()
        showParagraphs()
        showCleanup()
        showSave()
        sync()
    }

    override fun onResume() {
        super.onResume()
        Recording.listener = { refresh() }
        ParagraphStore.listener = { onParagraphDownload(it) }
        CleanupStore.listener = { onCleanupDownload(it) }
        cleanOk = CleanupStore.available(this)
        refresh()
        showParagraphs()
        showCleanup()
        showSave()
    }

    override fun onPause() {
        super.onPause()
        Recording.listener = null
        ParagraphStore.listener = null
        CleanupStore.listener = null
        // Without background recording the mic can't stay open off-screen.
        if (tape.active && !tape.paused && !Recording.background(this)) {
            tape.pause()
            Mic.release(this)
            Recording.changed()
            Recording.notice = R.string.tm_paused_left
        }
    }

    override fun onDestroy() {
        // Recording in the background carries on; otherwise the file is closed and offered next time.
        if (!(tape.active && Recording.background(this))) {
            if (tape.active) Recording.stop(this)
        }
        cancelled = true
        decoder?.cancel()
        // The recording can outlive the screen (background on): stop redrawing views that are gone.
        ui.removeCallbacks(tick)
        // A paragraph run still queued finishes (and records History); then the session is closed.
        paraWorker.execute { closeModel(); closeCleaner() }
        paraWorker.shutdown()
        super.onDestroy()
    }

    /** Redraw from [Recording] (changed from the notification, or while this screen was away). */
    private fun refresh() {
        if (Recording.notice != 0) { status.setText(Recording.notice); Recording.notice = 0 }
        showMic()
        sync()
    }

    /**
     * Background recording on or off. On needs notifications on Android 13+ (for the controls in
     * the notification); asked here or in Setup.
     */
    private fun setBackground(on: Boolean) {
        Prefs.setTmBackground(this, on)
        if (on && !Recording.notificationsAllowed(this)) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_NOTIFY)
        Recording.changed()
    }

    // -- mic ---------------------------------------------------------------------------
    private fun device() = Mic.preferred(this, Prefs.tmMic(this))

    private fun showMic() {
        val d = if (tape.active && !tape.paused) tape.routedDevice ?: device() else device()
        val name = Mic.label(this, d)
        micLine.text = getString(R.string.tm_mic, if (Prefs.tmMic(this) == Mic.AUTO) getString(R.string.tm_mic_auto, name) else name)
    }

    /** Automatic first, then each connected mic. Switching while recording carries on in the same file. */
    private fun changeMic() {
        val inputs = Mic.inputs(this)
        val keys = listOf(Mic.AUTO) + inputs.map { Mic.key(it) }
        val names = listOf(getString(R.string.tm_mic_auto, Mic.label(this, Mic.preferred(this, Mic.AUTO)))) + inputs.map { Mic.label(this, it) }
        if (inputs.size < 2 && names.size < 3) Toast.makeText(this, R.string.tm_mic_none, Toast.LENGTH_SHORT).show()
        AlertDialog.Builder(this)
            .setTitle(R.string.tm_mic_change)
            .setSingleChoiceItems(names.toTypedArray(), keys.indexOf(Prefs.tmMic(this)).coerceAtLeast(0)) { dlg, i ->
                Prefs.setTmMic(this, keys[i])
                dlg.dismiss()
                val d = device()
                if (tape.active) {
                    Mic.release(this)
                    Mic.routeFor(this, d)
                    try { tape.switchTo(d) } catch (e: Exception) { tape.pause(); status.setText(R.string.tm_mic_lost) }
                }
                showMic()
                sync()
            }
            .show()
    }

    // -- recorder ----------------------------------------------------------------------
    private fun recOrPause() {
        when {
            tape.active && tape.paused -> {
                val d = device()
                tape.preferredDevice = d
                Mic.routeFor(this, d)
                // Up to 1.008 the error was cleared on the next line, so a failed resume showed nothing.
                try { tape.resume(); status.text = "" } catch (e: Exception) { status.text = getString(R.string.ime_mic_error, e.message ?: "?") }
            }
            tape.active -> { tape.pause(); Mic.release(this) }
            else -> {
                if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                    requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQ_MIC)
                    return
                }
                val d = device()
                tape.preferredDevice = d
                Mic.routeFor(this, d)
                try {
                    tape.start(this)
                } catch (e: Exception) {
                    Mic.release(this)
                    status.text = getString(R.string.ime_mic_error, e.message ?: "?")
                    return
                }
                status.text = ""
            }
        }
        showMic()
        Recording.changed()
        sync()
    }

    /** Read on every redraw ([sync]), so from the file's size: Tape.recover rewrote the header each time up to 1.008. */
    private fun heldSeconds(): Float = held?.takeIf { it.exists() }?.let { Tape.seconds(it) } ?: 0f

    private fun confirmDrop(then: () -> Unit) {
        val s = if (tape.active) tape.seconds.toFloat() else heldSeconds()
        if (s < CONFIRM_DROP_S) return then()
        AlertDialog.Builder(this)
            .setMessage(getString(R.string.tm_confirm_drop, clock(s)))
            .setPositiveButton(R.string.tm_discard) { _, _ -> then() }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun dropHeld() {
        held?.delete()
        held = null
        Mic.release(this)
    }

    private fun stopTape() {
        Recording.stop(this)
        if (held != null) status.text = getString(R.string.tm_stopped, clock(heldSeconds()))
        sync()
    }

    private fun transcribeTape() {
        if (tape.active) Recording.stop(this)
        sync()
        held?.let { transcribe(it) }
    }

    /** Buttons for the state: idle, recording, paused, stopped (held), or transcribing. */
    private fun sync() {
        val busy = decoding != null
        val rec = tape.active
        val isHeld = held != null && !rec
        btnRec.setText(if (rec && tape.paused) R.string.tm_resume else if (rec) R.string.tm_pause else R.string.tm_record)
        btnRec.isEnabled = !busy && !isHeld
        btnRetake.isEnabled = !busy && (rec || isHeld)
        btnStop.isEnabled = rec
        btnGo.isEnabled = !busy && (rec || isHeld)
        btnDiscard.isEnabled = !busy && (rec || isHeld)
        for (b in listOf(btnRec, btnRetake, btnStop, btnGo, btnDiscard)) b.alpha = if (b.isEnabled) 1f else 0.45f
        progress.visibility = if (busy) View.VISIBLE else View.GONE
        btnCancel.visibility = progress.visibility
        if (rec && !tape.paused && !Recording.background(this)) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        ui.removeCallbacks(tick)
        if (rec) ui.post(tick) else {
            elapsed.text = if (isHeld) "■ " + clock(heldSeconds()) else ""
            renderLevel()
        }
    }

    private fun renderLevel() {
        if (!meterOn) return
        val live = tape.active && !tape.paused
        val clipping = live && tape.clippedAt > 0 && SystemClock.elapsedRealtime() - tape.clippedAt < CLIP_HOLD_MS
        val db = if (live) dbfs(tape.rms) else FLOOR_DB
        meter.set(db, if (live) dbfs(tape.peak) else FLOOR_DB, clipping)
        val (res, col) = when {
            !live -> R.string.tm_level_idle to getColor(R.color.brand_muted)
            clipping -> R.string.tm_level_clip to CLIP_RED
            db < QUIET_DB -> R.string.tm_level_quiet to getColor(R.color.brand_muted)
            db <= LOUD_DB -> R.string.tm_level_good to GOOD_GREEN
            else -> R.string.tm_level_loud to LOUD_AMBER
        }
        meterText.setText(res)
        meterText.setTextColor(col)
    }

    // -- leftovers ---------------------------------------------------------------------
    private fun showLeftover() {
        val mine = setOf(held, decoding, tape.file)
        leftover = Tape.leftovers(this).firstOrNull { it !in mine }
        leftoverBox.visibility = if (leftover == null) View.GONE else View.VISIBLE
        leftover?.let {
            val whenText = DateFormat.format("yyyy-MM-dd HH:mm", it.lastModified())
            leftoverText.text = getString(R.string.tm_leftover, whenText, clock(Tape.recover(it)))
        }
    }

    private fun deleteLeftover() {
        val f = leftover ?: return
        AlertDialog.Builder(this)
            .setMessage(getString(R.string.tm_confirm_drop, clock(Tape.seconds(f))))
            .setPositiveButton(R.string.tm_delete) { _, _ -> f.delete(); showLeftover() }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    // -- transcription -----------------------------------------------------------------
    /**
     * Reads [f] back in segments ([Tape.segments]) and decodes them in order; a paragraph about
     * every [PARAGRAPH_S] of audio, as on desktop. The reader waits while the decoder is more than
     * two segments behind, so memory stays small however long the recording is.
     */
    private fun transcribe(f: File) {
        if (decoding != null) return
        val total = Tape.recover(f)
        lastTotal = total
        decoding = f
        cancelled = false
        take = Take(text.text.toString())
        shown = text.text.toString()
        val ends = java.util.Collections.synchronizedList(ArrayList<Long>())   // cumulative samples per segment
        var paraAt = -1L
        var fed = 0L
        val d = TakeDecoder(this) { said ->
            val k = (decoderRef()?.segmentsDecoded ?: 1) - 1
            val at = ends.getOrNull(k) ?: 0L
            val brk = paraAt < 0 || at - paraAt >= PARAGRAPH_S * Transcriber.SAMPLE_RATE
            if (brk) paraAt = at
            ui.post { insert(said, brk) }
        }
        decoder = d
        status.text = getString(R.string.tm_transcribing, 0)
        progress.progress = 0
        showLeftover()
        sync()
        Thread {
            val tail = runCatching {
                Tape.segments(f, { cancelled }) { seg ->
                    fed += seg.size
                    ends.add(fed)
                    d.add(seg)
                    val pct = (fed / Transcriber.SAMPLE_RATE.toFloat() / total.coerceAtLeast(1f)).coerceAtMost(1f)
                    ui.post { progress.progress = (pct * 1000).toInt(); status.text = getString(R.string.tm_transcribing, (pct * 100).toInt()) }
                    while (!cancelled && d.segmentsQueued - d.segmentsDecoded > 2) Thread.sleep(50)
                }
            }
            val samples = tail.getOrNull()
            if (samples == null || cancelled) {
                ui.post { finished(f, tail.exceptionOrNull()) }
                return@Thread
            }
            val end = fed + samples.size
            d.finish(samples) { result ->
                val brk = paraAt < 0 || end - paraAt >= PARAGRAPH_S * Transcriber.SAMPLE_RATE
                ui.post {
                    result.onSuccess { last -> if (last.isNotBlank()) insert(last, brk) }
                    val t = take
                    finished(f, result.exceptionOrNull())
                    if (result.isSuccess && t != null) taken(t, d.stats())
                }
            }
        }.start()
    }

    private fun decoderRef() = decoder

    private fun finished(f: File, err: Throwable?) {
        decoder = null
        decoding = null
        if (held == f) held = null
        when {
            cancelled -> status.setText(R.string.tm_cancelled)
            err != null -> status.text = getString(R.string.try_failed, err.message ?: "?")
            else -> {
                f.delete()                       // the transcript is in History now
                status.text = getString(R.string.tm_done, clock(lastTotal))
            }
        }
        showLeftover()
        sync()
    }

    private var lastTotal = 0f

    /** A decoded piece: kept with its time-based break, then the box is redrawn in the current setting. */
    private fun insert(said: String, paragraph: Boolean) {
        val t = take ?: return
        val unedited = unedited()
        t.pieces.add(said)
        t.breaks.add(paragraph)
        if (unedited) return show(compose(t, mode))
        // Edited meanwhile: add at the end as before 1.002, and stop re-flowing this take.
        shown = null
        val e = text.text
        val sep = if (e.isEmpty()) "" else if (paragraph && mode == ParagraphMode.TIME) "\n\n" else null
        e.append(if (sep != null) sep + said.trimStart() else TakeDecoder.join(e, said))
    }

    // -- paragraphs (B-44a) ------------------------------------------------------------
    private fun unedited() = shown != null && text.text.toString() == shown

    /** Puts [s] in the box: appended when it only adds to what is there (keeps the cursor and scroll), else replaced. */
    private fun show(s: String) {
        val cur = text.text.toString()
        if (s != cur) {
            if (s.startsWith(cur)) text.text.append(s, cur.length, s.length) else text.setText(s)
        }
        shown = s
    }

    /** The take in [m], after whatever was in the box when it started (a blank line between). */
    private fun compose(t: Take, m: ParagraphMode): String {
        val body = flow(t, m)
        return if (t.base.isEmpty()) body else if (body.isEmpty()) t.base else t.base + "\n\n" + body
    }

    /**
     * The take's text in [m]. Paragraph model: the model's text once it has run; one block while
     * decoding or while it runs; Time-based when it is missing or failed (the spec's fallback).
     */
    private fun flow(t: Take, m: ParagraphMode): String = if (cleaning() && t.cleanText != null) t.cleanText!! else when (m) {
        ParagraphMode.NONE -> joined(t, false)
        ParagraphMode.TIME -> joined(t, true)
        ParagraphMode.MODEL -> t.modelText
            ?: if (t.modelRunning || (!t.done && ParagraphStore.isReady(this))) joined(t, false) else joined(t, true)
    }

    /**
     * The pieces joined as decoding hands them over ([TakeDecoder.join]); with [breaks], a blank
     * line before each piece that starts a time-based paragraph. A held-back full stop at the start
     * of such a piece (". Next") stays with the paragraph before.
     */
    private fun joined(t: Take, breaks: Boolean): String {
        val sb = StringBuilder()
        for ((i, p) in t.pieces.withIndex()) {
            if (sb.isEmpty()) { sb.append(p.trimStart()); continue }
            if (breaks && t.breaks[i]) {
                val lead = p.takeWhile { it in ".,;:?!" }
                val rest = p.drop(lead.length).trimStart()
                sb.append(lead)
                if (rest.isNotEmpty()) sb.append("\n\n").append(rest)
            } else sb.append(TakeDecoder.join(sb, p))
        }
        return sb.toString()
    }

    /** Transcription finished: Paragraph model runs now; otherwise History gets the take as shown. */
    private fun taken(t: Take, stats: TakeDecoder.Stats) {
        t.done = true
        noteDoc(t, stats)
        if (cleaning() && CleanupStore.readyFile(this) != null) return runCleanup(t, stats)
        paragraphsFor(t, stats)
    }

    /** The Paragraphs setting for a finished take: clean-up is off or failed. */
    private fun paragraphsFor(t: Take, stats: TakeDecoder.Stats?) {
        if (stats == null) {
            if (mode == ParagraphMode.MODEL && t.modelText == null && !t.modelRunning) runModel(t, null)
            else if (unedited()) show(compose(t, mode))
            return
        }
        if (mode == ParagraphMode.MODEL) runModel(t, stats)
        else History.record(this, flow(t, mode), stats, History.RECORD)
        if (mode == ParagraphMode.MODEL && !ParagraphStore.isReady(this)) {
            if (unedited()) show(compose(t, mode))
            status.text = getString(R.string.tm_para_not_installed)
        }
    }

    /**
     * Runs the paragraph model on [t] (on [paraWorker]), then applies it if the box is unedited.
     * [stats] set: the take has just finished and goes into History once its text is final.
     */
    private fun runModel(t: Take, stats: TakeDecoder.Stats?) {
        val inst = ParagraphStore.installed(this)
        val flat = joined(t, false)
        if (inst == null || !ParagraphStore.isReady(this) || flat.isBlank()) {
            if (flat.isBlank() && inst != null) t.modelText = flat
            if (stats != null) History.record(this, flow(t, ParagraphMode.MODEL), stats, History.RECORD)
            return
        }
        val dir = ParagraphStore.dir(this, inst)
        val threshold = ParagraphStore.threshold(this, inst)
        val before = status.text
        t.modelRunning = true
        status.text = getString(R.string.tm_para_running)
        val app = applicationContext
        paraWorker.execute {
            val r = runCatching { model(dir, threshold).apply(flat) }
            if (r.isFailure) closeModel()
            ui.post {
                t.modelRunning = false
                r.onSuccess { t.modelText = it }
                val current = take === t && mode == ParagraphMode.MODEL
                val applied = current && unedited()
                if (applied) show(compose(t, ParagraphMode.MODEL))
                if (stats != null) History.record(app, if (applied || !current) flow(t, ParagraphMode.MODEL) else flat, stats, History.RECORD)
                if (current) status.text = when {
                    r.isFailure -> getString(R.string.tm_para_failed, r.exceptionOrNull()?.message ?: "?")
                    !applied -> getString(R.string.tm_para_edited)
                    else -> before
                }
            }
        }
    }

    /** The kept ORT session for [dir], created on first use. [paraWorker] only. */
    private fun model(dir: File, threshold: Double): ParagraphModel {
        paraModel?.takeIf { paraModelDir == dir && it.threshold == threshold }?.let { return it }
        closeModel()
        return ParagraphModel(dir, threshold, Transcriber.threads).also { paraModel = it; paraModelDir = dir }
    }

    /** [paraWorker] only. */
    private fun closeModel() {
        runCatching { paraModel?.close() }
        paraModel = null
        paraModelDir = null
    }

    /** The setting changed, or the model arrived: re-flow the current take if the box is still what the app wrote. */
    private fun reflow() {
        val t = take ?: return
        if (t.pieces.isEmpty()) return
        if (!unedited()) { status.setText(R.string.tm_para_edited); return }
        // Cleaned: the clean-up model's paragraphs stand; the setting applies again if clean-up is turned off.
        if (cleaning() && t.cleanText != null) return show(compose(t, mode))
        // The model's first run on this take: the box keeps its current text until the result.
        if (mode == ParagraphMode.MODEL && t.done && t.modelText == null && !t.modelRunning && ParagraphStore.isReady(this)) runModel(t, null)
        else if (!t.modelRunning || mode != ParagraphMode.MODEL) show(compose(t, mode))
    }

    // -- clean up (B-40a) ---------------------------------------------------------------
    private fun cleaning() = cleanOn && cleanOk

    /**
     * Cleans [t] with the chosen clean-up model (on [paraWorker]), then applies it if the box is
     * unedited. Nothing cleaned (no model, an error, every part kept raw): the Paragraphs setting
     * instead. [stats] set: the take has just finished and goes into History once its text is final.
     */
    private fun runCleanup(t: Take, stats: TakeDecoder.Stats?) {
        val gguf = CleanupStore.readyFile(this)
        val flat = joined(t, false)
        if (gguf == null || flat.isBlank()) return paragraphsFor(t, stats)
        val keep = PersonalDictionary.entries(this).map { it.word }
        val cleanName = CleanupStore.chosen(this)?.let { "${it.name} ${it.version}" }
        val before = status.text
        t.cleanRunning = true
        status.setText(R.string.tm_cleanup_running)
        val app = applicationContext
        paraWorker.execute {
            val r = runCatching { Cleanup.clean(flat, cleaner(gguf), keep) }
            if (r.isFailure) closeCleaner()
            val res = r.getOrElse { Cleanup.Result(flat, 1, 1, it.message ?: it.javaClass.simpleName) }
            ui.post {
                t.cleanRunning = false
                val current = take === t && cleaning()
                if (!res.cleaned) {
                    if (current) status.text = getString(R.string.tm_cleanup_failed, res.error)
                    return@post paragraphsFor(t, stats)
                }
                t.cleanText = res.text
                if (take === t) cleanName?.let { doc?.cleanup?.add(it) }
                val applied = current && unedited()
                if (applied) show(compose(t, mode))
                if (stats != null) History.record(app, if (applied || !current) res.text else flat, stats, History.RECORD)
                if (current) status.text = when {
                    !applied -> getString(R.string.tm_cleanup_edited)
                    res.keptRaw > 0 -> getString(R.string.tm_cleanup_partly, res.keptRaw, res.chunks, res.error)
                    else -> before
                }
            }
        }
    }

    /** The loaded clean-up model for [f], loaded on first use. [paraWorker] only. */
    private fun cleaner(f: File): CleanupModel {
        cleanModel?.takeIf { cleanModelFile == f }?.let { return it }
        closeCleaner()
        return CleanupModel(f, Transcriber.threads).also { cleanModel = it; cleanModelFile = f }
    }

    /** [paraWorker] only. Frees the model's memory (a few hundred MB). */
    private fun closeCleaner() {
        runCatching { cleanModel?.close() }
        cleanModel = null
        cleanModelFile = null
    }

    /** Clean up switched, a model chosen or downloaded: redo the finished take if the box is still what the app wrote. */
    private fun reflowCleanup() {
        val t = take ?: return
        if (t.pieces.isEmpty() || !t.done || t.cleanRunning) return
        if (!unedited()) { status.setText(R.string.tm_cleanup_edited); return }
        if (cleaning() && t.cleanText == null && CleanupStore.readyFile(this) != null) runCleanup(t, null)
        else if (cleaning() && t.cleanText != null) show(compose(t, mode))
        else paragraphsFor(t, null)
    }

    private fun setCleanup(on: Boolean) {
        cleanOn = on
        Prefs.setTmCleanup(this, on)
        if (!on) paraWorker.execute { closeCleaner() }
        else if (CleanupStore.readyFile(this) == null) CleanupStore.chosen(this)?.let { askDownload(it) }
        showCleanup()
        showParagraphs()
        reflowCleanup()
    }

    private fun chooseCleanup() {
        val all = CleanupStore.entries(this)
        val cur = CleanupStore.chosen(this)
        val names = all.map { e ->
            val n = getString(if (e.experimental) R.string.tm_cleanup_finetune else R.string.tm_cleanup_stock, e.name, e.downloadMb)
            if (CleanupStore.isReady(this, e)) getString(R.string.tm_cleanup_downloaded_mark, n) else n
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.tm_cleanup_choose)
            .setSingleChoiceItems(names.toTypedArray(), all.indexOf(cur)) { dlg, i ->
                dlg.dismiss()
                pickCleanup(all[i])
            }
            .setNeutralButton(R.string.tm_cleanup_delete_unused) { _, _ ->
                all.filter { it.id != cur?.id }.forEach { CleanupStore.remove(this, it.id) }
                showCleanup()
            }
            .show()
    }

    private fun pickCleanup(e: CleanupStore.Entry) {
        if (e.id == CleanupStore.chosen(this)?.id) return
        Prefs.setCleanupChoice(this, e.id)
        paraWorker.execute { closeCleaner() }
        take?.cleanText = null
        if (!CleanupStore.isReady(this, e)) askDownload(e)
        showCleanup()
        showParagraphs()
        if (cleanOn) reflowCleanup()
    }

    private fun askDownload(e: CleanupStore.Entry) {
        AlertDialog.Builder(this)
            .setTitle(R.string.tm_cleanup_ask_title)
            .setMessage(getString(R.string.tm_cleanup_ask, e.name, e.downloadMb, e.ramMb))
            .setPositiveButton(R.string.tm_cleanup_download) { _, _ -> CleanupStore.download(this, e); showCleanup() }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun showCleanup() {
        val e = CleanupStore.chosen(this)
        cleanBox.visibility = if (cleanOk && e != null) View.VISIBLE else View.GONE
        if (!cleanOk || e == null) return
        val s = CleanupStore.status
        cleanLine.text = when {
            s is CleanupStore.Status.Running -> getString(R.string.tm_cleanup_downloading,
                CleanupStore.entries(this).firstOrNull { it.id == s.id }?.name ?: e.name,
                if (s.total > 0) (s.done * 100 / s.total).toInt() else 0)
            !cleanOn -> getString(R.string.tm_cleanup_line_off, e.name)
            !CleanupStore.isReady(this, e) -> getString(R.string.tm_cleanup_line_missing, e.name, e.downloadMb)
            else -> getString(R.string.tm_cleanup_line_ready, e.name)
        }
        cleanProgress.visibility = if (s is CleanupStore.Status.Running) View.VISIBLE else View.GONE
        if (s is CleanupStore.Status.Running) cleanProgress.progress = if (s.total > 0) (s.done * 1000 / s.total).toInt() else 0
    }

    private fun onCleanupDownload(s: CleanupStore.Status) {
        showCleanup()
        showParagraphs()
        showSave()
        val titleId = CleanupStore.title(this)?.id
        when (s) {
            is CleanupStore.Status.Done -> if (s.id == titleId) status.setText(R.string.tm_titles_downloaded)
                else if (cleanOn && s.id == CleanupStore.chosen(this)?.id) {
                    status.setText(R.string.tm_cleanup_downloaded)
                    reflowCleanup()
                }
            is CleanupStore.Status.Failed -> status.text = getString(
                if (s.id == titleId) R.string.tm_titles_download_failed else R.string.tm_cleanup_download_failed, s.message)
            else -> Unit
        }
    }

    // -- save (B-74a) and titles (B-75a) -------------------------------------------------
    /** The speech model in use, as the files name it: "Sabich v2.3". */
    private fun modelLabel(): String {
        val m = Catalogue.selected(this)
        return listOf(m.name, ModelStore.installed(this, m)?.label.orEmpty()).filter { it.isNotEmpty() }.joinToString(" ")
    }

    /** A take finished: start a new [Doc] when the box was empty, else add the take to it. */
    private fun noteDoc(t: Take, stats: TakeDecoder.Stats) {
        val d = doc?.takeIf { t.base.isNotBlank() } ?: Doc(System.currentTimeMillis()).also { doc = it }
        joined(t, false).trim().takeIf { it.isNotEmpty() }?.let(d.raw::add)
        d.seconds += stats.audioSeconds
        d.recorded = true
        modelLabel().takeIf { it.isNotEmpty() }?.let(d.models::add)
    }

    /** The front matter's details, in desktop's order (generator, model, audio_seconds, source, cleanup_model). */
    private fun meta(d: Doc?): Map<String, Any?> = linkedMapOf(
        "generator" to "Hebrish Android ${versionName()}",
        "model" to (d?.models?.takeIf { it.isNotEmpty() }?.joinToString(", ") ?: modelLabel()),
        "audio_seconds" to d?.seconds?.takeIf { it > 0 },
        "source" to if (d?.recorded == true) "recording" else null,
        "cleanup_model" to d?.cleanup?.takeIf { it.isNotEmpty() }?.joinToString(", "),
    )

    /**
     * Saves the box: the title first when the title model is downloaded and the switch is on (on
     * [paraWorker], which owns the models; the clean-up model is let go first to keep memory low),
     * then the files. No folder yet: the picker first, then this again.
     */
    private fun save() {
        val body = text.text.toString()
        if (body.isBlank()) { status.setText(R.string.tm_save_empty); return }
        val d = doc ?: Doc(System.currentTimeMillis()).also { doc = it }
        if (d.savedText == body) { status.text = getString(R.string.tm_already_saved, d.savedPath); return }
        if (saving) return
        if (TranscriptFolder.tree(this) == null) { saveAfterPick = true; pickFolder(); return }
        saving = true
        val raw = d.raw.takeIf { it.isNotEmpty() }?.joinToString("\n\n")
        val meta = meta(d)
        val titleFile = if (Prefs.titles(this)) CleanupStore.titleFile(this) else null
        val max = Prefs.titleMaxChars(this)
        status.setText(if (titleFile != null) R.string.tm_titling else R.string.tm_saving)
        val app = applicationContext
        paraWorker.execute {
            val title = titleFile?.let { f ->
                closeCleaner()
                runCatching { CleanupModel(f, Transcriber.threads, Titles.CTX).use { Titles.make(body, it, max) } }.getOrNull()
            }
            val r = runCatching { TranscriptFolder.save(app, body, raw, title, d.whenMs, meta) }
            ui.post {
                saving = false
                r.onSuccess { path ->
                    d.savedText = body
                    d.savedPath = path
                    status.text = getString(R.string.tm_saved, path)
                }.onFailure { status.text = getString(R.string.tm_save_failed, it.message ?: it.javaClass.simpleName) }
            }
        }
    }

    private fun pickFolder() {
        try {
            @Suppress("DEPRECATION") startActivityForResult(TranscriptFolder.pickIntent(this), PICK_FOLDER)
        } catch (_: android.content.ActivityNotFoundException) {
            saveAfterPick = false
            Toast.makeText(this, R.string.tm_no_picker, Toast.LENGTH_LONG).show()
        }
    }

    @Deprecated("Activity.onActivityResult")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        @Suppress("DEPRECATION") super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != PICK_FOLDER) return
        val uri = data?.data
        val again = saveAfterPick
        saveAfterPick = false
        if (resultCode != RESULT_OK || uri == null) return
        val ok = runCatching { TranscriptFolder.accept(this, uri) }
        ok.onFailure { status.text = getString(R.string.tm_save_failed, it.message ?: it.javaClass.simpleName) }
        showSave()
        if (ok.isSuccess && again) save()
    }

    private fun setTitles(on: Boolean) {
        Prefs.setTitles(this, on)
        val e = CleanupStore.title(this)
        if (on && e != null && !CleanupStore.isReady(this, e)) {
            AlertDialog.Builder(this)
                .setTitle(R.string.tm_titles_ask_title)
                .setMessage(getString(R.string.tm_titles_ask, e.downloadMb, e.ramMb))
                .setPositiveButton(R.string.tm_cleanup_download) { _, _ -> CleanupStore.download(this, e); showSave() }
                .setNegativeButton(android.R.string.cancel, null)
                .show()
        }
        showSave()
    }

    /** The folder line, and the title switch's line (hidden when this phone or catalogue has no title model). */
    private fun showSave() {
        saveLine.text = TranscriptFolder.label(this)?.let { getString(R.string.tm_save_line, it) } ?: getString(R.string.tm_save_no_folder)
        val e = CleanupStore.title(this)
        titleBox.visibility = if (e != null) View.VISIBLE else View.GONE
        if (e == null) return
        val s = CleanupStore.status
        val running = s is CleanupStore.Status.Running && s.id == e.id
        titleLine.text = when {
            running -> getString(R.string.tm_titles_downloading, (s as CleanupStore.Status.Running).let { if (it.total > 0) (it.done * 100 / it.total).toInt() else 0 })
            !Prefs.titles(this) -> getString(R.string.tm_titles_off)
            !CleanupStore.isReady(this, e) -> getString(R.string.tm_titles_missing, e.downloadMb)
            else -> getString(R.string.tm_titles_ready)
        }
        titleProgress.visibility = if (running) View.VISIBLE else View.GONE
        if (running) (s as CleanupStore.Status.Running).let { titleProgress.progress = if (it.total > 0) (it.done * 1000 / it.total).toInt() else 0 }
    }

    private fun chooseParagraphs() {
        val modes = ParagraphMode.values()
        val names = modes.map {
            when (it) {
                ParagraphMode.NONE -> getString(R.string.tm_para_none_long)
                ParagraphMode.TIME -> getString(R.string.tm_para_time_long)
                ParagraphMode.MODEL -> getString(if (ParagraphStore.isReady(this)) R.string.tm_para_model_long else R.string.tm_para_model_download)
            }
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.tm_paragraphs)
            .setSingleChoiceItems(names.toTypedArray(), modes.indexOf(mode)) { dlg, i ->
                dlg.dismiss()
                setParagraphs(modes[i])
            }
            .show()
    }

    private fun setParagraphs(m: ParagraphMode) {
        Prefs.setTmParagraphs(this, m.key)
        mode = m
        if (m != ParagraphMode.MODEL) paraWorker.execute { closeModel() }
        else if (!ParagraphStore.isReady(this)) ParagraphStore.download(this)
        showParagraphs()
        reflow()
    }

    private fun showParagraphs() {
        val name = getString(when (mode) {
            ParagraphMode.NONE -> R.string.tm_para_none
            ParagraphMode.TIME -> R.string.tm_para_time
            ParagraphMode.MODEL -> R.string.tm_para_model
        })
        val s = ParagraphStore.status
        val byCleanup = cleaning() && CleanupStore.readyFile(this) != null
        paraLine.alpha = if (byCleanup) 0.6f else 1f
        paraLine.text = when {
            byCleanup -> getString(R.string.tm_para_by_cleanup)
            s is ParagraphStore.Status.Running -> getString(R.string.tm_para_downloading, name,
                if (s.total > 0) (s.done * 100 / s.total).toInt() else 0)
            mode == ParagraphMode.MODEL && !ParagraphStore.isReady(this) -> getString(R.string.tm_para_line_missing, name)
            else -> getString(R.string.tm_para_line, name)
        }
        paraProgress.visibility = if (s is ParagraphStore.Status.Running) View.VISIBLE else View.GONE
        if (s is ParagraphStore.Status.Running) paraProgress.progress = if (s.total > 0) (s.done * 1000 / s.total).toInt() else 0
    }

    private fun onParagraphDownload(s: ParagraphStore.Status) {
        showParagraphs()
        when (s) {
            is ParagraphStore.Status.Done -> if (mode == ParagraphMode.MODEL) {
                status.setText(R.string.tm_para_downloaded)
                reflow()
            }
            is ParagraphStore.Status.Failed -> status.text = getString(R.string.tm_para_download_failed, s.message)
            else -> Unit
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        if (requestCode == REQ_NOTIFY) { Recording.changed(); return refresh() }
        if (requestCode == REQ_MIC && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) recOrPause()
        else if (requestCode == REQ_MIC) status.setText(R.string.try_need_mic)
    }

    /** The desktop meter (ui/meter.py): block RMS in dBFS over -60..0 on zone bands, a peak tick, a clip lamp. */
    private class Meter(ctx: Context) : View(ctx) {
        private var db = FLOOR_DB
        private var peakDb = FLOOR_DB
        private var clipping = false
        private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        private val d = ctx.resources.displayMetrics.density
        // Redrawn on every meter block: no allocations in onDraw.
        private val lampRect = RectF()
        private val clipLabel = ctx.getString(R.string.tm_meter_clip)

        fun set(db: Float, peakDb: Float, clipping: Boolean) {
            this.db = db; this.peakDb = peakDb; this.clipping = clipping
            invalidate()
        }

        private fun x(v: Float, w: Float) = ((v - FLOOR_DB) / -FLOOR_DB).coerceIn(0f, 1f) * w

        override fun onDraw(c: Canvas) {
            val lamp = 34 * d
            val w = width - lamp - 6 * d
            val h = height.toFloat()
            for ((lo, hi, col) in ZONES) {
                paint.color = Color.argb(55, Color.red(col), Color.green(col), Color.blue(col))
                c.drawRect(x(lo, w), 0f, x(hi, w), h, paint)
            }
            val level = x(db, w)
            for ((lo, hi, col) in ZONES) {
                val a = x(lo, w)
                val b = minOf(x(hi, w), level)
                if (b > a) { paint.color = col; c.drawRect(a, 3 * d, b, h - 3 * d, paint) }
            }
            if (peakDb > FLOOR_DB) {
                paint.color = Color.DKGRAY
                val px = x(peakDb, w)
                c.drawRect(px - d, 0f, px + d, h, paint)
            }
            paint.color = if (clipping) CLIP_RED else Color.rgb(0xc9, 0xcf, 0xcc)
            lampRect.set(w + 6 * d, 0f, w + 6 * d + lamp, h)
            c.drawRoundRect(lampRect, 4 * d, 4 * d, paint)
            paint.color = Color.WHITE
            paint.textSize = 9 * d
            paint.isFakeBoldText = true
            paint.textAlign = Paint.Align.CENTER
            c.drawText(clipLabel, w + 6 * d + lamp / 2, h / 2 + 3 * d, paint)
        }
    }

    companion object {
        private const val REQ_MIC = 11
        private const val REQ_NOTIFY = 12
        private const val PICK_FOLDER = 13
        private const val PARAGRAPH_S = 30
        private const val CONFIRM_DROP_S = 60f
        private const val CLIP_HOLD_MS = 1500L
        // Level zones (desktop audio.QUIET_DB / LOUD_DB, from Voice Notepad's mic test: aim for -30 to -12).
        private const val FLOOR_DB = -60f
        private const val QUIET_DB = -40f
        private const val LOUD_DB = -12f
        private val GOOD_GREEN = Color.rgb(0x2e, 0x9e, 0x5b)
        private val LOUD_AMBER = Color.rgb(0xb0, 0x7a, 0x0c)
        private val CLIP_RED = Color.rgb(0xD6, 0x28, 0x28)
        private val ZONES = listOf(Triple(FLOOR_DB, QUIET_DB, Color.rgb(0x9a, 0xa3, 0xa0)), Triple(QUIET_DB, LOUD_DB, GOOD_GREEN),
            Triple(LOUD_DB, -3f, Color.rgb(0xE8, 0xA3, 0x17)), Triple(-3f, 0f, CLIP_RED))

        private fun dbfs(x: Float) = if (x > 1e-6f) (20 * kotlin.math.log10(x)) else -120f

        fun clock(s: Float): String {
            val t = s.toInt()
            return if (t >= 3600) "%d:%02d:%02d".format(t / 3600, t / 60 % 60, t % 60) else "%02d:%02d".format(t / 60, t % 60)
        }
    }
}
