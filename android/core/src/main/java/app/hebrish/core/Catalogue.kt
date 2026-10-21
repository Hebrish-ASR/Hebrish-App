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
 * holds every variant, for the Models screen, which lists the others greyed with where they run.
 */
object Catalogue {
    const val ASSET = "catalogue.json"
    const val SCHEMA = 2
    const val PLATFORM = "android"
    /** Engines this build can run. Phase 2 adds sherpa_online_transducer (Shakshuka). */
    val SUPPORTED_ENGINES = setOf("sherpa_offline_transducer")

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
    ) {
        /** This build can run it. */
        val supported: Boolean get() = engine in SUPPORTED_ENGINES && PLATFORM in platforms
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

    /**
     * The model the keyboard uses: the user's pick if still available. Without a pick, a model
     * already on the phone (recommended first), so a user of an older build that defaulted to
     * stock keeps a working keyboard; then the recommended model (Sabich since 2026-10-21).
     */
    fun selected(ctx: Context): Model {
        val data = get(ctx)
        val pick = ModelPrefs.selectedModel(ctx)?.let { id -> data.models.firstOrNull { it.id == id && it.available } }
        if (pick != null) return pick
        val order = data.models.filter { it.available }
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
                        platforms = strings(m, "platforms"),
                        hardware = m.optString("hardware"),
                        downloadMb = if (m.isNull("download_mb")) null else m.optInt("download_mb").takeIf { it > 0 },
                        speed = m.optInt("speed"),
                        accuracy = m.optInt("accuracy"),
                        recommendation = m.optString("recommendation"),
                        runsOn = m.optString("runs_on"),
                    )
                })
        }
        val models = lines.flatMap { it.variants }.filter { it.supported }
        if (models.none { it.available } || files.isEmpty()) return null
        val recommended = o.optString("recommended").ifEmpty { models.first { it.available }.id }
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
