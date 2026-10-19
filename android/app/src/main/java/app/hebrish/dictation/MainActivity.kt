package app.hebrish.dictation

import app.hebrish.core.*
import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.DocumentsContract
import android.provider.Settings
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.RadioButton
import android.widget.RadioGroup
import android.widget.Switch
import android.widget.Toast
import android.widget.TextView
import java.io.File

/** Setup: pick and download a model, grant the mic, enable the keyboard, and try it out. */
class MainActivity : Activity() {
    private lateinit var modelPicker: RadioGroup
    private lateinit var manageBtn: Button
    private lateinit var modelStatus: TextView
    private lateinit var modelProgress: ProgressBar
    private lateinit var downloadBtn: Button
    private lateinit var updateStatus: TextView
    private lateinit var updateBtn: Button
    private lateinit var checkUpdateBtn: Button
    private lateinit var micStatus: TextView
    private lateinit var micBtn: Button
    private lateinit var imeStatus: TextView
    private lateinit var locationStatus: TextView
    private lateinit var resetLocationBtn: Button
    private lateinit var returnStatus: TextView
    /** Set while the user is away granting storage access, so the folder picker opens on return. */
    private var pickAfterGrant = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        modelPicker = findViewById(R.id.model_picker)
        manageBtn = findViewById(R.id.manage_models)
        manageBtn.setOnClickListener { manageModels() }
        modelStatus = findViewById(R.id.model_status)
        modelProgress = findViewById(R.id.model_progress)
        downloadBtn = findViewById(R.id.download)
        updateStatus = findViewById(R.id.update_status)
        updateBtn = findViewById(R.id.update)
        checkUpdateBtn = findViewById(R.id.check_update)
        micStatus = findViewById(R.id.mic_status)
        micBtn = findViewById(R.id.grant_mic)
        imeStatus = findViewById(R.id.ime_status)
        locationStatus = findViewById(R.id.location_status)
        resetLocationBtn = findViewById(R.id.reset_location)
        returnStatus = findViewById(R.id.return_status)
        findViewById<Button>(R.id.return_change).setOnClickListener { chooseReturnIme() }
        findViewById<Button>(R.id.open_try).setOnClickListener { startActivity(Intent(this, TryActivity::class.java)) }

        downloadBtn.setOnClickListener {
            if (ModelDownload.status is ModelDownload.Status.Running) ModelDownload.cancel() else ModelDownload.start(this)
        }
        updateBtn.setOnClickListener { ModelDownload.update(this) }
        checkUpdateBtn.setOnClickListener { ModelDownload.check(this, force = true) }
        micBtn.setOnClickListener { requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQ_MIC) }
        findViewById<Button>(R.id.choose_location).setOnClickListener { chooseLocation() }
        resetLocationBtn.setOnClickListener { ModelDownload.relocate(this, null); render() }
        findViewById<Button>(R.id.enable_ime).setOnClickListener { startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS)) }
        findViewById<Button>(R.id.pick_ime).setOnClickListener {
            (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker()
        }
        findViewById<Button>(R.id.get_heliboard).setOnClickListener { open(getString(R.string.url_heliboard)) }
        findViewById<Button>(R.id.open_model).setOnClickListener {
            val m = Catalogue.selected(this)
            open(m.card ?: "https://huggingface.co/${m.repo}")
        }
        findViewById<Button>(R.id.open_source).setOnClickListener { open(getString(R.string.url_source)) }
        findViewById<Button>(R.id.open_terms).setOnClickListener { open(getString(R.string.url_terms)) }
        findViewById<LinearLayout>(R.id.hebrish_links).let { box ->
            for ((label, url) in Hebrish.LINKS) box.addView(Button(this).apply {
                setText(label)
                setOnClickListener { open(url) }
            }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        }

        findViewById<Switch>(R.id.auto_start).apply {
            isChecked = Prefs.autoStart(this@MainActivity)
            setOnCheckedChangeListener { _, v -> Prefs.setAutoStart(this@MainActivity, v) }
        }
        findViewById<Switch>(R.id.auto_return).apply {
            isChecked = Prefs.autoReturn(this@MainActivity)
            setOnCheckedChangeListener { _, v -> Prefs.setAutoReturn(this@MainActivity, v) }
        }
        findViewById<Switch>(R.id.back_switches).apply {
            isChecked = Prefs.backSwitches(this@MainActivity)
            setOnCheckedChangeListener { _, v -> Prefs.setBackSwitches(this@MainActivity, v) }
        }
    }

    override fun onResume() {
        super.onResume()
        ModelDownload.listener = { render() }
        if (pickAfterGrant && hasStorageAccess()) openFolderPicker()
        pickAfterGrant = false
        noteDefaultIme()
        ModelDownload.check(this)
        render()
    }

    override fun onPause() {
        super.onPause()
        ModelDownload.listener = null
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        render()
        if (requestCode == REQ_STORAGE) {
            if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) openFolderPicker()
            return
        }
        if (grantResults.firstOrNull() == PackageManager.PERMISSION_DENIED && !shouldShowRequestPermissionRationale(Manifest.permission.RECORD_AUDIO)) {
            // Permanently denied: only the app settings page can grant it now.
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQ_FOLDER || resultCode != RESULT_OK) return
        val path = data?.data?.let(::treeToPath)
        val dir = path?.let { File(it, ModelStore.sharedFolder(Catalogue.selected(this))) }
        if (dir == null || !(dir.isDirectory || dir.mkdirs()) || !dir.canWrite()) {
            locationStatus.text = getString(R.string.location_unusable)
            return
        }
        ModelDownload.relocate(this, path)
        render()
    }

    /** Shared storage needs a real file path (sherpa-onnx opens files by path), hence all-files access. */
    private fun chooseLocation() {
        if (hasStorageAccess()) return openFolderPicker()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            pickAfterGrant = true
            startActivity(Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION, Uri.parse("package:$packageName")))
        } else {
            requestPermissions(arrayOf(Manifest.permission.WRITE_EXTERNAL_STORAGE), REQ_STORAGE)
        }
    }

    private fun hasStorageAccess() =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) Environment.isExternalStorageManager()
        else checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED

    private fun openFolderPicker() = startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE), REQ_FOLDER)

    /** "primary:Models" -> /storage/emulated/0/Models; "1234-ABCD:x" -> /storage/1234-ABCD/x (SD card). */
    private fun treeToPath(uri: Uri): String? {
        if (uri.authority != "com.android.externalstorage.documents") return null
        val id = DocumentsContract.getTreeDocumentId(uri)
        val volume = id.substringBefore(':')
        val rel = id.substringAfter(':', "")
        val root = if (volume == "primary") Environment.getExternalStorageDirectory().path else "/storage/$volume"
        return if (rel.isEmpty()) root else "$root/$rel"
    }

    /**
     * One radio button per catalogue model. Planned models are shown, disabled, as coming soon.
     * Picking a model makes it the keyboard's model at once; if it isn't downloaded yet the model
     * section below offers the download. Disabled while a download or move runs.
     */
    private fun renderPicker(running: Boolean) {
        val selected = Catalogue.selected(this)
        modelPicker.setOnCheckedChangeListener(null)
        modelPicker.removeAllViews()
        for (m in Catalogue.get(this).models) {
            val state = when {
                !m.available -> getString(R.string.model_coming_soon)
                ModelStore.isReady(this, model = m) -> getString(R.string.model_downloaded)
                else -> getString(R.string.model_not_downloaded)
            }
            modelPicker.addView(RadioButton(this).apply {
                id = View.generateViewId()
                tag = m.id
                text = getString(R.string.model_option, m.name, state, m.summary)
                isEnabled = m.available && !running
                isChecked = m.id == selected.id
                setPadding(paddingLeft, 8, paddingRight, 8)
            })
        }
        modelPicker.setOnCheckedChangeListener { group, checkedId ->
            val id = group.findViewById<RadioButton>(checkedId)?.tag as? String ?: return@setOnCheckedChangeListener
            if (id == Catalogue.selected(this).id) return@setOnCheckedChangeListener
            ModelPrefs.setSelectedModel(this, id)
            Transcriber.unload()
            ModelDownload.clearFailure()
            ModelDownload.check(this)
            render()
        }
    }

    /** Lists downloaded models other than the selected one; tapping one deletes it after a confirm. */
    private fun manageModels() {
        val selected = Catalogue.selected(this)
        val others = ModelStore.readyModels(this).filter { it.id != selected.id }
        if (others.isEmpty()) {
            android.app.AlertDialog.Builder(this).setMessage(R.string.manage_none).setPositiveButton(android.R.string.ok, null).show()
            return
        }
        val labels = others.map { getString(R.string.manage_item, it.name, ModelStore.installed(this, it)!!.totalBytes / 1_000_000) }
        android.app.AlertDialog.Builder(this)
            .setTitle(R.string.manage_title)
            .setItems(labels.toTypedArray()) { _, which ->
                val m = others[which]
                android.app.AlertDialog.Builder(this)
                    .setMessage(getString(R.string.manage_confirm, m.name))
                    .setPositiveButton(R.string.delete) { _, _ -> ModelStore.delete(this, m); render() }
                    .setNegativeButton(R.string.cancel, null)
                    .show()
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun render() {
        val model = Catalogue.selected(this)
        val installed = ModelStore.installed(this, model)
        val mb = (installed?.totalBytes ?: ModelStore.BUNDLED.values.first().totalBytes) / 1_000_000
        val s = ModelDownload.status
        val ready = ModelStore.isReady(this)
        renderPicker(s is ModelDownload.Status.Running)
        manageBtn.visibility = if (ModelStore.readyModels(this).any { it.id != model.id }) View.VISIBLE else View.GONE
        findViewById<TextView>(R.id.version).text = if (installed != null)
            getString(R.string.version_line, BuildConfigShim.versionName(this), model.name, installed.version, installed.revision.take(12))
        else getString(R.string.version_line_none, BuildConfigShim.versionName(this), model.name)
        modelProgress.visibility = if (s is ModelDownload.Status.Running) View.VISIBLE else View.GONE
        when {
            s is ModelDownload.Status.Running -> {
                modelProgress.progress = (s.done * 1000 / s.total.coerceAtLeast(1)).toInt()
                modelStatus.text = if (ModelDownload.moving) getString(R.string.model_moving, s.done / 1_000_000, s.total / 1_000_000)
                else getString(R.string.model_downloading_version, ModelDownload.target?.let { (m, v) -> listOfNotNull(m.name, v?.version).joinToString(" ") } ?: "", s.done / 1_000_000, s.total / 1_000_000)
                downloadBtn.setText(R.string.cancel)
                downloadBtn.visibility = View.VISIBLE
                window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
            ready -> {
                modelStatus.text = getString(R.string.model_ready, model.name, installed!!.version, mb)
                downloadBtn.visibility = View.GONE
                window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
            else -> {
                modelStatus.text = if (s is ModelDownload.Status.Failed) getString(R.string.model_failed, s.message)
                else getString(R.string.model_missing, model.name, mb)
                downloadBtn.setText(R.string.download)
                downloadBtn.visibility = View.VISIBLE
                window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
        }

        renderUpdate(installed, s, ready)
        findViewById<Button>(R.id.open_try).apply {
            isEnabled = ready
            setText(if (ready) R.string.try_open else R.string.try_open_no_model)
        }

        val root = ModelPrefs.modelRoot(this)
        locationStatus.text = if (root == null) getString(R.string.location_private)
        else getString(R.string.location_shared, ModelStore.base(this).path)
        resetLocationBtn.visibility = if (root == null) View.GONE else View.VISIBLE

        val mic = checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
        micStatus.setText(if (mic) R.string.mic_ok else R.string.mic_missing)
        micBtn.visibility = if (mic) View.GONE else View.VISIBLE

        val fixed = imeLabel(Prefs.returnIme(this))
        val auto = imeLabel(Prefs.lastOtherIme(this))
        returnStatus.text = when {
            fixed != null -> getString(R.string.return_fixed, fixed)
            auto != null -> getString(R.string.return_auto, auto)
            else -> getString(R.string.return_auto_unknown)
        }

        val imm = getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager
        val enabled = imm.enabledInputMethodList.any { it.packageName == packageName }
        imeStatus.setText(if (enabled) R.string.ime_enabled else R.string.ime_disabled)
    }

    /** Only once a model is installed; before that, Download already fetches the newest one. */
    private fun renderUpdate(installed: ModelStore.Manifest?, s: ModelDownload.Status, ready: Boolean) {
        val running = s is ModelDownload.Status.Running
        val update = ModelDownload.updateAvailable(this)
        checkUpdateBtn.visibility = if (ready && !running && !ModelDownload.checking) View.VISIBLE else View.GONE
        updateBtn.visibility = if (update != null && !running) View.VISIBLE else View.GONE
        update?.let { updateBtn.text = getString(R.string.update_button, it.version) }
        updateStatus.visibility = if (ready && !running) View.VISIBLE else View.GONE
        updateStatus.text = when {
            ModelDownload.checking -> getString(R.string.update_checking)
            update != null && s is ModelDownload.Status.Failed -> getString(R.string.update_failed, s.message, installed?.version ?: "")
            update != null -> getString(R.string.update_available, update.version, update.totalBytes / 1_000_000, installed?.version ?: "")
            ModelDownload.checkError != null -> getString(R.string.update_check_failed, ModelDownload.checkError)
            ModelDownload.latest(Catalogue.selected(this).id) != null -> getString(R.string.update_none, installed?.version ?: "")
            else -> ""
        }
    }

    /**
     * The IME service can't see which keyboard it was opened from, but the system default is
     * readable here. When setup opens it is usually the user's regular keyboard: remember it
     * as a fallback target for VoiceImeService.switchBack.
     */
    private fun noteDefaultIme() {
        val id = Settings.Secure.getString(contentResolver, Settings.Secure.DEFAULT_INPUT_METHOD) ?: return
        if (!id.startsWith("$packageName/")) Prefs.setLastOtherIme(this, id)
    }

    private fun otherImes() = (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).enabledInputMethodList
        .filter { it.packageName != packageName }

    private fun imeLabel(id: String?) = otherImes().firstOrNull { it.id == id }?.loadLabel(packageManager)?.toString()

    private fun chooseReturnIme() {
        val imes = otherImes()
        val labels = listOf(getString(R.string.return_auto_option)) + imes.map { it.loadLabel(packageManager).toString() }
        val current = imes.indexOfFirst { it.id == Prefs.returnIme(this) } + 1
        android.app.AlertDialog.Builder(this)
            .setTitle(R.string.return_title)
            .setSingleChoiceItems(labels.toTypedArray(), current) { d, which ->
                Prefs.setReturnIme(this, if (which == 0) null else imes[which - 1].id)
                d.dismiss()
                render()
            }
            .show()
    }

    private fun open(url: String) {
        if (!url.startsWith("mailto:")) return startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        // Feedback email: the version lines help triage; the user writes above them.
        val version = packageManager.getPackageInfo(packageName, 0).versionName
        val body = "\n\n--\nHebrish $version, Android ${Build.VERSION.RELEASE}, ${Build.MANUFACTURER} ${Build.MODEL}"
        val mail = Intent(Intent.ACTION_SENDTO, Uri.parse("$url&body=" + Uri.encode(body)))
        try { startActivity(mail) } catch (_: android.content.ActivityNotFoundException) {
            Toast.makeText(this, getString(R.string.no_email_app, Hebrish.FEEDBACK), Toast.LENGTH_LONG).show()
        }
    }

    private companion object {
        const val REQ_MIC = 1
        const val REQ_STORAGE = 2
        const val REQ_FOLDER = 3
    }
}

/** Avoids enabling the BuildConfig generator just for one string. */
object BuildConfigShim {
    fun versionName(a: Activity): String =
        a.packageManager.getPackageInfo(a.packageName, 0).versionName ?: "?"
}
