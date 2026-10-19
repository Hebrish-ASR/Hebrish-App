package app.hebrish.core

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * The model catalogue, shared/models.json. The APK carries a copy in its assets ([ASSET], copied
 * by the gradle `copyCatalogue` task). Each update check also fetches `catalogue_url`; a copy that
 * parses with schema [SCHEMA] is cached in Prefs and wins over the bundled one, so a newly
 * published model appears without an APK release.
 */
object Catalogue {
    const val ASSET = "models.json"
    const val SCHEMA = 1

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
    ) {
        /** Listed but not downloadable: "planned" models show as coming soon. */
        val available: Boolean get() = status == "available" && !(repo.isNullOrEmpty() && manifestUrl.isNullOrEmpty())
    }

    data class Data(
        val catalogueUrl: String?,
        val default: String,
        val files: List<String>,
        val versionFile: String,
        val models: List<Model>,
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

    /** The model the keyboard uses: the user's pick if still available, else the catalogue default. */
    fun selected(ctx: Context): Model {
        val data = get(ctx)
        val pick = ModelPrefs.selectedModel(ctx)?.let { id -> data.models.firstOrNull { it.id == id && it.available } }
        return pick ?: data.models.firstOrNull { it.id == data.default && it.available }
            ?: data.models.first { it.available }
    }

    /** Null if [s] is not a catalogue this app understands. */
    fun parse(s: String): Data? = runCatching {
        val o = JSONObject(s)
        if (o.getInt("schema") != SCHEMA) return null
        val files = o.getJSONArray("files").let { a -> (0 until a.length()).map { a.getString(it) } }
        val arr = o.getJSONArray("models")
        val models = (0 until arr.length()).map { i ->
            val m = arr.getJSONObject(i)
            Model(
                id = m.getString("id"),
                name = m.getString("name"),
                summary = m.optString("summary"),
                status = m.optString("status", "planned"),
                repo = m.optString("repo").ifEmpty { null },
                subdir = m.optString("subdir").trim('/'),
                card = m.optString("card").ifEmpty { null },
                versionLabel = m.optString("version_label").ifEmpty { null },
                manifestUrl = m.optString("manifest_url").ifEmpty { null },
            )
        }
        if (models.none { it.available }) return null
        Data(o.optString("catalogue_url").ifEmpty { null }, o.getString("default"), files,
            o.optString("version_file", "version.json"), models)
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
