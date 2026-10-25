"""Both apps read the model catalogue from shared/: catalogue.json (schema 2, Android 0.7.0+ and
desktop 0.6.0+) and models.json (schema 1, older builds, which reject any other schema)."""

import json
import os
import re
import sys

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
        v = by_id[m["id"]]
        for key in ("repo", "subdir", "manifest_url", "version_label", "status"):
            assert m.get(key, "") == v.get(key, ""), (m["id"], key)
        assert v["engine"] == "sherpa_offline_transducer"
    assert old["recommended"] == v2()["recommended"]
    assert old["files"] == v2()["engines"]["sherpa_offline_transducer"]["files"]


def test_android_offline_fallbacks_are_available_models():
    ids = set(re.findall(r'"(\w+)" to Manifest\(', open(os.path.join(KT, "ModelStore.kt")).read()))
    available = {v["id"] for v in all_variants() if v["status"] == "available"}
    assert ids and ids <= available


def test_hebrish_ships_only_code_switching_lines_and_stock():
    """Hebrish is the code-switching app: Sabich (everything, recommended, first), Jachnun
    (code-switching only), Shakshuka (streaming, trained on Sabich's blend) and stock Parakeet last.
    The fine-tunes without Hebrew (Boxty, tech, personal) belong to Parlance
    (danielrosehill/Parlance-Dictation). Schema 1 keeps its three models."""
    assert [ln["id"] for ln in v2()["lines"]] == ["sabich", "jachnun", "shakshuka", "stock"]
    assert v2()["lines"][0]["variants"][0]["id"] == v2()["recommended"] == "sabich"
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
    idmap = {"jachnun": "codeswitch"}
    by_id = {v["id"]: v for v in all_variants()}
    for sv in site["variants"]:
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
UPDATES = os.path.join(ROOT, "shared", "updates.json")


def test_updates_are_bundled_by_both_apps():
    from hebrish.ui import about
    assert open(about.UPDATES).read() == open(UPDATES).read(), \
        "run scripts/bake_updates.py (it writes both copies)"
    assert "../shared/updates.json" in open(os.path.join(ANDROID, "build.gradle.kts")).read()
    assert "data/updates.json" in open(os.path.join(ROOT, "desktop", "pyproject.toml")).read()


def test_updates_are_well_formed():
    doc = json.load(open(UPDATES))
    entries = doc["entries"]
    assert doc["schema"] == 1 and 0 < len(entries) <= 20
    dates = [e["date"] for e in entries]
    assert dates == sorted(dates, reverse=True) and dates[0] <= doc["built"]
    for e in entries:
        assert e["title"] and e["summary"] and len(e["summary"]) <= 281, e
        assert "<" not in e["title"] + e["summary"], e


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
                               "summary": 'It can leave "word. Capital" now. Second sentence.'}]
