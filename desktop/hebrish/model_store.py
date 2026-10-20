"""The model catalogue, the weights on disk, and the check against Hugging Face.

Same protocol as the Android app (../shared/update-protocol.md):

0. The catalogue (../shared/models.json, bundled as data/models.json) lists the models.
   Every update check also re-fetches it from `catalogue_url`, so a newly published model
   shows up without an app release. A model with status "planned" can't be downloaded.
1. GET /api/models/<repo>/revision/main                 -> sha `main` points at now
2. GET /api/models/<repo>/tree/<sha>[/<subdir>]           -> per file size + lfs.oid (SHA-256)
3. GET /<repo>/resolve/<sha>[/<subdir>]/version.json      -> {"version": "v4", "run": ...}
   (optional; only sets the label)

Since 0.2.2 a model may instead have a `manifest_url` (the Hebrish CDN, cdn.hebrish.app):
one GET returns {"version", "run", "revision", "base_url", "files": {name: {size, sha256}}},
and files download from base_url + name. It is used whenever present; `repo` stays in the
catalogue for older apps.

An update is offered when the weights differ, never because `main` moved: model-card
and eval commits move `main` many times a day without touching the weights.

Each installed version lives in models/<model id>/<version>-<sha12>/ and is complete only
once its manifest.json exists (written last, after every file verified).
"""

import hashlib
import json
import shutil
import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .config import CATALOGUE_CACHE, MODELS_DIR, STATE_PATH, load_json, save_json

BUNDLED_CATALOGUE = Path(__file__).resolve().parent / "data" / "models.json"
SCHEMA = 1
HF = "https://huggingface.co"
USER_AGENT = "hebrish (+https://github.com/Hebrish-ASR/Hebrish-App)"


class Cancelled(Exception):
    pass


# -- catalogue ---------------------------------------------------------------

@dataclass
class Model:
    id: str
    name: str
    summary: str = ""
    status: str = "planned"          # available | planned
    repo: str = ""
    subdir: str = ""
    card: str = ""
    version_label: str = ""          # label when the repo has no version.json
    manifest_url: str = ""           # CDN manifest; preferred over repo when set (0.2.2+)

    @property
    def available(self) -> bool:
        return self.status == "available" and bool(self.repo or self.manifest_url)

    def path(self, name: str = "") -> str:
        """`subdir/name` without stray slashes; subdir is empty when files sit at the repo root."""
        return "/".join(p for p in (self.subdir, name) if p)


def _parse(doc: dict) -> dict:
    if doc.get("schema") != SCHEMA or not isinstance(doc.get("models"), list):
        raise ValueError("unsupported catalogue")
    return doc


def _load_catalogue() -> dict:
    bundled = _parse(json.loads(BUNDLED_CATALOGUE.read_text()))
    try:
        return _parse(load_json(CATALOGUE_CACHE))
    except ValueError:
        return bundled


def catalogue() -> dict:
    return _load_catalogue()


FILES: tuple = tuple(catalogue()["files"])
VERSION_FILE: str = catalogue()["version_file"]


def models() -> list[Model]:
    keys = Model.__dataclass_fields__
    return [Model(**{k: v for k, v in m.items() if k in keys}) for m in catalogue()["models"]]


def get_model(mid: str) -> Model | None:
    return next((m for m in models() if m.id == mid), None)


def refresh_catalogue():
    """Fetch the published catalogue; keep the cached/bundled one if that fails."""
    url = json.loads(BUNDLED_CATALOGUE.read_text())["catalogue_url"]
    try:
        doc = _parse(json.loads(_get(url)))
    except Exception:
        return
    save_json(CATALOGUE_CACHE, doc)


def current_id() -> str:
    """The model the user picked; else the catalogue default."""
    mid = load_json(STATE_PATH).get("model")
    m = get_model(mid) if mid else None
    return m.id if m and m.available else catalogue()["default"]


def current() -> Model:
    return get_model(current_id())


def select(mid: str):
    m = get_model(mid)
    if not m or not m.available:
        raise ValueError(f"{mid} is not available")
    state = load_json(STATE_PATH)
    state["model"] = mid
    save_json(STATE_PATH, state)


# -- manifests ---------------------------------------------------------------

@dataclass
class Manifest:
    model: str                       # catalogue id
    revision: str                    # full commit sha the files were fetched at
    version: str                     # "v4", or "rev abc1234" without version.json
    run: str = ""
    files: dict = field(default_factory=dict)   # name -> {"size": int, "sha256": str|None}
    base_url: str = ""               # CDN folder the files download from; empty = Hugging Face

    @property
    def dirname(self) -> str:
        label = self.version if not self.version.startswith("rev ") else "rev"
        return f"{label}-{self.revision[:12]}"

    @property
    def label(self) -> str:
        run = f", {self.run}" if self.run else ""
        return f"{self.version}{run} (rev {self.revision[:7]})"

    @property
    def full_label(self) -> str:
        m = get_model(self.model)
        return f"{m.name if m else self.model} {self.label}"

    @property
    def total_size(self) -> int:
        return sum(f["size"] for f in self.files.values())

    def same_weights(self, other: "Manifest") -> bool:
        """tokens.txt is a plain git file (no lfs.oid), so only its size is compared."""
        if self.model != other.model:
            return False
        for name in FILES:
            a, b = self.files.get(name), other.files.get(name)
            if not a or not b:
                return False
            if a.get("sha256") or b.get("sha256"):
                if a.get("sha256") != b.get("sha256"):
                    return False
            elif a["size"] != b["size"]:
                return False
        return True

    def to_json(self) -> dict:
        d = {"model": self.model, "revision": self.revision, "version": self.version,
             "run": self.run, "files": self.files}
        if self.base_url:
            d["base_url"] = self.base_url
        return d

    @classmethod
    def from_json(cls, d: dict, model: str = "") -> "Manifest":
        return cls(d.get("model") or model, d["revision"], d["version"], d.get("run", ""),
                   d.get("files", {}), d.get("base_url", ""))


# -- remote ------------------------------------------------------------------

def _get(url: str, timeout=20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def manifest_from_tree(model: Model, sha: str, tree: list, version_info: dict | None) -> Manifest:
    files = {}
    for entry in tree:
        name = entry["path"].rsplit("/", 1)[-1]
        if name in FILES:
            lfs = entry.get("lfs") or {}
            files[name] = {"size": entry["size"], "sha256": lfs.get("oid")}
    missing = [f for f in FILES if f not in files]
    if missing:
        raise RuntimeError(f"{model.repo} at {sha[:7]} is missing {', '.join(missing)}")
    info = version_info or {}
    version = info.get("version") or model.version_label or f"rev {sha[:7]}"
    return Manifest(model.id, sha, version, info.get("run", ""), files)


def manifest_from_cdn(model: Model, doc: dict) -> Manifest:
    files = {n: doc["files"][n] for n in FILES if n in doc.get("files", {})}
    missing = [f for f in FILES if f not in files]
    if missing:
        raise RuntimeError(f"{model.manifest_url} is missing {', '.join(missing)}")
    base = doc["base_url"] if doc["base_url"].endswith("/") else doc["base_url"] + "/"
    return Manifest(model.id, doc["revision"], doc["version"], doc.get("run", ""), files, base)


def fetch_latest(mid: str | None = None) -> Manifest:
    model = get_model(mid or current_id())
    if not model or not model.available:
        raise RuntimeError(f"{mid} is not downloadable yet")
    if model.manifest_url:
        return manifest_from_cdn(model, json.loads(_get(model.manifest_url)))
    sha = json.loads(_get(f"{HF}/api/models/{model.repo}/revision/main"))["sha"]
    tree = json.loads(_get("/".join(p for p in (f"{HF}/api/models/{model.repo}/tree/{sha}", model.subdir) if p)))
    try:
        info = json.loads(_get(f"{HF}/{model.repo}/resolve/{sha}/{model.path(VERSION_FILE)}"))
    except Exception:
        info = None
    return manifest_from_tree(model, sha, tree, info)


# -- local -------------------------------------------------------------------

# Where models live: MODELS_DIR, or the folder the user picked (config `models_dir`, 0.5.0).
# The app calls set_root() at start and when the setting changes; the CLI uses the default.
ROOT = MODELS_DIR


def set_root(path: Path):
    global ROOT
    ROOT = Path(path)


def model_dir(mid: str) -> Path:
    return ROOT / mid


def installed(mid: str | None = None) -> list[tuple[Path, Manifest]]:
    """Complete installs of one model, newest first (by manifest mtime)."""
    mid = mid or current_id()
    out, base = [], model_dir(mid)
    if base.is_dir():
        for d in base.iterdir():
            mf = d / "manifest.json"
            if mf.is_file():
                try:
                    out.append((d, Manifest.from_json(json.loads(mf.read_text()), mid)))
                except (ValueError, KeyError):
                    continue
    out.sort(key=lambda t: (t[0] / "manifest.json").stat().st_mtime, reverse=True)
    return out


def installed_ids() -> list[str]:
    return [m.id for m in models() if installed(m.id)]


def active(mid: str | None = None) -> tuple[Path, Manifest] | None:
    """The install state.json names for this model, else its newest complete one."""
    mid = mid or current_id()
    all_ = installed(mid)
    want = load_json(STATE_PATH).get("active", {})
    want = want.get(mid) if isinstance(want, dict) else None
    for d, m in all_:
        if d.name == want:
            return d, m
    return all_[0] if all_ else None


def set_active(dirname: str, mid: str | None = None):
    state = load_json(STATE_PATH)
    if not isinstance(state.get("active"), dict):
        state["active"] = {}
    state["active"][mid or current_id()] = dirname
    save_json(STATE_PATH, state)


def remove(dirname: str, mid: str | None = None):
    base = model_dir(mid or current_id()).resolve()
    target = (base / dirname).resolve()
    if target.parent != base:                   # never leave our own folder
        raise ValueError(dirname)
    shutil.rmtree(target)


def remove_model(mid: str):
    """Delete every version of one model."""
    target = model_dir(mid).resolve()
    if target.parent != ROOT.resolve():
        raise ValueError(mid)
    shutil.rmtree(target, ignore_errors=True)


def prune_except(keep: str, mid: str | None = None):
    """Delete the other versions of one model; other models are never touched."""
    mid = mid or current_id()
    for d, _m in installed(mid):
        if d.name != keep:
            remove(d.name, mid)
    base = model_dir(mid)       # half-finished downloads of other versions
    if base.is_dir():
        for d in base.iterdir():
            if d.is_dir() and d.name != keep and not (d / "manifest.json").exists():
                shutil.rmtree(d, ignore_errors=True)


def disk_usage(mid: str) -> int:
    base = model_dir(mid)
    return sum(f.stat().st_size for f in base.rglob("*") if f.is_file()) if base.is_dir() else 0


def needs_update(latest: Manifest) -> bool:
    cur = active(latest.model)
    return cur is None or not cur[1].same_weights(latest)


# -- download ----------------------------------------------------------------

def _sha256(path: Path, cancel: threading.Event | None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(4 << 20):
            if cancel and cancel.is_set():
                raise Cancelled()
            h.update(chunk)
    return h.hexdigest()


def download(m: Manifest, on_progress=None, cancel: threading.Event | None = None,
             keep_old: bool = True) -> Path:
    """Fetch every file pinned to m.revision, verify, then activate.

    `.part` files resume on the next attempt. The previous version stays usable until
    the new one has verified; only then is it (optionally) deleted.
    """
    model = get_model(m.model)
    dest = model_dir(m.model) / m.dirname
    dest.mkdir(parents=True, exist_ok=True)

    need = m.total_size - sum((dest / n).stat().st_size for n in FILES if (dest / n).exists())
    free = shutil.disk_usage(dest).free
    if need > free:
        raise RuntimeError(f"Not enough disk space: need {need >> 20} MB, have {free >> 20} MB")

    total, done = m.total_size, 0
    for name in FILES:
        info = m.files[name]
        final, part = dest / name, dest / (name + ".part")
        if final.exists() and final.stat().st_size == info["size"]:
            done += info["size"]
            continue
        have = part.stat().st_size if part.exists() else 0
        if have > info["size"]:
            part.unlink()
            have = 0
        url = (m.base_url + name) if m.base_url else f"{HF}/{model.repo}/resolve/{m.revision}/{model.path(name)}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        if have:
            req.add_header("Range", f"bytes={have}-")
        with urllib.request.urlopen(req, timeout=60) as r:
            if have and r.status != 206:      # server ignored Range: start over
                have = 0
            with part.open("ab" if have else "wb") as f:
                done_file = have
                while chunk := r.read(1 << 20):
                    if cancel and cancel.is_set():
                        raise Cancelled()
                    f.write(chunk)
                    done_file += len(chunk)
                    if on_progress:
                        on_progress(done + done_file, total, name)
        if part.stat().st_size != info["size"]:
            raise RuntimeError(f"{name}: size {part.stat().st_size} != {info['size']}")
        if info.get("sha256"):
            if on_progress:
                on_progress(done + info["size"], total, f"verifying {name}")
            got = _sha256(part, cancel)
            if got != info["sha256"]:
                part.unlink()
                raise RuntimeError(f"{name}: SHA-256 mismatch (got {got[:12]}…)")
        part.rename(final)
        done += info["size"]

    (dest / "manifest.json").write_text(json.dumps(m.to_json(), indent=2))
    set_active(dest.name, m.model)
    if not keep_old:
        prune_except(dest.name, m.model)
    return dest


def main():
    import argparse
    import sys
    from .config import CONFIG_PATH, import_parlance, models_root
    import_parlance()                   # first start: copy Parlance's settings and models
    set_root(models_root(load_json(CONFIG_PATH)))
    p = argparse.ArgumentParser(prog="hebrish-model")
    p.add_argument("cmd", choices=["list", "status", "check", "download", "use"])
    p.add_argument("model", nargs="?", help="catalogue id (default: the selected model)")
    p.add_argument("--replace", action="store_true", help="delete older versions after download")
    a = p.parse_args()
    if a.cmd in ("list", "check", "download"):
        refresh_catalogue()
    if a.cmd == "list":
        sel = current_id()
        for m in models():
            tag = "selected" if m.id == sel else ("installed" if installed(m.id) else m.status)
            print(f"  {m.id:12} {m.name:32} [{tag}]")
        return
    if a.cmd == "use":
        select(a.model or current_id())
        print("selected", current_id())
        return
    mid = a.model or current_id()
    cur = active(mid)
    rows = [f"  {d.name}{'  (active)' if cur and d == cur[0] else ''}" for d, _ in installed(mid)]
    print(f"{mid} installed:", *(rows or ["  none"]), sep="\n")
    if a.cmd == "status":
        return
    latest = fetch_latest(mid)
    print("latest on HF:", latest.label)
    if not needs_update(latest):
        print("up to date")
        return
    print("update available" if cur else "not installed")
    if a.cmd == "download":
        def prog(d, t, name):
            sys.stdout.write(f"\r{d * 100 // t:3d}%  {name:40.40s}")
            sys.stdout.flush()
        print("\ninstalled to", download(latest, prog, keep_old=not a.replace))


if __name__ == "__main__":
    main()
