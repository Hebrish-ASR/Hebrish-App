"""Is there a newer Hebrish app, and how can this copy get it? (0.6.2, 2026-10-21)

Model updates are model_store's job; this is the app itself. No Qt import, so it is testable.

1. GET https://cdn.hebrish.app/downloads/latest.json, the same manifest hebrish.app/get/<os>
   follows: {version, released, notes, terms, files: {android|ubuntu|windows: {url, name,
   platform, size, sha256, version}}}. The top-level `version` is not ours: Android and desktop
   version separately, so only files.ubuntu.version (Linux) or files.windows.version counts.
2. Compare it with hebrish.__version__ (numeric, so 0.10.0 > 0.9.0).
3. install_method() says what to offer:
   apt        the .deb (/usr/lib/hebrish) and /etc/apt/sources.list.d/hebrish.sources, which the
              .deb installs from 0.6.2: pkexec runs APT_SCRIPT (refresh only that source,
              upgrade only hebrish), then the app offers to restart.
   deb-manual the .deb without that file (0.6.1 and earlier, or the user deleted it): link to
              the download page; the new .deb brings the source with it.
   windows    the portable zip (frozen PyInstaller build, no installer): link to the download page,
              which since 1.041 offers the installer.
   velopack   the Windows installer (Velopack, 1.041, 2026-11-17): updates itself with no user action.
              It does not read latest.json: it reads its own feed (VELOPACK_FEED, channel stable),
              downloads in the background, and the update is applied the next time Hebrish starts
              (Velopack's auto-apply on startup) or at once from "Restart to update".
              research/windows-distribution/README.md.
   msix       the Microsoft Store package: the Store updates it, so nothing is offered.
   appimage   the AppImage (build-appimage.sh; the runtime sets $APPIMAGE and $APPDIR, 2026-10-31):
              link to the download page.
   Channels (2026-10-31): the .deb follows beta (files.ubuntu, the APT repo); the AppImage and
   the Windows zip follow stable (files.appimage, files.windows), so each reads only its own key.
   source     a checkout or venv: say a new version exists, nothing else.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__
# The same GET as the model manifests: Cloudflare's bot filter answers 403 to urllib's default
# User-Agent on cdn.hebrish.app (V, 2026-10-21), and model_store sends its own.
from .model_store import _get

LATEST_URL = "https://cdn.hebrish.app/downloads/latest.json"
DOWNLOAD_PAGE = "https://hebrish.app/download"
INSTALL_DIR = Path("/usr/lib/hebrish")              # the .deb's copy of the package
LAUNCHER = "/usr/bin/hebrish"
SOURCES = Path("/etc/apt/sources.list.d/hebrish.sources")
METHODS = ("apt", "deb-manual", "windows", "velopack", "msix", "appimage", "source")

# Velopack (Windows installer). packId is not "Hebrish": Velopack installs to %LOCALAPPDATA%\<packId>,
# and %LOCALAPPDATA%\Hebrish is already the data folder (models, history; config.DATA_DIR).
VELOPACK_ID = "HebrishDictation"
VELOPACK_FEED = "https://cdn.hebrish.app/apps/windows/velopack/"
VELOPACK_CHANNEL = "stable"

# Refresh only the Hebrish source, then upgrade only hebrish (never install it, never touch
# other packages). Option names checked against apt 3.2.0 on Ubuntu 26.04 (V, 2026-10-21, with
# --print-uris as a normal user: all 13 URIs on cdn.hebrish.app, none elsewhere):
#   Dir::Etc::sourcelist  the one list file to read; a .sources name is parsed as deb822
#   Dir::Etc::sourceparts "-" = read no sources.list.d/ directory
#   APT::Get::List-Cleanup=0  keep the other sources' downloaded lists; with the default (1),
#                         apt deletes list files of sources it wasn't told about, and the next
#                         install would see only Hebrish's packages until a full `apt update`.
# A full `apt-get update` would also work but takes longer, and fails the whole command when
# any unrelated third-party source is broken.
# No terminal under pkexec, so a dpkg conffile question would hang the run: noninteractive, and
# keep the user's version of any changed conffile (confdef, else confold).
APT_SCRIPT = (f"apt-get update -o Dir::Etc::sourcelist={SOURCES.as_posix()} -o Dir::Etc::sourceparts=- "
              "-o APT::Get::List-Cleanup=0 && DEBIAN_FRONTEND=noninteractive apt-get install -y "
              "--only-upgrade -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold hebrish")
# What to run by hand when pkexec isn't there or fails
TERMINAL_COMMAND = "sudo apt update && sudo apt install --only-upgrade hebrish"


@dataclass
class Release:
    version: str
    url: str = ""           # the file (.deb / zip); the app links to DOWNLOAD_PAGE instead
    name: str = ""
    released: str = ""
    notes: str = ""


def parse_version(v: str) -> tuple[int, ...]:
    """'0.6.2' -> (0, 6, 2). Leading 'v', a Debian revision ('0.6.2-1') and a suffix
    ('0.7.0rc1') are dropped; trailing zeros too, so 0.6 == 0.6.0."""
    m = re.match(r"v?(\d+(?:\.\d+)*)", str(v).strip())
    if not m:
        raise ValueError(f"not a version: {v!r}")
    parts = [int(p) for p in m.group(1).split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def is_newer(latest: str, current: str = __version__) -> bool:
    try:
        return parse_version(latest) > parse_version(current)
    except ValueError:
        return False


def platform_key(platform: str = sys.platform, method: str | None = None) -> str:
    """The latest.json `files` key for this copy: windows, appimage (both stable) or ubuntu (beta)."""
    if platform == "win32":
        return "windows"
    method = install_method(platform) if method is None else method
    return "appimage" if method == "appimage" else "ubuntu"


def parse_manifest(doc: dict, key: str | None = None) -> Release:
    """latest.json -> this platform's Release. ValueError when the entry or its version is missing."""
    key = key or platform_key()
    entry = (doc.get("files") or {}).get(key) if isinstance(doc, dict) else None
    if not isinstance(entry, dict) or not entry.get("version"):
        raise ValueError(f"latest.json has no files.{key}.version")
    parse_version(entry["version"])
    return Release(version=str(entry["version"]), url=entry.get("url", ""), name=entry.get("name", ""),
                   released=str(doc.get("released", "")), notes=str(doc.get("notes", "")))


def fetch(key: str | None = None) -> Release:
    return parse_manifest(json.loads(_get(LATEST_URL, timeout=15)), key)


def install_method(platform: str = sys.platform, frozen: bool | None = None,
                   module_file: str | None = None, sources: Path = SOURCES,
                   install_dir: Path = INSTALL_DIR, env: dict | None = None) -> str:
    """apt | deb-manual | windows | appimage | source (see the module docstring). The arguments
    exist for the tests; the app calls it bare."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if platform == "win32":
        if not frozen:
            return "source"
        exe = Path(env_get(env, "HEBRISH_EXE") or sys.executable)
        if "\\windowsapps\\" in str(exe).lower():                # an MSIX package (Store)
            return "msix"
        if (exe.parent.parent / "Update.exe").is_file():           # <root>\current\Hebrish.exe
            return "velopack"
        return "windows"
    here = Path(module_file or __file__).resolve()
    if appimage_path(env) and Path(env_get(env, "APPDIR")).resolve() in here.parents:
        return "appimage"
    if install_dir.resolve() not in here.parents:
        return "source"
    return "apt" if sources.is_file() else "deb-manual"


def env_get(env: dict | None, key: str) -> str:
    return (os.environ if env is None else env).get(key, "")


def appimage_path(env: dict | None = None) -> str:
    """The .AppImage file this copy runs from ('' when it isn't one). Only the AppImage runtime
    sets both variables; a child process inherits them, so APPDIR must hold this module too
    (install_method checks that)."""
    return env_get(env, "APPIMAGE") if env_get(env, "APPIMAGE") and env_get(env, "APPDIR") else ""


def download_page(method: str) -> str:
    return f"{DOWNLOAD_PAGE}#{ {'windows': 'windows', 'appimage': 'appimage'}.get(method, 'ubuntu') }"


def apt_command() -> list[str]:
    return ["pkexec", "sh", "-c", APT_SCRIPT]


def installed_deb_version() -> str:
    """The hebrish package's version per dpkg ('' if unknown): checked after an upgrade, because
    `apt-get install --only-upgrade` exits 0 also when the repo has nothing newer."""
    try:
        r = subprocess.run(["dpkg-query", "-W", "-f=${Version}", "hebrish"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def run_apt_upgrade(target: str, timeout: int = 900) -> tuple[bool, str]:
    """Blocking (run it off the GUI thread). (ok, message for the user). pkexec shows the
    desktop's polkit password dialog; it exits 126 when the dialog is dismissed and 127 when
    authorisation fails (pkexec(1))."""
    if not shutil.which("pkexec"):
        return False, f"pkexec isn't installed. Update in a terminal: {TERMINAL_COMMAND}"
    try:
        r = subprocess.run(apt_command(), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "The update took too long and was stopped."
    except OSError as e:
        return False, f"Couldn't start pkexec: {e}"
    if r.returncode == 126:
        return False, "Update cancelled."
    if r.returncode == 127:
        return False, f"Not authorised. Update in a terminal instead: {TERMINAL_COMMAND}"
    if r.returncode != 0:
        tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
        return False, "The update failed: " + (" ".join(tail) or f"exit code {r.returncode}")
    now = installed_deb_version()
    if not now:
        return True, "Hebrish was updated."
    if not is_newer(target, now):
        return True, f"Hebrish {parse_label(now)} is installed."
    return False, (f"The Hebrish repository doesn't offer {target} yet (installed: "
                   f"{parse_label(now)}). Try again later.")


def parse_label(deb_version: str) -> str:
    """'0.6.2-1' -> '0.6.2'."""
    return deb_version.split("-", 1)[0]


def relaunch(pid: int | None = None):
    """Start /usr/bin/hebrish once this process (pid) has exited, so the new copy doesn't find the
    old one's single-instance socket and just hand it a "show". The caller then quits."""
    pid = pid or os.getpid()
    launcher = shlex.quote(appimage_path()) if install_method() == "appimage" else LAUNCHER
    subprocess.Popen(["sh", "-c", f"while kill -0 {pid} 2>/dev/null; do sleep 0.2; done; exec {launcher}"],
                     start_new_session=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# -- Velopack (Windows installer, 1.041) -------------------------------------------------------

def velopack_version(version: str) -> str:
    """Our M.NNN as the SemVer Velopack needs: '1.041' -> '1.41.0'. SemVer forbids leading zeros,
    and the counter always has three digits, so the order is kept (1.099 < 1.100)."""
    major, _, counter = version.partition(".")
    return f"{int(major)}.{int(counter or 0)}.0"


def our_version(semver: str) -> str:
    """The inverse: '1.41.0' -> '1.041'."""
    major, counter = semver.split(".")[:2]
    return f"{int(major)}.{int(counter):03d}"


def velopack_manager():
    import velopack
    from .model_store import USER_AGENT          # Cloudflare 403s unknown user agents on the CDN
    http = velopack.HttpOptions([velopack.HttpHeader("User-Agent", USER_AGENT)], 120_000)
    return velopack.UpdateManager(velopack.HttpSource(VELOPACK_FEED, http),
                                  velopack.UpdateOptions(False, 10, VELOPACK_CHANNEL))


def velopack_stage(on_progress=None) -> str | None:
    """Blocking. Check the feed and download a newer version; return its version (M.NNN) or None.
    Velopack applies a downloaded update when the app next starts (auto-apply, launcher.py)."""
    um = velopack_manager()
    pending = um.get_update_pending_restart()
    if pending:
        return our_version(pending.Version)
    info = um.check_for_updates()
    if not info:
        return None
    um.download_updates(info, on_progress)
    return our_version(info.TargetFullRelease.Version)


def velopack_restart():
    """Apply the downloaded update once this process has exited, then start the new version.
    The caller quits."""
    um = velopack_manager()
    pending = um.get_update_pending_restart()
    if pending:
        um.wait_exit_then_apply_updates(pending, silent=True, restart=True)
