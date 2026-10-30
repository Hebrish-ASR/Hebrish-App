"""The model catalogue, the weights on disk, and the check against Hugging Face.

Same protocol as the Android app (../shared/update-protocol.md):

0. The catalogue (../shared/catalogue.json, schema 2, bundled as data/catalogue.json) lists
   lines and their variants; models() is the variants this build's engines can run.
   Every update check also re-fetches it from `catalogue_url`, so a newly published model
   shows up without an app release. (`catalogue_v2_url`; schema 1, models.json, is
   for builds up to 0.5.x.) A model with status "planned" can't be downloaded.
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
import sys
import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .config import CATALOGUE_CACHE, MODELS_DIR, STATE_PATH, load_json, save_json

BUNDLED_CATALOGUE = Path(__file__).resolve().parent / "data" / "catalogue.json"
SCHEMA = 2
HF = "https://huggingface.co"
USER_AGENT = "hebrish (+https://github.com/Hebrish-ASR/Hebrish-App)"
# Engines this build can run. A variant with any other engine is listed (greyed, with where it
# runs and its card) but can't be selected or downloaded. sherpa_online_transducer (Shakshuka) since
# 0.7.0; its files have the same names as the offline engine's.
SUPPORTED_ENGINES = {"sherpa_offline_transducer", "sherpa_online_transducer"}
PLATFORM = "windows" if sys.platform == "win32" else "linux"


class Cancelled(Exception):
    pass


# -- catalogue ---------------------------------------------------------------

@dataclass
class Model:
    """One variant of the v2 catalogue (shared/catalogue.json)."""
    id: str
    name: str
    summary: str = ""
    status: str = "planned"          # available | planned
    repo: str = ""
    subdir: str = ""
    card: str = ""
    version_label: str = ""          # label when the repo has no version.json
    manifest_url: str = ""           # CDN manifest; preferred over repo when set (0.2.2+)
    line: str = ""                   # line id (sabich, jachnun, shakshuka, stock)
    engine: str = "sherpa_offline_transducer"
    feature_dim: int = 128           # mel features for sherpa (80 for Sabich-Parakeet-110M)
    base_model: str = ""             # repo id; shown only under Technical details
    base_label: str = ""             # what the Models tab shows: "Parakeet 0.6B v2 by NVIDIA" (2026-10-25)
    technical: str = ""              # formats, runtimes, VRAM: Technical details only
    size_label: str = ""
    platforms: list = field(default_factory=lambda: ["android", "linux", "windows"])
    devices: list = field(default_factory=list)       # wearable | phone | desktop
    requirements: dict = field(default_factory=dict)  # {"ram_mb", "gpu": null | {"vram_gb", "backends"}}
    hardware: str = ""
    download_mb: int | None = None
    speed: int = 0                   # 1-5, estimate
    accuracy: int = 0                # 1-5, estimate
    gradient: int = 0                # 0 = smallest and fastest, 100 = most accurate (estimate)
    recommendation: str = ""
    runs_on: str = ""                # where an unsupported variant runs instead
    streaming: bool = False

    @property
    def supported(self) -> bool:
        """This build can run it on this OS."""
        return self.engine in SUPPORTED_ENGINES and PLATFORM in self.platforms

    @property
    def available(self) -> bool:
        return self.supported and self.status == "available" and bool(self.repo or self.manifest_url)

    def path(self, name: str = "") -> str:
        """`subdir/name` without stray slashes; subdir is empty when files sit at the repo root."""
        return "/".join(p for p in (self.subdir, name) if p)


@dataclass
class Line:
    id: str
    name: str
    summary: str = ""
    card: str = ""
    variants: list = field(default_factory=list)      # [Model]


def _parse(doc: dict) -> dict:
    if (doc.get("schema") != SCHEMA or not isinstance(doc.get("lines"), list)
            or "sherpa_offline_transducer" not in doc.get("engines", {})):
        raise ValueError("unsupported catalogue")
    if not any(v.get("id") for ln in doc["lines"] for v in ln.get("variants", [])):
        raise ValueError("empty catalogue")
    return doc


_BUNDLED: dict | None = None
_CACHED: tuple = (None, None)       # (stat key of CATALOGUE_CACHE, its parsed doc or None)


def bundled_catalogue() -> dict:
    """The catalogue shipped with the app, parsed once (it can't change while the app runs)."""
    global _BUNDLED
    if _BUNDLED is None:
        _BUNDLED = _parse(json.loads(BUNDLED_CATALOGUE.read_text()))
    return _BUNDLED


def _stat_key(path: Path):
    try:
        st = path.stat()
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size, st.st_ino


def catalogue() -> dict:
    """The published catalogue last fetched (CATALOGUE_CACHE), else the bundled one. Read from
    disk only when the cache file changes: the window asks for it dozens of times per refresh
    (lines(), models(), current_id(), get_model() all start here). Callers must not mutate it."""
    global _CACHED
    key = _stat_key(CATALOGUE_CACHE)
    if key is None or key != _CACHED[0]:
        try:
            doc = _parse(load_json(CATALOGUE_CACHE)) if key is not None else None
        except ValueError:
            doc = None
        _CACHED = (key, doc)
    return _CACHED[1] or bundled_catalogue()


FILES: tuple = tuple(catalogue()["engines"]["sherpa_offline_transducer"]["files"])
VERSION_FILE: str = catalogue().get("version_file", "version.json")


def lines() -> list[Line]:
    """Every line with every variant, supported or not, in catalogue order."""
    keys = Model.__dataclass_fields__
    out = []
    for ln in catalogue()["lines"]:
        vs = [Model(**{k: v for k, v in m.items() if k in keys}, line=ln["id"],
                    summary=m.get("summary") or ln.get("summary", ""))
              for m in ln.get("variants", [])]
        out.append(Line(ln["id"], ln["name"], ln.get("summary", ""), ln.get("card", ""), vs))
    return out


def variants() -> list[Model]:
    return [v for ln in lines() for v in ln.variants]


def models() -> list[Model]:
    """The variants this build can run (planned ones included), in catalogue order. Everything
    that downloads, selects or lists installs goes through this, never through variants()."""
    return [v for v in variants() if v.supported]


def get_model(mid: str) -> Model | None:
    return next((m for m in models() if m.id == mid), None)


def get_variant(mid: str) -> Model | None:
    return next((m for m in variants() if m.id == mid), None)


def recommended_id() -> str:
    """`recommended_by_platform` (0.7.0: Shakshuka on Linux and Windows, Daniel 2026-10-22), else
    `recommended` (Sabich; what Android and older desktop builds read)."""
    cat = catalogue()
    return cat.get("recommended_by_platform", {}).get(PLATFORM) or cat.get("recommended", "")


def refresh_catalogue():
    """Fetch the published catalogue; keep the cached/bundled one if that fails."""
    url = bundled_catalogue()["catalogue_v2_url"]
    try:
        doc = _parse(json.loads(_get(url)))
    except Exception:
        return
    save_json(CATALOGUE_CACHE, doc)


def current_id() -> str:
    """The model the user picked. Without a pick: a downloaded model (recommended first), so an
    install that ran schema 1's default (stock) keeps working; else the recommended model."""
    mid = load_json(STATE_PATH).get("model")
    m = get_model(mid) if mid else None
    if m and m.available:
        return m.id
    rec = recommended_id()
    order = sorted((m for m in models() if m.available), key=lambda m: m.id != rec)
    for m in order:
        if installed(m.id):
            return m.id
    return order[0].id if order else rec


# -- help me choose (0.6.0) --------------------------------------------------

def vram_bucket(gb: float) -> str:
    """The chooser's VRAM buckets (GB, rounded up): 4, 8, 12, 16."""
    return next((b for b in ("4", "8", "12") if gb <= int(b)), "16")


def _matches(when: dict, form: dict) -> bool:
    return all(form.get(k) in v for k, v in when.items())


def recommend(device: str, gpu: str = "none", vram_gb: float = 0, priority: str = "balanced",
              live: bool = False) -> dict:
    """The catalogue's `chooser.rules`, the same list as hebrish.app/models/choose: the first
    rule whose `when` matches the form wins. device is phone | computer | wearable, gpu none |
    amd | nvidia | apple. Returns the rule with `pick` / `runner_up` resolved to Models (either
    may be one this app can't run: check .available) and `here`, the best variant this app can
    download: the pick, else the runner-up, else the recommended model."""
    form = {"device": device, "gpu": gpu, "vram": vram_bucket(vram_gb), "priority": priority, "live": live}
    rule = next((r for r in catalogue().get("chooser", {}).get("rules", [])
                 if _matches(r.get("when", {}), form)), None)
    rec = get_model(recommended_id())
    if rule is None:
        return {"pick": rec, "runner_up": None, "here": rec, "how": "", "reason": "", "note": ""}
    pick, runner = get_variant(rule["pick"]), get_variant(rule.get("runner_up", ""))
    here = next((m for m in (pick, runner) if m and m.available), rec)
    return {**rule, "pick": pick, "runner_up": runner, "here": here}


def detect_gpu() -> tuple[str, float]:
    """Best-effort (vendor, VRAM in GB): nvidia-smi, then Linux sysfs (amdgpu reports VRAM there),
    else ("none", 0). Cheap: each probe has a 3 s timeout and failures are ignored."""
    import shutil as _sh
    import subprocess
    if _sh.which("nvidia-smi"):
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=3).stdout
            mib = max(int(x) for x in out.split() if x.strip().isdigit())
            return "nvidia", round(mib / 1024, 1)
        except Exception:
            pass
    best = ("none", 0.0)
    for dev in Path("/sys/class/drm").glob("card[0-9]*/device"):
        try:
            vendor = (dev / "vendor").read_text().strip()
        except OSError:
            continue
        name = {"0x1002": "amd", "0x10de": "nvidia", "0x8086": "intel"}.get(vendor)
        if not name:
            continue
        try:
            gb = int((dev / "mem_info_vram_total").read_text()) / (1 << 30)
        except (OSError, ValueError):
            gb = 0.0
        if gb >= best[1] or best[0] == "none":
            best = (name, round(gb, 1))
    return best


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
        """What the UI shows: just the version, "v2.0". No run name or commit (Daniel, 2026-10-22:
        "too much information"); those stay in [debug_label] for logs. A CDN manifest's version may
        repeat the model name ("Sabich v2.0"), so it is dropped here; a "rev abc1234" fallback
        (no version.json) shows nothing."""
        m = get_model(self.model)
        v = self.version
        if m and v.lower().startswith(m.name.lower() + " "):
            v = v[len(m.name) + 1:]
        return "" if v.startswith("rev ") else v

    @property
    def debug_label(self) -> str:
        run = f", {self.run}" if self.run else ""
        return f"{self.version}{run} (rev {self.revision[:7]})"

    @property
    def full_label(self) -> str:
        m = get_model(self.model)
        return f"{m.name if m else self.model} {self.label}".strip()

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


def prune_all():
    """Keep only the active version of every installed model (0.5.1: one version per model;
    run once at start to clear what earlier versions kept). Returns the bytes freed."""
    freed = 0
    for mid in installed_ids():
        cur = active(mid)
        before = disk_usage(mid)
        if cur:
            prune_except(cur[0].name, mid)
        freed += before - disk_usage(mid)
    return freed


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


def fetch_files(dest: Path, files: dict, url_for, on_progress=None,
                cancel: threading.Event | None = None):
    """Fetch `files` ({name: {"size", "sha256"}}) into `dest`, each from url_for(name), resuming
    `.part` files and checking size and SHA-256 before the rename. A file already there at the
    right size is kept. on_progress(done_bytes, total_bytes, name). Shared by the speech models
    and the paragraph model (paragraphs.download)."""
    dest.mkdir(parents=True, exist_ok=True)
    total = sum(f["size"] for f in files.values())
    need = total - sum((dest / n).stat().st_size for n in files if (dest / n).exists())
    free = shutil.disk_usage(dest).free
    if need > free:
        raise RuntimeError(f"Not enough disk space: need {need >> 20} MB, have {free >> 20} MB")

    done = 0
    for name, info in files.items():
        final, part = dest / name, dest / (name + ".part")
        if final.exists() and final.stat().st_size == info["size"]:
            done += info["size"]
            continue
        have = part.stat().st_size if part.exists() else 0
        if have > info["size"]:
            part.unlink()
            have = 0
        req = urllib.request.Request(url_for(name), headers={"User-Agent": USER_AGENT})
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


def download(m: Manifest, on_progress=None, cancel: threading.Event | None = None,
             keep_old: bool = False) -> Path:
    """Fetch every file pinned to m.revision, verify, then activate.

    `.part` files resume on the next attempt. The previous version stays usable until
    the new one has verified; only then is it (optionally) deleted.
    """
    model = get_model(m.model)
    dest = model_dir(m.model) / m.dirname

    def url_for(name):
        return (m.base_url + name) if m.base_url else f"{HF}/{model.repo}/resolve/{m.revision}/{model.path(name)}"
    fetch_files(dest, {n: m.files[n] for n in FILES}, url_for, on_progress, cancel)

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
    print("latest:", latest.debug_label)
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
