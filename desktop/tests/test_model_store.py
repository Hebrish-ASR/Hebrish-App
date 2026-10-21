"""Offline tests of the update decision and the install layout. Run: .venv/bin/python -m pytest tests"""

import json
import os
import shutil
import sys

import pytest

# conftest.py points XDG_* / APPDATA / LOCALAPPDATA at a temp dir before this is imported.
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from hebrish import model_store as ms  # noqa: E402

# Shape of GET /api/models/Hebrish/Parakeet-...-sherpa-onnx-int8/tree/<sha>, trimmed. Files sit at the
# repo root since 2026-10-19, when the app moved off the (now gated) main repo's sherpa-onnx/int8/.
TREE = [
    {"type": "file", "size": 12441, "path": "bpe.vocab"},
    {"type": "file", "size": 7, "path": "decoder.int8.onnx",
     "lfs": {"oid": "d" * 64, "size": 7}},
    {"type": "file", "size": 6, "path": "encoder.int8.onnx",
     "lfs": {"oid": "e" * 64, "size": 6}},
    {"type": "file", "size": 5, "path": "joiner.int8.onnx",
     "lfs": {"oid": "j" * 64, "size": 5}},
    {"type": "file", "size": 4, "path": "tokens.txt"},
    {"type": "file", "size": 35, "path": "version.json"},
]


# The stock repo also keeps its files at the root, and has no version.json.
STOCK_TREE = [{"type": "file", "size": e["size"], "path": e["path"].rsplit("/", 1)[-1],
               **({"lfs": e["lfs"]} if "lfs" in e else {})} for e in TREE[1:5]]
CS = ms.get_model("codeswitch")


def manifest(sha="a" * 40, version="v4", encoder_oid=None, model=CS):
    tree = json.loads(json.dumps(TREE))
    if encoder_oid:
        tree[2]["lfs"]["oid"] = encoder_oid
    return ms.manifest_from_tree(model, sha, tree, {"version": version, "run": "r4-en30"})


def install(m):
    d = ms.model_dir(m.model) / m.dirname
    d.mkdir(parents=True, exist_ok=True)
    for name, info in m.files.items():
        (d / name).write_bytes(b"x" * info["size"])
    (d / "manifest.json").write_text(json.dumps(m.to_json()))
    return d


@pytest.fixture(autouse=True)
def clean():
    shutil.rmtree(ms.MODELS_DIR.parent, ignore_errors=True)
    ms.select("codeswitch")
    yield


def test_parse_tree():
    m = manifest()
    assert set(m.files) == set(ms.FILES)
    assert m.files["tokens.txt"]["sha256"] is None       # plain git file, size only
    assert m.dirname == "v4-aaaaaaaaaaaa"
    assert m.label == "v4, r4-en30 (rev aaaaaaa)"


def test_label_without_version_json():
    m = ms.manifest_from_tree(CS, "b" * 40, TREE, None)
    assert m.version == "rev bbbbbbb" and m.dirname == "rev-bbbbbbbbbbbb"


def test_stock_root_level_tree_and_label():
    stock = ms.get_model("stock")
    assert stock.path("tokens.txt") == "tokens.txt" and stock.path() == ""
    assert CS.path("tokens.txt") == "tokens.txt"
    m = ms.manifest_from_tree(stock, "s" * 40, STOCK_TREE, None)
    assert m.model == "stock" and m.version == "v2"


def test_missing_file_is_an_error():
    with pytest.raises(RuntimeError):
        ms.manifest_from_tree(CS, "c" * 40, TREE[:2], None)


def test_main_moving_without_weight_change_is_not_an_update():
    install(manifest(sha="a" * 40))
    assert not ms.needs_update(manifest(sha="f" * 40))   # model-card commit


def test_changed_weights_are_an_update():
    install(manifest())
    assert ms.needs_update(manifest(sha="f" * 40, version="v5", encoder_oid="9" * 64))


def test_nothing_installed_needs_download():
    assert ms.needs_update(manifest())


def test_active_follows_state_and_prune_keeps_only_new():
    old = install(manifest(sha="1" * 40, version="v3"))
    new = install(manifest(sha="2" * 40, version="v4", encoder_oid="9" * 64))
    ms.set_active(old.name)
    assert ms.active()[0] == old
    (ms.model_dir("codeswitch") / "v5-half").mkdir()      # abandoned partial download
    ms.prune_except(new.name)
    assert [d for d, _ in ms.installed()] == [new]
    assert not (ms.model_dir("codeswitch") / "v5-half").exists()
    assert ms.active()[0] == new                          # state points at a deleted dir


def test_download_with_files_present_keeps_old():
    old = install(manifest(sha="1" * 40, version="v3"))
    m = manifest(sha="2" * 40, version="v4", encoder_oid="9" * 64)
    d = install(m)
    (d / "manifest.json").unlink()                        # files there, not yet committed
    assert ms.download(m, keep_old=True) == d             # no network: every file present
    assert ms.active()[0] == d and old.exists()


def test_download_replace_deletes_old():
    old = install(manifest(sha="1" * 40, version="v3"))
    m = manifest(sha="2" * 40, version="v4", encoder_oid="9" * 64)
    d = install(m)
    (d / "manifest.json").unlink()
    ms.download(m, keep_old=False)
    assert not old.exists()


def test_remove_refuses_paths_outside_models_dir():
    ms.model_dir("codeswitch").mkdir(parents=True)
    with pytest.raises(ValueError):
        ms.remove("../state.json")
    with pytest.raises(ValueError):
        ms.remove("../stock")
    with pytest.raises(ValueError):
        ms.remove_model("..")


def test_models_are_isolated():
    cs = install(manifest())
    stock = install(ms.manifest_from_tree(ms.get_model("stock"), "s" * 40, STOCK_TREE, None))
    assert sorted(ms.installed_ids()) == ["codeswitch", "stock"]   # catalogue order
    ms.prune_except(cs.name, "codeswitch")
    assert stock.exists()                                 # pruning one model never touches another
    ms.select("stock")
    assert ms.active()[0] == stock and ms.active("codeswitch")[0] == cs
    # same files, different model: never "the same weights"
    assert not ms.active("stock")[1].same_weights(ms.active("codeswitch")[1])


def test_planned_models_cannot_be_selected_or_fetched():
    # Hebrish's catalogue lists no planned model, so use a made-up one.
    planned = ms.Model("planned-test", "Planned", "", "planned")
    assert not planned.available
    with pytest.raises(ValueError):
        ms.select(planned.id)
    with pytest.raises(RuntimeError):
        ms.fetch_latest(planned.id)


def test_bad_cached_catalogue_falls_back_to_bundled():
    ms.save_json(ms.CATALOGUE_CACHE, {"schema": 99, "models": []})
    assert ms.get_model("stock") is not None
    ms.save_json(ms.CATALOGUE_CACHE, {**json.loads(ms.BUNDLED_CATALOGUE.read_text()),
                                      "models": [{"id": "x", "name": "X", "status": "available", "repo": "a/b"}],
                                      "default": "x"})
    assert [m.id for m in ms.models()] == ["x"]           # a newer published catalogue wins
    ms.CATALOGUE_CACHE.unlink()


def test_legacy_voice_to_hebrish_install_is_adopted(monkeypatch):
    from hebrish import config
    old_data = config.DATA_DIR.with_name(config._LEGACY[0])     # VoiceToHebrish on Windows
    old_cfg = config.CONFIG_DIR.with_name(config._LEGACY[0])
    m = manifest()
    d = old_data / "models" / m.dirname
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({k: v for k, v in m.to_json().items() if k != "model"}))
    old_cfg.mkdir(parents=True, exist_ok=True)
    (old_cfg / "config.json").write_text(json.dumps({"hotkey": "KEY_F14", "junk": 1}))
    config.CONFIG_PATH.unlink(missing_ok=True)
    config.migrate_legacy()
    assert json.loads(config.CONFIG_PATH.read_text()) == {"hotkey": "KEY_F14", **{"feedback": "beeps", "keep_history": False, "live_insert_s": 10}}
    assert ms.current_id() == "codeswitch"
    assert ms.active()[0].name == m.dirname and ms.active()[1].model == "codeswitch"
    shutil.rmtree(old_data)
    shutil.rmtree(old_cfg)


CDN_DOC = {"schema": 1, "model": "codeswitch", "version": "v1.0", "run": "r6-en30",
           "revision": "b" * 40, "base_url": "https://cdn.hebrish.app/models/parakeet-codeswitch/v1.0/sherpa-onnx-int8",
           "files": {e["path"]: {"size": e["size"], "sha256": (e.get("lfs") or {}).get("oid")}
                     for e in TREE if e["path"] in ms.FILES}}


def test_cdn_manifest_and_url():
    m = ms.manifest_from_cdn(CS, CDN_DOC)
    assert m.version == "v1.0" and m.base_url.endswith("/sherpa-onnx-int8/")
    assert ms.Manifest.from_json(m.to_json()).base_url == m.base_url
    # same weights as the Hugging Face build of the same files: no re-download
    assert m.same_weights(manifest(sha="b" * 40))


def test_cdn_manifest_missing_file_is_an_error():
    doc = json.loads(json.dumps(CDN_DOC)); doc["files"].pop("joiner.int8.onnx")
    with pytest.raises(RuntimeError):
        ms.manifest_from_cdn(CS, doc)


def test_custom_model_folder(tmp_path):
    """Settings, "Where the models are stored" (0.5.0): every lookup follows set_root."""
    from hebrish import config
    assert config.models_root({"models_dir": ""}) == config.MODELS_DIR
    assert config.models_root({"models_dir": str(tmp_path)}) == tmp_path
    try:
        ms.set_root(tmp_path)
        d = install(manifest())
        assert tmp_path in d.parents and ms.installed_ids() == ["codeswitch"]
        ms.remove_model("codeswitch")
        assert not d.exists()
    finally:
        ms.set_root(config.MODELS_DIR)


def test_one_version_per_model_by_default():
    """0.5.1 (Daniel, 2026-10-21): an update replaces the old version, and old versions kept by
    earlier releases are cleared at start (prune_all), the active one always kept."""
    old = install(manifest(sha="1" * 40, version="v3"))
    m = manifest(sha="2" * 40, version="v4", encoder_oid="9" * 64)
    d = install(m)
    (d / "manifest.json").unlink()
    ms.download(m)                                        # default: replace
    assert not old.exists() and ms.active()[0] == d
    older = install(manifest(sha="3" * 40, version="v2", encoder_oid="8" * 64))
    ms.set_active(d.name)
    assert ms.prune_all() > 0
    assert not older.exists() and d.exists()


def test_upgrade_drops_keep_old_versions_and_turns_on_auto_update():
    from hebrish.config import upgrade
    out = upgrade({"feedback": "beeps", "keep_old_versions": True, "auto_update": False})
    assert out == {"feedback": "beeps", "auto_update": True}
