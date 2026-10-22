"""First-start import from Parlance (config.import_parlance, 2026-10-19).

Hebrish runs alongside Parlance, so the import copies and never moves: Parlance's dirs must be
intact afterwards, models hardlinked where the filesystem allows. Every path is redirected into
tmp_path with monkeypatch (and conftest.py already points XDG_*/APPDATA at a temp dir)."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from hebrish import config  # noqa: E402

VERSION = "v4-edbc85c1ce89"
ENCODER = os.path.join("models", "codeswitch", VERSION, "encoder.int8.onnx")


def _parlance_install(root):
    cfg = root / "config" / config.PARLANCE
    data = root / "data" / config.PARLANCE
    (data / "models" / "codeswitch" / VERSION).mkdir(parents=True)
    (data / ENCODER).write_bytes(b"x" * 10)
    (data / "models" / "codeswitch" / VERSION / "manifest.json").write_text("{}")
    (data / "state.json").write_text('{"model": "codeswitch"}')
    (data / "history.json").write_text('[{"text": "boker tov"}]')
    (data / "venv").mkdir()                                     # install.sh's venv: not copied
    cfg.mkdir(parents=True)
    (cfg / "config.json").write_text(json.dumps({"hotkey": "KEY_F13", "mode": "toggle", "junk": 1}))
    return cfg, data


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    new = "Hebrish" if sys.platform == "win32" else "hebrish"
    cfg, data = tmp_path / "config" / new, tmp_path / "data" / new
    for name, value in {"CONFIG_DIR": cfg, "DATA_DIR": data, "CONFIG_PATH": cfg / "config.json",
                        "STATE_PATH": data / "state.json", "MODELS_DIR": data / "models"}.items():
        monkeypatch.setattr(config, name, value)
    return tmp_path


def test_parlance_is_copied_and_left_intact(dirs):
    old_cfg, old_data = _parlance_install(dirs)
    assert config.import_parlance() is True
    # Parlance untouched
    assert json.loads((old_cfg / "config.json").read_text())["hotkey"] == "KEY_F13"
    assert (old_data / ENCODER).read_bytes() == b"x" * 10
    assert (old_data / "state.json").is_file() and (old_data / "history.json").is_file()
    # Hebrish got settings minus the hotkey (and minus unknown keys), state, history, models
    assert json.loads(config.CONFIG_PATH.read_text()) == {"hold_to_talk": False, **{"feedback": "beeps", "keep_history": True, "live_insert_s": 7}}   # mode upgraded, 0.5.0 defaults, 0.7.0 Normal and history
    assert config.DEFAULTS["hotkey"] == "KEY_F14"
    assert json.loads(config.STATE_PATH.read_text()) == {"model": "codeswitch"}
    assert (config.DATA_DIR / "history.json").read_text() == '[{"text": "boker tov"}]'
    new_enc = config.DATA_DIR / ENCODER
    assert new_enc.read_bytes() == b"x" * 10
    assert (config.MODELS_DIR / "codeswitch" / VERSION / "manifest.json").is_file()
    assert not (config.DATA_DIR / "venv").exists()


def test_models_are_hardlinked(dirs):
    _, old_data = _parlance_install(dirs)
    config.import_parlance()
    assert os.stat(config.DATA_DIR / ENCODER).st_ino == os.stat(old_data / ENCODER).st_ino


def test_hardlink_failure_falls_back_to_copy(dirs, monkeypatch):
    import errno
    _, old_data = _parlance_install(dirs)

    def exdev(*a):
        raise OSError(errno.EXDEV, "Invalid cross-device link")
    monkeypatch.setattr(config.os, "link", exdev)
    config.import_parlance()
    new_enc = config.DATA_DIR / ENCODER
    assert new_enc.read_bytes() == b"x" * 10
    assert os.stat(new_enc).st_ino != os.stat(old_data / ENCODER).st_ino


def test_runs_once_and_never_overwrites(dirs):
    old_cfg, _ = _parlance_install(dirs)
    config.import_parlance()
    config.save_json(config.CONFIG_PATH, {"hotkey": "KEY_F20"})
    (old_cfg / "config.json").write_text('{"mode": "hold"}')
    assert config.import_parlance() is False
    assert json.loads(config.CONFIG_PATH.read_text()) == {"hotkey": "KEY_F20"}


def test_data_import_ignores_a_venv_only_data_dir(dirs):
    _parlance_install(dirs)
    (config.DATA_DIR / "venv").mkdir(parents=True)              # install.sh ran first
    config.import_parlance()
    assert config.STATE_PATH.is_file() and (config.DATA_DIR / ENCODER).is_file()


def test_nothing_to_import(dirs):
    assert config.import_parlance() is False
    assert not config.CONFIG_DIR.exists() and not config.DATA_DIR.exists()
