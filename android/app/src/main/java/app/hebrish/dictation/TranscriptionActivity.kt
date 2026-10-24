package app.hebrish.dictation

import app.hebrish.core.*
import android.Manifest
import android.app.AlertDialog
import android.content.ClipData
import android.content.ClipboardManager
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
        meter = Meter(this)
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
            button(R.string.try_copy, r) { copy() }
            button(R.string.try_share, r) { share() }
            button(R.string.try_clear, r) { text.setText("") }
        }

        showMic()
        showLeftover()
        sync()
    }

    override fun onResume() {
        super.onResume()
        Recording.listener = { refresh() }
        refresh()
    }

    override fun onPause() {
        super.onPause()
        Recording.listener = null
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
                try { tape.resume() } catch (e: Exception) { status.text = getString(R.string.ime_mic_error, e.message ?: "?") }
                status.text = ""
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

    private fun heldSeconds(): Float = held?.takeIf { it.exists() }?.let { Tape.recover(it) } ?: 0f

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
            .setMessage(getString(R.string.tm_confirm_drop, clock(Tape.recover(f))))
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
                    if (result.isSuccess) History.record(this, d.text, d.stats(), History.RECORD)
                    finished(f, result.exceptionOrNull())
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

    private fun insert(said: String, paragraph: Boolean) {
        val e = text.text
        val sep = if (e.isEmpty()) "" else if (paragraph) "\n\n" else null
        val chunk = if (sep != null) sep + said.trimStart() else TakeDecoder.join(e, said)
        e.append(chunk)
    }

    private fun copy() {
        (getSystemService(CLIPBOARD_SERVICE) as ClipboardManager)
            .setPrimaryClip(ClipData.newPlainText(getString(R.string.app_name), text.text))
        Toast.makeText(this, R.string.try_copied, Toast.LENGTH_SHORT).show()
    }

    private fun share() {
        if (text.text.isBlank()) return
        startActivity(Intent.createChooser(
            Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, text.text.toString()),
            getString(R.string.try_share)))
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
            c.drawRoundRect(RectF(w + 6 * d, 0f, w + 6 * d + lamp, h), 4 * d, 4 * d, paint)
            paint.color = Color.WHITE
            paint.textSize = 9 * d
            paint.isFakeBoldText = true
            paint.textAlign = Paint.Align.CENTER
            c.drawText("CLIP", w + 6 * d + lamp / 2, h / 2 + 3 * d, paint)
        }
    }

    companion object {
        private const val REQ_MIC = 11
        private const val REQ_NOTIFY = 12
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
