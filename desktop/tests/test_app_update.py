"""Offline tests of the app update check (app_update.py, 0.6.2): version order, latest.json
parsing, and how this copy can update. Run: .venv/bin/python -m pytest tests"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from hebrish import app_update as au  # noqa: E402

# Shape of https://cdn.hebrish.app/downloads/latest.json on 2026-10-21 (sha256 trimmed). Android
# and desktop version separately: the top-level version is the desktop's here, but only
# files.<os>.version counts.
LATEST = {
    "version": "0.6.1", "released": "2026-10-21",
    "notes": "https://github.com/Hebrish-ASR/Hebrish-App/releases", "terms": "https://hebrish.app/terms",
    "files": {
        "android": {"url": "https://cdn.hebrish.app/apps/android/Hebrish-latest.apk",
                    "name": "Hebrish-v0.7.0.apk", "size": 14654970, "sha256": "b3d7", "version": "0.7.0"},
        "ubuntu": {"url": "https://cdn.hebrish.app/apps/ubuntu/hebrish-latest-amd64.deb",
                   "name": "hebrish_0.6.2-1_amd64.deb", "size": 11194324, "sha256": "5b57", "version": "0.6.2"},
        "windows": {"url": "https://cdn.hebrish.app/apps/windows/Hebrish-latest-windows-x64.zip",
                    "name": "Hebrish-v0.6.1-windows-x64.zip", "size": 69142132, "sha256": "9aca", "version": "0.6.1"},
    },
}


@pytest.mark.parametrize("a,b", [
    ("0.6.2", "0.6.1"), ("0.10.0", "0.9.9"), ("1.0", "0.99.99"), ("0.6.2-1", "0.6.1-3"),
    ("v0.7.0", "0.6.9"), ("0.6.10", "0.6.9"),
    # M.NNN versions since 1.000 (2026-10-24): above every 0.x, and NNN compares as a number.
    ("1.000", "0.10.0"), ("1.000", "0.99.99"), ("1.001", "1.000"), ("1.010", "1.009"), ("1.100", "1.099"),
    ("2.000", "1.999"),
])
def test_newer(a, b):
    assert au.is_newer(a, b)
    assert not au.is_newer(b, a)


@pytest.mark.parametrize("a,b", [("0.6.1", "0.6.1"), ("0.6", "0.6.0"), ("0.6.1-2", "0.6.1"),
                                 ("0.7.0rc1", "0.7.0")])
def test_equal_is_not_newer(a, b):
    assert not au.is_newer(a, b) and not au.is_newer(b, a)


def test_garbage_version_is_never_newer():
    assert not au.is_newer("latest", "0.6.1")
    assert not au.is_newer("", "0.6.1")
    with pytest.raises(ValueError):
        au.parse_version("abc")


def test_manifest_uses_the_platform_entry_not_the_top_level_version():
    assert au.parse_manifest(LATEST, "ubuntu").version == "0.6.2"
    assert au.parse_manifest(LATEST, "windows").version == "0.6.1"
    rel = au.parse_manifest(LATEST, "ubuntu")
    assert rel.name == "hebrish_0.6.2-1_amd64.deb" and rel.released == "2026-10-21"


def test_platform_key():
    assert au.platform_key("linux") == "ubuntu"
    assert au.platform_key("win32") == "windows"


@pytest.mark.parametrize("doc", [{}, {"files": {}}, {"files": {"ubuntu": {"url": "x"}}},
                                 {"files": {"ubuntu": {"version": "soon"}}}, [], None])
def test_bad_manifest_raises(doc):
    with pytest.raises(ValueError):
        au.parse_manifest(doc, "ubuntu")


def _layout(tmp_path, sources=True):
    lib = tmp_path / "usr/lib/hebrish/hebrish"
    lib.mkdir(parents=True)
    src = tmp_path / "etc/apt/sources.list.d/hebrish.sources"
    src.parent.mkdir(parents=True)
    if sources:
        src.write_text("Types: deb\n")
    return lib / "app_update.py", src, tmp_path / "usr/lib/hebrish"


def test_installed_package_with_repo_is_apt(tmp_path):
    mod, src, inst = _layout(tmp_path)
    assert au.install_method("linux", False, str(mod), src, inst) == "apt"


def test_installed_package_without_repo_is_deb_manual(tmp_path):
    mod, src, inst = _layout(tmp_path, sources=False)
    assert au.install_method("linux", False, str(mod), src, inst) == "deb-manual"


def test_checkout_is_source_even_with_the_repo_configured(tmp_path):
    _, src, inst = _layout(tmp_path)
    checkout = tmp_path / "home/me/Hebrish-Dictation/desktop/hebrish/app_update.py"
    assert au.install_method("linux", False, str(checkout), src, inst) == "source"


def test_windows(tmp_path):
    assert au.install_method("win32", True, "C:/x/_internal/hebrish/app_update.py") == "windows"
    assert au.install_method("win32", False, "C:/src/desktop/hebrish/app_update.py") == "source"


def test_appimage(tmp_path):
    _, src, inst = _layout(tmp_path)
    mnt = tmp_path / "tmp/.mount_HebrisXYZ"
    mod = mnt / "usr/lib/hebrish/hebrish/app_update.py"
    env = {"APPIMAGE": "/home/me/Apps/Hebrish-1.017-x86_64.AppImage", "APPDIR": str(mnt)}
    assert au.install_method("linux", False, str(mod), src, inst, env) == "appimage"
    # a child started from inside the AppImage inherits the variables: a checkout is still source
    checkout = tmp_path / "home/me/Hebrish-Dictation/desktop/hebrish/app_update.py"
    assert au.install_method("linux", False, str(checkout), src, inst, env) == "source"
    assert au.appimage_path(env) == env["APPIMAGE"]
    assert au.appimage_path({"APPIMAGE": "x"}) == ""
    assert au.download_page("appimage") == "https://hebrish.app/download#appimage"
    # stable channel: the AppImage reads files.appimage, never the beta .deb's entry
    assert au.platform_key("linux", "appimage") == "appimage"
    assert au.platform_key("linux", "apt") == "ubuntu"
    assert au.platform_key("win32") == "windows"


def test_this_checkout_is_source():
    assert au.install_method() == "source"


def test_download_pages():
    assert au.download_page("windows") == "https://hebrish.app/download#windows"
    assert au.download_page("deb-manual") == "https://hebrish.app/download#ubuntu"


def test_apt_command_refreshes_only_the_hebrish_source_and_upgrades_only_hebrish():
    cmd = au.apt_command()
    assert cmd[:3] == ["pkexec", "sh", "-c"]
    script = cmd[3]
    assert "Dir::Etc::sourcelist=/etc/apt/sources.list.d/hebrish.sources" in script
    assert "Dir::Etc::sourceparts=-" in script and "APT::Get::List-Cleanup=0" in script
    assert "apt-get install -y --only-upgrade" in script and script.endswith(" hebrish")
    assert "DEBIAN_FRONTEND=noninteractive" in script and "--force-confold" in script


def test_upgrade_reports_when_the_repo_has_nothing_newer(monkeypatch):
    class R:
        returncode, stdout, stderr = 0, "", ""
    monkeypatch.setattr(au.shutil, "which", lambda _: "/usr/bin/pkexec")
    monkeypatch.setattr(au.subprocess, "run", lambda *a, **k: R())
    monkeypatch.setattr(au, "installed_deb_version", lambda: "0.6.1-1")
    ok, msg = au.run_apt_upgrade("0.6.2")
    assert not ok and "doesn't offer 0.6.2" in msg
    monkeypatch.setattr(au, "installed_deb_version", lambda: "0.6.2-1")
    assert au.run_apt_upgrade("0.6.2") == (True, "Hebrish 0.6.2 is installed.")


@pytest.mark.parametrize("code,word", [(126, "cancelled"), (127, "Not authorised"), (100, "failed")])
def test_upgrade_pkexec_exit_codes(monkeypatch, code, word):
    class R:
        returncode, stdout, stderr = code, "", "E: something"
    monkeypatch.setattr(au.shutil, "which", lambda _: "/usr/bin/pkexec")
    monkeypatch.setattr(au.subprocess, "run", lambda *a, **k: R())
    ok, msg = au.run_apt_upgrade("0.6.2")
    assert not ok and word in msg
