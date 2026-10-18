package com.danielrosehill.codeswitchvoice

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.ProgressBar
import android.widget.Switch
import android.widget.TextView

/** Setup: download the model, grant the mic, enable the keyboard, and try it out. */
class MainActivity : Activity() {
    private lateinit var modelStatus: TextView
    private lateinit var modelProgress: ProgressBar
    private lateinit var downloadBtn: Button
    private lateinit var micStatus: TextView
    private lateinit var micBtn: Button
    private lateinit var imeStatus: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        modelStatus = findViewById(R.id.model_status)
        modelProgress = findViewById(R.id.model_progress)
        downloadBtn = findViewById(R.id.download)
        micStatus = findViewById(R.id.mic_status)
        micBtn = findViewById(R.id.grant_mic)
        imeStatus = findViewById(R.id.ime_status)

        findViewById<TextView>(R.id.version).text =
            getString(R.string.version_line, BuildConfigShim.versionName(this), ModelStore.MODEL_VERSION, ModelStore.REVISION.take(12))

        downloadBtn.setOnClickListener {
            if (ModelDownload.status is ModelDownload.Status.Running) ModelDownload.cancel() else ModelDownload.start(this)
        }
        micBtn.setOnClickListener { requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1) }
        findViewById<Button>(R.id.enable_ime).setOnClickListener { startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS)) }
        findViewById<Button>(R.id.pick_ime).setOnClickListener {
            (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker()
        }
        findViewById<Button>(R.id.get_heliboard).setOnClickListener { open(getString(R.string.url_heliboard)) }
        findViewById<Button>(R.id.open_model).setOnClickListener { open("https://huggingface.co/${ModelStore.REPO}") }
        findViewById<Button>(R.id.open_dataset).setOnClickListener { open(getString(R.string.url_dataset)) }

        findViewById<Switch>(R.id.auto_start).apply {
            isChecked = Prefs.autoStart(this@MainActivity)
            setOnCheckedChangeListener { _, v -> Prefs.setAutoStart(this@MainActivity, v) }
        }
        findViewById<Switch>(R.id.auto_return).apply {
            isChecked = Prefs.autoReturn(this@MainActivity)
            setOnCheckedChangeListener { _, v -> Prefs.setAutoReturn(this@MainActivity, v) }
        }
    }

    override fun onResume() {
        super.onResume()
        ModelDownload.listener = { render() }
        render()
    }

    override fun onPause() {
        super.onPause()
        ModelDownload.listener = null
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        render()
        if (grantResults.firstOrNull() == PackageManager.PERMISSION_DENIED && !shouldShowRequestPermissionRationale(Manifest.permission.RECORD_AUDIO)) {
            // Permanently denied: only the app settings page can grant it now.
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
        }
    }

    private fun render() {
        val mb = ModelStore.totalBytes / 1_000_000
        val s = ModelDownload.status
        val ready = ModelStore.isReady(this)
        modelProgress.visibility = if (s is ModelDownload.Status.Running) View.VISIBLE else View.GONE
        when {
            s is ModelDownload.Status.Running -> {
                modelProgress.progress = (s.done * 1000 / ModelStore.totalBytes).toInt()
                modelStatus.text = getString(R.string.model_downloading, s.done / 1_000_000, mb)
                downloadBtn.setText(R.string.cancel)
                window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
            ready -> {
                modelStatus.text = getString(R.string.model_ready, ModelStore.MODEL_VERSION, mb)
                downloadBtn.visibility = View.GONE
                window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
            else -> {
                modelStatus.text = if (s is ModelDownload.Status.Failed) getString(R.string.model_failed, s.message)
                else getString(R.string.model_missing, mb)
                downloadBtn.setText(R.string.download)
                downloadBtn.visibility = View.VISIBLE
                window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
        }

        val mic = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
        micStatus.setText(if (mic) R.string.mic_ok else R.string.mic_missing)
        micBtn.visibility = if (mic) View.GONE else View.VISIBLE

        val imm = getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager
        val enabled = imm.enabledInputMethodList.any { it.packageName == packageName }
        imeStatus.setText(if (enabled) R.string.ime_enabled else R.string.ime_disabled)
    }

    private fun open(url: String) = startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
}

/** Avoids enabling the BuildConfig generator just for one string. */
object BuildConfigShim {
    fun versionName(a: Activity): String =
        a.packageManager.getPackageInfo(a.packageName, 0).versionName ?: "?"
}
