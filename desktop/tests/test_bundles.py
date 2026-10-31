"""B-79: model bundles and Update all (hebrish/bundles.py)."""

from hebrish import bundles as B, cleanup, model_store, paragraphs


def test_catalogue_bundles_name_real_models_and_addons():
    doc = model_store.bundled_catalogue()
    speech = {v["id"] for ln in doc["lines"] for v in ln["variants"]}
    addons = {a["id"] for a in doc["addons"]} | {paragraphs.MODEL_ID}
    bs = [b for b in doc["bundles"] if b.get("id")]
    assert bs and sum(bool(b.get("default")) for b in bs) == 1
    for b in bs:
        assert set(b["models"]) <= speech, b["id"]
        assert set(b["addons"]) <= addons, b["id"]


def test_default_bundle_first_and_android_only_items_skipped(monkeypatch):
    real = model_store.bundled_catalogue()
    monkeypatch.setattr(model_store, "catalogue", lambda: {**real, "bundles": [
        {"id": "x", "name": "X", "models": ["sabich-asr4all-s"], "addons": []},       # Android only
        {"id": "a", "name": "A", "models": ["sabich", "sabich-asr4all-s"], "addons": ["nope"]},
        {"id": "d", "name": "D", "models": ["sabich"], "addons": [], "default": True}]})
    assert [b["id"] for b in B.bundles()] == ["d", "a"]
    assert B.items(B.get("a")) == (["sabich"], [])


def test_missing_lists_only_what_is_not_downloaded(monkeypatch):
    b = {"id": "t", "models": ["sabich", "shakshuka"], "addons": ["title-gemma-270m", paragraphs.MODEL_ID]}
    monkeypatch.setattr(model_store, "installed", lambda m=None: [("x", None)] if m == "sabich" else [])
    monkeypatch.setattr(B, "addon_installed", lambda a: a == paragraphs.MODEL_ID)
    assert B.missing(b) == (["shakshuka"], ["title-gemma-270m"])


def test_check_covers_every_downloaded_model_and_keeps_going_after_a_failure(monkeypatch):
    class M:
        def __init__(self, mid): self.model = mid
    def latest(mid):
        if mid == "codeswitch":
            raise OSError("offline")
        return M(mid)
    monkeypatch.setattr(model_store, "installed_ids", lambda: ["sabich", "codeswitch", "shakshuka"])
    monkeypatch.setattr(model_store, "fetch_latest", latest)
    monkeypatch.setattr(model_store, "needs_update", lambda m: m.model == "shakshuka")
    monkeypatch.setattr(B, "_addon_stale", lambda a: a == "title-gemma-270m")
    monkeypatch.setattr(B, "_paragraphs_stale", lambda: True)
    ups = B.check()
    assert [m.model for m in ups.models] == ["shakshuka"]
    assert ups.addons == ["title-gemma-270m", paragraphs.MODEL_ID]
    assert ups.errors == [("codeswitch", "offline")] and len(ups) == 3


def test_addon_stale_only_with_an_older_version_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(model_store, "ROOT", tmp_path)
    monkeypatch.setattr(cleanup, "installed", lambda a: None)
    assert not B._addon_stale("title-gemma-270m")                  # never downloaded
    old = tmp_path / "title-gemma-270m" / "v0"
    old.mkdir(parents=True)
    (old / "manifest.json").write_text("{}")
    assert B._addon_stale("title-gemma-270m")
