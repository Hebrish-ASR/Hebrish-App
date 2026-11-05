"""Both apps read the model catalogue from shared/: catalogue.json (schema 2, Android 0.7.0+ and
desktop 0.6.0+) and models.json (schema 1, older builds, which reject any other schema)."""

import functools
import json
import os
import re
import sys

import pytest

open = functools.partial(open, encoding="utf-8")     # Windows defaults to cp1252

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "desktop"))

from hebrish import model_store  # noqa: E402

SHARED = os.path.join(ROOT, "shared", "catalogue.json")
SHARED_V1 = os.path.join(ROOT, "shared", "models.json")
ANDROID = os.path.join(ROOT, "android", "app")
KT = os.path.join(ANDROID, "..", "core", "src", "main", "java", "app", "hebrish", "core")
ENGINES = {"sherpa_offline_transducer", "sherpa_online_transducer", "qwen3_asr", "asr4all", "nemo_salm"}


def v2():
    return json.load(open(SHARED))


def all_variants():
    return [v for ln in v2()["lines"] for v in ln["variants"]]


def test_desktop_bundles_the_shared_catalogue():
    """desktop/hebrish/data/catalogue.json is a copy (PyInstaller and the .deb need it inside the
    package). After editing shared/catalogue.json: cp shared/catalogue.json desktop/hebrish/data/"""
    assert open(model_store.BUNDLED_CATALOGUE).read() == open(SHARED).read()


def test_android_bundles_the_shared_catalogue():
    """The APK's assets/catalogue.json is copied from shared/ at build time, never by hand."""
    assert "../shared/catalogue.json" in open(os.path.join(ANDROID, "build.gradle.kts")).read()
    src = open(os.path.join(KT, "Catalogue.kt")).read()
    schema = re.search(r"const val SCHEMA = (\d+)", src)
    assert schema and int(schema.group(1)) == v2()["schema"] == 2
    engines = set(re.findall(r'"(\w+)"', re.search(r"SUPPORTED_ENGINES = setOf\(([^)]*)\)", src).group(1)))
    # Same engines on both apps, except streaming: desktop first (Daniel, 2026-10-22), Android
    # follows (planning/backlog.md B-13). Remove the exception when Android adds it.
    assert engines | {"sherpa_online_transducer"} == model_store.SUPPORTED_ENGINES


def test_catalogue_v2_url_points_at_this_file():
    assert v2()["catalogue_v2_url"].endswith("/Hebrish-App/main/shared/catalogue.json")


def test_variants_are_well_formed():
    doc = v2()
    ids = [v["id"] for v in all_variants()]
    assert len(ids) == len(set(ids)), "variant ids are folder names: unique and permanent"
    assert doc["recommended"] in ids
    for v in all_variants():
        assert v["engine"] in ENGINES and v["engine"] in doc["engines"], v["id"]
        assert v["status"] in ("available", "planned"), v["id"]
        assert set(v["platforms"]) <= {"android", "linux", "windows"} and v["platforms"], v["id"]
        assert set(v["devices"]) <= {"wearable", "phone", "desktop"} and v["devices"], v["id"]
        assert 1 <= v["speed"] <= 5 and 1 <= v["accuracy"] <= 5 and 0 <= v["gradient"] <= 100, v["id"]
        if v["engine"] == "sherpa_offline_transducer":
            assert v["feature_dim"] in (80, 128), v["id"]
        assert v["recommendation"] and len(v["recommendation"]) <= 110, v["id"]
        assert v["hardware"] and v["card"], v["id"]
        gpu = v["requirements"]["gpu"]
        assert gpu is None or (gpu["vram_gb"] > 0 and gpu["backends"]), v["id"]
        if v["engine"] not in model_store.SUPPORTED_ENGINES:
            assert v.get("runs_on"), f"{v['id']}: an unsupported engine needs runs_on"
        if v["status"] == "available" and v["engine"] in model_store.SUPPORTED_ENGINES:
            assert v.get("repo") or v.get("manifest_url"), v["id"]


def test_schema1_models_match_their_v2_variants():
    """Old builds still read models.json: every model there must be the same download here."""
    old = json.load(open(SHARED_V1))
    assert old["schema"] == 1
    by_id = {v["id"]: v for v in all_variants()}
    for m in old["models"]:
        if m["id"] in ("codeswitch", "sabich"):  # Jachnun, and the schema-1 Sabich entry: kept for old builds, out of schema 2 since 2026-11-04
            continue
        v = by_id[m["id"]]
        for key in ("repo", "subdir", "manifest_url", "version_label", "status"):
            assert m.get(key, "") == v.get(key, ""), (m["id"], key)
        assert v["engine"] == "sherpa_offline_transducer"
    # 2026-11-02: schema 1 cannot list Sabich (Rolling), so old builds keep recommending Sabich.
    assert old["recommended"] in [m["id"] for m in old["models"]]
    assert old["recommended"] == v2()["recommended"] or v2()["recommended"] == "sabich-rolling"
    assert old["files"] == v2()["engines"]["sherpa_offline_transducer"]["files"]


def test_android_offline_fallbacks_are_available_models():
    ids = set(re.findall(r'"(\w+)" to Manifest\(', open(os.path.join(KT, "ModelStore.kt")).read()))
    available = {v["id"] for v in all_variants() if v["status"] == "available"}
    assert ids and ids - {"codeswitch"} <= available  # Jachnun stays a fallback until the next Android release


def test_hebrish_ships_only_code_switching_lines_and_stock():
    """Hebrish is the code-switching app: Sabich (everything; Sabich (Rolling) recommended and first), Shakshuka
    (streaming, trained on Sabich's blend) and stock Parakeet last. Jachnun left the apps on 2026-11-04 (Daniel: two active models).
    The fine-tunes without Hebrew (Boxty, tech, personal) belong to Parlance
    (danielrosehill/Parlance-Dictation). Schema 1 keeps its three models."""
    assert [ln["id"] for ln in v2()["lines"]] == ["sabich", "shakshuka", "stock"]
    # Daniel, 2026-11-02: Sabich (Rolling) is the default while he tests it; Sabich stays in the line.
    assert v2()["lines"][0]["variants"][0]["id"] == v2()["recommended"] == "sabich-rolling"
    assert v2()["lines"][0]["variants"][0]["name"] == "Sabich"
    assert "sabich" not in [v["id"] for v in v2()["lines"][0]["variants"]]   # Stable left 2026-11-04 (Daniel)
    assert set(v2()["recommended_by_platform"].values()) - {v2()["recommended_by_platform"]["_doc"]} == {"sabich-rolling"}
    assert not any("boxty" in v["id"] or v["id"] in ("tech", "personal") for v in all_variants())
    with open(SHARED_V1) as f:
        assert [m["id"] for m in json.load(f)["models"]] == ["sabich", "codeswitch", "stock"]


def test_chooser_rules_name_catalogue_variants():
    ids = {v["id"] for v in all_variants()}
    rules = v2()["chooser"]["rules"]
    assert rules[-1]["when"] == {}, "the last rule is the catch-all"
    for r in rules:
        assert r["pick"] in ids and r.get("runner_up", r["pick"]) in ids, r
        assert set(r["when"]) <= {"device", "gpu", "vram", "priority", "live"}, r


SITE = os.path.join(ROOT, "..", "Hebrish-App", "data", "variants.json")   # hebrish.app (Hebrish-Website)


def test_numbers_and_rules_match_the_website():
    """hebrish.app/models/choose and the apps must agree (2026-10-21). Runs only where the
    website repo is checked out next to this one (not in CI)."""
    import pytest
    if not os.path.exists(SITE):
        pytest.skip("website repo not checked out")
    site = json.load(open(SITE))
    idmap = {"jachnun": "codeswitch", "sabich": "sabich-rolling"}
    by_id = {v["id"]: v for v in all_variants()}
    for sv in site["variants"]:
        if sv["id"] == "jachnun":  # on the site as an experimental test; not in the apps since 2026-11-04
            continue
        v = by_id[idmap.get(sv["id"], sv["id"])]
        assert (v["speed"], v["accuracy"], v["gradient"]) == (sv["speed"], sv["accuracy"], sv["gradient"]), sv["id"]
    mapped = [{**r, "pick": idmap.get(r["pick"], r["pick"]),
               **({"runner_up": idmap.get(r["runner_up"], r["runner_up"])} if "runner_up" in r else {})}
              for r in site["rules"]]
    assert mapped == v2()["chooser"]["rules"]


# -- plain model descriptions (2026-10-25) ------------------------------------------------------
JARGON = re.compile(r"\b(bf16|f16|fp16|int8|q8_0|q4_k_m|gguf|onnx|pytorch|transformers|llama\.cpp|nemo|sherpa|"
                    r"cuda|rocm|hip|vulkan|vram|ctc|runtime)\b|/", re.I)


def test_what_users_see_is_plain_language():
    """Daniel, 2026-10-25: the Models screens are for regular people. What they show (base_label,
    hardware, recommendation, runs_on) has no repo ids, formats or runtimes; those go in
    `technical` (and base_model, repo), shown only under Technical details."""
    for v in all_variants():
        assert v.get("base_label") and " by " in v["base_label"], v["id"]
        for key in ("base_label", "hardware", "recommendation", "runs_on"):
            assert not JARGON.search(v.get(key, "")), (v["id"], key, v.get(key))


# -- What's new, baked at build time (2026-10-25) -----------------------------------------------
# One list per app (2026-10-31): Android's in shared/, copied into the APK; the desktop's in its package
# (the path, without importing the Qt UI: CI's test job has no PySide6).
UPDATES = {"android": (os.path.join(ROOT, "shared", "updates-android.json"), {"android"}),
           "desktop": (os.path.join(ROOT, "desktop", "hebrish", "data", "updates.json"), {"desktop", "site"})}


def test_updates_are_bundled_by_both_apps():
    assert '"../shared/updates-android.json"' in open(os.path.join(ANDROID, "build.gradle.kts")).read()
    assert "data/updates.json" in open(os.path.join(ROOT, "desktop", "pyproject.toml")).read()
    assert not os.path.exists(os.path.join(ROOT, "shared", "updates.json")), "retired 2026-10-31: one list per app"


@pytest.mark.parametrize("platform", sorted(UPDATES))
def test_updates_are_well_formed(platform):
    path, shown = UPDATES[platform]
    doc = json.load(open(path))
    entries = doc["entries"]
    assert doc["schema"] == 1 and doc["platform"] == platform and 0 < len(entries) <= 20
    # Only this app's entries: "updates should only be related to Android on Android".
    assert all(shown & set(e["platforms"]) for e in entries), [e["title"] for e in entries if not shown & set(e["platforms"])]
    dates = [e["date"] for e in entries]
    assert dates == sorted(dates, reverse=True) and dates[0] <= doc["built"]
    for e in entries:
        assert e["title"] and e["summary"] and len(e["summary"]) <= 281, e
        # No leftover markup. A literal "<" is fine: entities are decoded on purpose, so the
        # 2026-10-25 entry "no more <unk>" is text, not a tag.
        assert not re.search(r"</?(a|b|i|em|strong|code|span|p|ul|ol|li|br|h[1-6]|time|article|div)\b[^>]*>",
                             e["title"] + e["summary"]), e


def test_bake_reads_the_changelog_markup():
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import bake_updates
    page = """<article class="log"><p class="log-meta"><time datetime="2026-10-26">2026-10-26</time>
      <span class="tag">Apps 1.004</span></p><h3>Future</h3><ul><li>Not yet.</li></ul></article>
      <article class="log"><p class="log-meta"><time datetime="2026-10-25">2026-10-25</time>
      <span class="tag">Models</span> <span class="tag">Site</span></p><h3>A &amp; B</h3>
      <ul><li>It can leave "word. Capital" now. <a href="/x">Second</a> sentence. Third one.</li><li>Other.</li></ul></article>"""
    doc = bake_updates.bake(page, "2026-10-25", 20, "test")
    assert doc["entries"] == [{"date": "2026-10-25", "tag": "Models · Site", "title": "A & B",
                               "summary": 'It can leave "word. Capital" now. Second sentence.',
                               "platforms": ["models", "site"]}]


def test_bake_keeps_each_apps_own_entries():
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import bake_updates
    page = """<article class="log" data-platforms="android desktop models"><time datetime="2026-10-30"></time>
      <span class="tag">Models</span><h3>Sabich</h3><ul><li>New model.</li></ul></article>
      <article class="log" data-platforms="desktop"><time datetime="2026-10-30"></time>
      <span class="tag">Desktop 1.013</span><h3>Desk</h3><ul><li>Desktop.</li></ul></article>
      <article class="log" data-platforms="models"><time datetime="2026-10-29"></time>
      <span class="tag">Models</span><h3>TTS</h3><ul><li>Not in the apps.</li></ul></article>
      <article class="log"><time datetime="2026-10-28"></time>
      <span class="tag">Android 1.007</span><h3>Phone</h3><ul><li>No attribute: from the tag.</li></ul></article>
      <article class="log"><time datetime="2026-10-27"></time><h3>Site</h3><ul><li>Untagged.</li></ul></article>"""
    titles = lambda p: [e["title"] for e in bake_updates.bake(page, "2026-10-31", 20, "test", p)["entries"]]
    assert titles("android") == ["Sabich", "Phone"]
    assert titles("desktop") == ["Sabich", "Desk", "Site"]
    assert titles("") == ["Sabich", "Desk", "TTS", "Phone", "Site"]


# -- Text transformation prompt library, shipped as data only (2026-11-02, I-18) -------------------
PROMPTS = os.path.join(ROOT, "shared", "text-transformation-prompts.json")


def test_transformation_prompts_are_bundled_by_both_apps():
    """Written by scripts/import_transformation_prompts.py into shared/ and the desktop package;
    the APK copies the shared file into its assets at build time."""
    assert open(os.path.join(ROOT, "desktop", "hebrish", "data", "text-transformation-prompts.json")).read() == open(PROMPTS).read()
    assert '"../shared/text-transformation-prompts.json"' in open(os.path.join(ANDROID, "build.gradle.kts")).read()
    assert "data/text-transformation-prompts.json" in open(os.path.join(ROOT, "desktop", "pyproject.toml")).read()


def test_transformation_prompts_are_well_formed():
    doc = json.load(open(PROMPTS))
    prompts = doc["prompts"]
    assert doc["schema"] == 2 and doc["count"] == len(prompts) > 0
    assert all(p["type"] in doc["types"] and p["style"] in doc["styles"] and p["label"] for p in prompts)
    ids = [p["id"] for p in prompts]
    assert len(ids) == len(set(ids)) and all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", i) for i in ids)
    assert all(p["name"] and p["prompt"] and p["structured_output"] in (True, False, None) for p in prompts)
