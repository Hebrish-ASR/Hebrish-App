"""Offline tests of the update decision and the install layout. Run: .venv/bin/python -m pytest tests"""

import json
import os
import shutil
import sys
import tempfile

import pytest

os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from voice_to_hebrish import model_store as ms  # noqa: E402

# Shape of GET /api/models/<repo>/tree/<sha>/sherpa-onnx/int8, trimmed (live 2026-10-18).
TREE = [
    {"type": "file", "size": 12441, "path": "sherpa-onnx/int8/bpe.vocab"},
    {"type": "file", "size": 7, "path": "sherpa-onnx/int8/decoder.int8.onnx",
     "lfs": {"oid": "d" * 64, "size": 7}},
    {"type": "file", "size": 6, "path": "sherpa-onnx/int8/encoder.int8.onnx",
     "lfs": {"oid": "e" * 64, "size": 6}},
    {"type": "file", "size": 5, "path": "sherpa-onnx/int8/joiner.int8.onnx",
     "lfs": {"oid": "j" * 64, "size": 5}},
    {"type": "file", "size": 4, "path": "sherpa-onnx/int8/tokens.txt"},
    {"type": "file", "size": 35, "path": "sherpa-onnx/int8/version.json"},
]


def manifest(sha="a" * 40, version="v4", encoder_oid=None):
    tree = json.loads(json.dumps(TREE))
    if encoder_oid:
        tree[2]["lfs"]["oid"] = encoder_oid
    return ms.manifest_from_tree(sha, tree, {"version": version, "run": "r4-en30"})


def install(m):
    d = ms.MODELS_DIR / m.dirname
    d.mkdir(parents=True, exist_ok=True)
    for name, info in m.files.items():
        (d / name).write_bytes(b"x" * info["size"])
    (d / "manifest.json").write_text(json.dumps(m.to_json()))
    return d


@pytest.fixture(autouse=True)
def clean():
    shutil.rmtree(ms.MODELS_DIR.parent, ignore_errors=True)
    yield


def test_parse_tree():
    m = manifest()
    assert set(m.files) == set(ms.FILES)
    assert m.files["tokens.txt"]["sha256"] is None       # plain git file, size only
    assert m.dirname == "v4-aaaaaaaaaaaa"
    assert m.label == "v4, r4-en30 (rev aaaaaaa)"


def test_label_without_version_json():
    m = ms.manifest_from_tree("b" * 40, TREE, None)
    assert m.version == "rev bbbbbbb" and m.dirname == "rev-bbbbbbbbbbbb"


def test_missing_file_is_an_error():
    with pytest.raises(RuntimeError):
        ms.manifest_from_tree("c" * 40, TREE[:2], None)


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
    (ms.MODELS_DIR / "v5-half").mkdir()                   # abandoned partial download
    ms.prune_except(new.name)
    assert [d for d, _ in ms.installed()] == [new]
    assert not (ms.MODELS_DIR / "v5-half").exists()
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
    ms.MODELS_DIR.mkdir(parents=True)
    with pytest.raises(ValueError):
        ms.remove("../state.json")
