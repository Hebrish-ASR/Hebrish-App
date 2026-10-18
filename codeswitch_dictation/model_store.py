"""The fine-tune's weights on disk, and the check against Hugging Face.

Same protocol as the Android app (Codeswitch Voice, docs/maintaining.md):

1. GET /api/models/<repo>/revision/main            -> sha `main` points at now
2. GET /api/models/<repo>/tree/<sha>/sherpa-onnx/int8 -> per file size + lfs.oid (SHA-256)
3. GET /<repo>/resolve/<sha>/sherpa-onnx/int8/version.json -> {"version": "v4", "run": ...}
   (optional; only sets the label)

An update is offered when the weights differ, never because `main` moved: model-card
and eval commits move `main` many times a day without touching the weights.

Each installed model lives in models/<version>-<sha12>/ and is complete only once its
manifest.json exists (written last, after every file verified).
"""

import hashlib
import json
import shutil
import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .config import MODELS_DIR, STATE_PATH, load_json, save_json

REPO = "danielrosehill/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching"
SUBDIR = "sherpa-onnx/int8"
FILES = ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt")
HF = "https://huggingface.co"
USER_AGENT = "codeswitch-dictation (+https://github.com/danielrosehill)"


class Cancelled(Exception):
    pass


@dataclass
class Manifest:
    revision: str                    # full commit sha the files were fetched at
    version: str                     # "v4", or "rev abc1234" without version.json
    run: str = ""
    files: dict = field(default_factory=dict)   # name -> {"size": int, "sha256": str|None}

    @property
    def dirname(self) -> str:
        label = self.version if not self.version.startswith("rev ") else "rev"
        return f"{label}-{self.revision[:12]}"

    @property
    def label(self) -> str:
        run = f", {self.run}" if self.run else ""
        return f"{self.version}{run} (rev {self.revision[:7]})"

    @property
    def total_size(self) -> int:
        return sum(f["size"] for f in self.files.values())

    def same_weights(self, other: "Manifest") -> bool:
        """tokens.txt is a plain git file (no lfs.oid), so only its size is compared."""
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
        return {"revision": self.revision, "version": self.version, "run": self.run,
                "files": self.files}

    @classmethod
    def from_json(cls, d: dict) -> "Manifest":
        return cls(d["revision"], d["version"], d.get("run", ""), d.get("files", {}))


# -- remote ------------------------------------------------------------------

def _get(url: str, timeout=20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def manifest_from_tree(sha: str, tree: list, version_info: dict | None) -> Manifest:
    files = {}
    for entry in tree:
        name = entry["path"].rsplit("/", 1)[-1]
        if name in FILES:
            lfs = entry.get("lfs") or {}
            files[name] = {"size": entry["size"], "sha256": lfs.get("oid")}
    missing = [f for f in FILES if f not in files]
    if missing:
        raise RuntimeError(f"HF revision {sha[:7]} is missing {', '.join(missing)}")
    version = (version_info or {}).get("version") or f"rev {sha[:7]}"
    return Manifest(sha, version, (version_info or {}).get("run", ""), files)


def fetch_latest() -> Manifest:
    sha = json.loads(_get(f"{HF}/api/models/{REPO}/revision/main"))["sha"]
    tree = json.loads(_get(f"{HF}/api/models/{REPO}/tree/{sha}/{SUBDIR}"))
    try:
        info = json.loads(_get(f"{HF}/{REPO}/resolve/{sha}/{SUBDIR}/version.json"))
    except Exception:
        info = None
    return manifest_from_tree(sha, tree, info)


# -- local -------------------------------------------------------------------

def installed() -> list[tuple[Path, Manifest]]:
    """Complete installs, newest first (by manifest mtime)."""
    out = []
    if MODELS_DIR.is_dir():
        for d in MODELS_DIR.iterdir():
            mf = d / "manifest.json"
            if mf.is_file():
                try:
                    out.append((d, Manifest.from_json(json.loads(mf.read_text()))))
                except (ValueError, KeyError):
                    continue
    out.sort(key=lambda t: (t[0] / "manifest.json").stat().st_mtime, reverse=True)
    return out


def active() -> tuple[Path, Manifest] | None:
    """The install state.json names, else the newest complete one."""
    all_ = installed()
    want = load_json(STATE_PATH).get("active")
    for d, m in all_:
        if d.name == want:
            return d, m
    return all_[0] if all_ else None


def set_active(dirname: str):
    state = load_json(STATE_PATH)
    state["active"] = dirname
    save_json(STATE_PATH, state)


def remove(dirname: str):
    target = (MODELS_DIR / dirname).resolve()
    if target.parent != MODELS_DIR.resolve():     # never leave our own folder
        raise ValueError(dirname)
    shutil.rmtree(target)


def prune_except(keep: str):
    for d, _m in installed():
        if d.name != keep:
            remove(d.name)
    # half-finished downloads of other versions
    if MODELS_DIR.is_dir():
        for d in MODELS_DIR.iterdir():
            if d.is_dir() and d.name != keep and not (d / "manifest.json").exists():
                shutil.rmtree(d, ignore_errors=True)


def needs_update(latest: Manifest) -> bool:
    cur = active()
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

    `.part` files resume on the next attempt. The previous model stays usable until
    the new one has verified; only then is it (optionally) deleted.
    """
    dest = MODELS_DIR / m.dirname
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
        url = f"{HF}/{REPO}/resolve/{m.revision}/{SUBDIR}/{name}"
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
    set_active(dest.name)
    if not keep_old:
        prune_except(dest.name)
    return dest


def main():
    import argparse
    import sys
    p = argparse.ArgumentParser(prog="codeswitch-dictation-model")
    p.add_argument("cmd", choices=["status", "check", "download"])
    p.add_argument("--replace", action="store_true", help="delete older versions after download")
    a = p.parse_args()
    cur = active()
    rows = [f"  {d.name}{'  (active)' if cur and d == cur[0] else ''}" for d, _ in installed()]
    print("installed:", *(rows or ["  none"]), sep="\n")
    if a.cmd == "status":
        return
    latest = fetch_latest()
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
