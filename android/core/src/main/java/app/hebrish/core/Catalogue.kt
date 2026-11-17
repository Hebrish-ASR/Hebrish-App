package app.hebrish.core

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * The model catalogue, shared/catalogue.json (schema 2, since 0.7.0): lines (what a model is
 * trained for: Sabich, Jachnun, Shakshuka, stock) each with variants (the line on another base
 * model). The APK carries a copy in its assets ([ASSET], copied by the gradle `copyCatalogue`
 * task). Each update check also fetches `catalogue_v2_url`; a copy that parses with schema
 * [SCHEMA] is cached in Prefs and wins over the bundled one, so a newly published model appears
 * without an APK release. Builds up to 0.6.0 read shared/models.json (schema 1) instead.
 *
 * [Data.models] holds only the variants this build can run ([SUPPORTED_ENGINES], platform
 * android), planned ones included; everything that downloads or selects uses it. [Data.lines]
 * holds every variant; the Models screen lists only the ones this build can run and the catalogue
 * offers on Android (`offered_on`), plus any already installed (D-2026-11-16-02, Daniel: a model
 * that isn't available on the platform is not listed at all).
 */
object Catalogue {
    const val ASSET = "catalogue.json"
    const val SCHEMA = 2
    const val PLATFORM = "android"
    /**
     * Engines this build runs. sherpa_online_transducer since B-13 (2026-11-17): Shakshuka streams on
     * Android too ([Model.streaming]); before that it ran only for language variants (the Hebrew line).
     * Literal strings: desktop/tests/test_shared.py reads this line.
     */
    val SUPPORTED_ENGINES = setOf("sherpa_offline_transducer", "sherpa_online_transducer")
    /** The streaming engine: [StreamingTranscriber] (language models) and [StreamingTranscriber.dictation] (Shakshuka). */
    const val ONLINE_ENGINE = "sherpa_online_transducer"

    /**
     * A third-party model's attribution (catalogue `credit`, required by CC BY 4.0 for the
     * Hebrew line): shown on its Models card and on About.
     */
    data class Credit(
        val text: String,
        val author: String = "",
        val data: String = "",
        val license: String = "",
        val licenseUrl: String? = null,
        val url: String? = null,
        val originalUrl: String? = null,
        val changes: String = "",
    )

    data class Model(
        val id: String,
        val name: String,
        val summary: String,
        val status: String,
        val repo: String?,
        val subdir: String,
        val card: String?,
        /** Label for a repo with no version.json (the stock export); else "rev <sha7>". */
        val versionLabel: String?,
        /** CDN manifest (cdn.hebrish.app); preferred over [repo] when set (0.2.2+). */
        val manifestUrl: String? = null,
        val line: String = "",
        val engine: String = "sherpa_offline_transducer",
        /** Mel features for sherpa-onnx: 128 for the 0.6B models, 80 for Sabich-Parakeet-110M. */
        val featureDim: Int = 128,
        val baseModel: String = "",
        /** What the Models screen shows for the base: "Parakeet 0.6B v2 by NVIDIA" (2026-10-25). */
        val baseLabel: String = "",
        /** Formats, runtimes, VRAM: only under the card's Technical details. */
        val technical: String = "",
        val platforms: List<String> = listOf(PLATFORM),
        val hardware: String = "",
        /** Download size in MB from the catalogue; null when not known yet. */
        val downloadMb: Int? = null,
        /** 1-5 tiers, estimates (catalogue `tiers`). */
        val speed: Int = 0,
        val accuracy: Int = 0,
        val recommendation: String = "",
        /** Where a variant this app can't run runs instead. */
        val runsOn: String = "",
        /**
         * Set (BCP 47, "he") for a language model (catalogue `language`, 2026-11-16): not a dictation
         * model the user picks, but the one used when the input language is that language
         * (docs/maintaining.md, "Hebrew model switching"). Kept out of [selected] and the main list.
         */
        val language: String? = null,
        /** sherpa-onnx online `model_type` (catalogue `engine_options.model_type`, "zipformer2"). */
        val modelType: String = "",
        val credit: Credit? = null,
        /** Catalogue `offered_on` (2026-11-12): the platforms whose Models screen lists it; null = every platform it runs on. */
        val offeredOn: List<String>? = null,
    ) {
        /** This build can run it: an Android variant on an engine in [SUPPORTED_ENGINES]. */
        val supported: Boolean get() = PLATFORM in platforms && engine in SUPPORTED_ENGINES
        /** A streaming model: decoded by an OnlineRecognizer, words as you speak (Shakshuka, the Hebrew line). */
        val streaming: Boolean get() = engine == ONLINE_ENGINE
        /** Listed but not downloadable: "planned" models show as coming soon. */
        val available: Boolean get() = supported && status == "available" && !(repo.isNullOrEmpty() && manifestUrl.isNullOrEmpty())
    }

    data class Line(val id: String, val name: String, val summary: String, val card: String?, val variants: List<Model>)

    data class Data(
        val catalogueUrl: String?,
        val default: String,
        /** The model to use when the user hasn't picked one (0.6.0+). */
        val recommended: String,
        val files: List<String>,
        val versionFile: String,
        val models: List<Model>,
        val lines: List<Line> = emptyList(),
    )

    @Volatile private var cached: Data? = null

    fun get(ctx: Context): Data {
        cached?.let { return it }
        val app = ctx.applicationContext
        val data = ModelPrefs.catalogueJson(app)?.let(::parse)
            ?: parse(app.assets.open(ASSET).bufferedReader().use { it.readText() })
            ?: throw IllegalStateException("bundled $ASSET does not parse")
        cached = data
        return data
    }

    fun model(ctx: Context, id: String): Model? = get(ctx).models.firstOrNull { it.id == id }

    /** The available model for [language] ("he"), downloaded or not; null if the catalogue has none. */
    fun forLanguage(ctx: Context, language: String): Model? {
        // Since 2026-11-17 the Hebrew line has two variants (the base Zipformer and Gefilte PoC): the
        // user's pick (Use for Hebrew) if downloaded, else the first downloaded, else the first available.
        val ms = get(ctx).models.filter { it.language == language && it.available }
        val pick = ModelPrefs.languageModel(ctx, language)?.let { id -> ms.firstOrNull { it.id == id } }
        if (pick != null && ModelStore.isReady(ctx, model = pick)) return pick
        return ms.firstOrNull { ModelStore.isReady(ctx, model = it) } ?: ms.firstOrNull()
    }

    /**
     * The model the keyboard uses: the user's pick if still available. Without a pick, a model
     * already on the phone (recommended first), so a user of an older build that defaulted to
     * stock keeps a working keyboard; then the recommended model (Sabich since 2026-10-21).
     */
    fun selected(ctx: Context): Model {
        val data = get(ctx)
        val pick = ModelPrefs.selectedModel(ctx)?.let { id -> data.models.firstOrNull { it.id == id && it.available && it.language == null } }
        if (pick != null) return pick
        val order = data.models.filter { it.available && it.language == null }
            .sortedBy { when (it.id) { data.recommended -> 0; data.default -> 1; else -> 2 } }
        return order.firstOrNull { ModelStore.isReady(ctx, model = it) } ?: order.first()
    }

    private fun strings(o: JSONObject, key: String): List<String> =
        o.optJSONArray(key)?.let { a -> (0 until a.length()).map { a.getString(it) } } ?: emptyList()

    /** Null if [s] is not a catalogue this app understands. */
    fun parse(s: String): Data? = runCatching {
        val o = JSONObject(s)
        if (o.getInt("schema") != SCHEMA) return null
        val files = strings(o.getJSONObject("engines").getJSONObject("sherpa_offline_transducer"), "files")
        val la = o.getJSONArray("lines")
        val lines = (0 until la.length()).map { i ->
            val l = la.getJSONObject(i)
            val va = l.getJSONArray("variants")
            Line(l.getString("id"), l.getString("name"), l.optString("summary"), l.optString("card").ifEmpty { null },
                (0 until va.length()).map { j ->
                    val m = va.getJSONObject(j)
                    Model(
                        id = m.getString("id"),
                        name = m.getString("name"),
                        summary = m.optString("summary").ifEmpty { l.optString("summary") },
                        status = m.optString("status", "planned"),
                        repo = m.optString("repo").ifEmpty { null },
                        subdir = m.optString("subdir").trim('/'),
                        card = m.optString("card").ifEmpty { null },
                        versionLabel = m.optString("version_label").ifEmpty { null },
                        manifestUrl = m.optString("manifest_url").ifEmpty { null },
                        line = l.getString("id"),
                        engine = m.optString("engine", "sherpa_offline_transducer"),
                        featureDim = m.optInt("feature_dim", 128),
                        baseModel = m.optString("base_model"),
                        baseLabel = m.optString("base_label"),
                        technical = m.optString("technical"),
                        platforms = strings(m, "platforms"),
                        hardware = m.optString("hardware"),
                        downloadMb = if (m.isNull("download_mb")) null else m.optInt("download_mb").takeIf { it > 0 },
                        speed = m.optInt("speed"),
                        accuracy = m.optInt("accuracy"),
                        recommendation = m.optString("recommendation"),
                        runsOn = m.optString("runs_on"),
                        language = (m.optString("language").ifEmpty { l.optString("language") }).ifEmpty { null },
                        modelType = m.optJSONObject("engine_options")?.optString("model_type").orEmpty(),
                        credit = m.optJSONObject("credit")?.let { c ->
                            Credit(c.optString("text"), c.optString("author"), c.optString("data"), c.optString("license"),
                                c.optString("license_url").ifEmpty { null }, c.optString("url").ifEmpty { null },
                                c.optString("original_url").ifEmpty { null }, c.optString("changes"))
                        }?.takeIf { it.text.isNotEmpty() },
                        offeredOn = if (m.has("offered_on")) strings(m, "offered_on") else null,
                    )
                })
        }
        val models = lines.flatMap { it.variants }.filter { it.supported }
        if (models.none { it.available && it.language == null } || files.isEmpty()) return null
        val recommended = o.optString("recommended").ifEmpty { models.first { it.available && it.language == null }.id }
        Data(o.optString("catalogue_v2_url").ifEmpty { null }, recommended, recommended, files,
            o.optString("version_file", "version.json"), models, lines)
    }.getOrNull()

    /**
     * Fetches the published catalogue and, if it parses, caches and uses it. Blocking; call from
     * a worker thread. A failure leaves the current catalogue in place and is not an error the
     * user needs to see: model updates still work from it.
     */
    fun refresh(ctx: Context) {
        val url = get(ctx).catalogueUrl ?: return
        val text = runCatching {
            val conn = URL(url).openConnection() as HttpURLConnection
            conn.connectTimeout = 15_000
            conn.readTimeout = 15_000
            try {
                if (conn.responseCode != HttpURLConnection.HTTP_OK) null
                else conn.inputStream.bufferedReader().use { it.readText() }
            } finally {
                conn.disconnect()
            }
        }.getOrNull() ?: return
        val data = parse(text) ?: return
        ModelPrefs.setCatalogueJson(ctx.applicationContext, text)
        cached = data
    }
}
