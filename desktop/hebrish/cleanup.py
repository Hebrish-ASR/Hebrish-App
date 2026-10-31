"""Dictation clean-up (B-40): a clean-up model run on a finished Transcription-tab transcript when
the user has downloaded it and turned it on. Desktop only. Since 2026-10-30 (Daniel) there is a
choice: stock S1-mini by Superwhisper (the default) or S1-ASR-Cleanup, Daniel's fine-tune of it
(experimental), one row each in Models → Utilities; `chosen()` says which one *Clean up* uses.

The licence (Apache 2.0 plus a naming term) requires that wherever the app names or describes the
model it is identified as "S1-mini" by "Superwhisper", exact capitalisation (the catalogue's
`short_name`, `label()`).

- The models are listed in the catalogue under `addons` (../shared/catalogue.json, `kind:
  text_cleanup`): the GGUF file on Hugging Face (repo, tag, file name) and the llama.cpp build
  that runs it (a pinned CPU build of `llama-server` per OS, with size and SHA-256). An entry
  still marked "TODO" (not yet published) is not offered.
- Runtime: the stock `llama-server` from ggml-org/llama.cpp's GitHub releases, downloaded with
  the first model into <models>/llama.cpp/<build>/ (shared) and started on first use as a child
  process on 127.0.0.1 (one slot, CPU), stopped after IDLE_S without work and when the app quits.
  No Python LLM package: the .deb and the Windows zip stay as they are, and an install that never
  downloads the add-on runs no llama.cpp code at all. Why not llama-cpp-python: no prebuilt wheels
  on PyPI, so it would have to be compiled into every .deb and Windows build (maintaining.md).
- Prompt: exactly as the model was trained (ASR-Post-Processor-Model training/s1mini_lora.py,
  `render_prompt(text, "1,2")`): S1-mini's system prompt verbatim, the control line, a newline,
  the transcript; the Qwen3 template with an empty think block. Greedy, n_predict = 1.3 x input
  tokens + 32. Inputs above MAX_INPUT_TOKENS are cut at sentence ends and cleaned chunk by chunk.
- Never loses text: a chunk whose output is empty, cut off by the token limit, timed out, failed,
  or dropped a personal-dictionary word keeps its raw text (`accept`).

No Qt import: ui/transcribe.py runs `clean()` on a worker thread.
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import model_store

DEFAULT_ID = "s1-mini"           # the catalogue's `default: true` entry decides; this is for tests/docs
LEGACY_ID = "s1-asr-cleanup"     # 1.013's only model; its runtime folder is adopted (`_adopt`)
LEGACY_RUNTIME = "runtime"
RUNTIME_ROOT = "llama.cpp"       # <models>/llama.cpp/<build>/, shared by every clean-up model
SERVER = "llama-server.exe" if sys.platform == "win32" else "llama-server"

# -- prompt (verbatim from ASR-Post-Processor-Model training/s1mini_lora.py) -------------------
SYSTEM_PROMPT = (
    "You are a text normalizer for speech-to-text transcripts. The input begins "
    "with a control line specifying the styling, structure, and context settings; "
    "clean the transcript to match those settings and output only the cleaned text."
)
CONTROL_LINE = "[Styling: semi-formal] [Structure: prose] [Context: general] [Layers: 1,2]"   # control_line("1,2")
ASSISTANT_PREFIX = "<|im_start|>assistant\n<think>\n\n</think>\n\n"
END_OF_TURN = "<|im_end|>"

MAX_INPUT_TOKENS = 900       # the model card: keep inputs under about 1,000 tokens
CTX = 4096                   # system ~60 + input <= 900 (a lone long sentence may exceed it) + output
IDLE_S = 600                 # stop llama-server after 10 minutes without a request
START_TIMEOUT_S = 90         # loading the 650 MB model from a cold disk


def render_prompt(transcript: str) -> str:
    """The full prompt up to and including the assistant prefix, byte-identical to
    s1mini_lora.render_prompt(transcript, "1,2")."""
    return (
        f"<|im_start|>system\n{SYSTEM_PROMPT}{END_OF_TURN}\n"
        f"<|im_start|>user\n{CONTROL_LINE}\n{transcript}{END_OF_TURN}\n"
        f"{ASSISTANT_PREFIX}"
    )


def max_tokens(input_tokens: int) -> int:
    """The output ceiling the S1-mini card recommends: 1.3 x input tokens + 32."""
    return int(1.3 * input_tokens) + 32


def timeout_for(n_predict: int) -> float:
    """Seconds one chunk may take: generous for a slow laptop CPU (~10 tokens/s), then give up."""
    return 30.0 + n_predict / 10.0


# -- chunks and the guard ------------------------------------------------------------------

_SENTENCE = re.compile(r"(?<=[.!?…])\s+|\n\s*\n")


def sentences(text: str) -> list[str]:
    return [s for s in (p.strip() for p in _SENTENCE.split(text)) if s]


def split_chunks(text: str, count, limit: int = MAX_INPUT_TOKENS) -> list[str]:
    """`text` as chunks of whole sentences of at most `limit` tokens each (count(str) -> int).
    A single sentence over the limit is a chunk of its own: never cut mid-sentence."""
    text = text.strip()
    if not text:
        return []
    if count(text) <= limit:
        return [text]
    out, cur, have = [], [], 0
    for s in sentences(text):
        n = count(s) + 1
        if cur and have + n > limit:
            out.append(" ".join(cur))
            cur, have = [], 0
        cur.append(s)
        have += n
    if cur:
        out.append(" ".join(cur))
    return out


def _has(text: str, word: str) -> bool:
    """`word` in `text` as a whole word: exact case for a word with a capital (the dictionary
    writes those as given), any case otherwise."""
    flags = 0 if word != word.lower() else re.IGNORECASE
    pat = r"\s+".join(re.escape(p) for p in word.split())
    return re.search(r"(?<!\w)" + pat + r"(?!\w)", text, flags) is not None


def accept(raw: str, out: str, stop: str = "eos", keep: tuple = ()) -> bool:
    """Whether the model's `out` may replace `raw`: not empty, not cut off by the token limit
    (`stop` == "limit"), and every word of `keep` (the personal dictionary) that is in `raw` is
    still in `out` (research/post-processing, "a guard for S1-mini")."""
    if not out.strip() and raw.strip():
        return False
    if stop == "limit":
        return False
    return all(_has(out, w) for w in keep if _has(raw, w))


def tidy(out: str) -> str:
    """The model's reply as text: the end-of-turn token and any think block removed, and
    paragraphs separated by exactly one blank line."""
    out = out.replace(END_OF_TURN, "")
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S)
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", out)]
    return "\n\n".join(p for p in paras if p)


@dataclass
class Result:
    text: str          # what goes in the transcript: cleaned, or raw where a chunk fell back
    chunks: int        # chunks sent to the model
    kept_raw: int      # chunks that fell back to their raw text
    error: str = ""    # the first failure, for the status line
    model: str = ""    # the catalogue id and version that ran (run() sets them), for History
    version: str = ""
    name: str = ""     # its display name (label())

    @property
    def cleaned(self) -> bool:
        """At least one chunk was cleaned."""
        return self.chunks > self.kept_raw


def clean(text: str, client, keep: tuple = ()) -> Result:
    """Clean `text` with `client` (`count(str) -> int`, `complete(prompt, n_predict, timeout) ->
    (content, stop_type)`; `Server` in the app, a fake in the tests). Chunks are joined with a
    paragraph break. Any failure keeps that chunk's raw text, so nothing is lost; a failure to
    count tokens at all returns `text` unchanged."""
    raw = text.strip()
    if not raw:
        return Result(text, 0, 0)
    try:
        chunks = split_chunks(raw, client.count)
    except Exception as e:
        return Result(text, 1, 1, str(e) or type(e).__name__)
    out, kept, first = [], 0, ""
    for chunk in chunks:
        try:
            n_predict = max_tokens(client.count(chunk))
            content, stop = client.complete(render_prompt(chunk), n_predict, timeout_for(n_predict))
            got = tidy(content)
            if accept(chunk, got, stop, keep):
                out.append(got)
                continue
            why = ("cut off" if stop == "limit" else "empty reply" if not got else
                   "changed a dictionary word")
        except Exception as e:
            why = str(e) or type(e).__name__
        kept += 1
        first = first or why
        out.append(chunk)
    return Result("\n\n".join(out), len(chunks), kept, first)


# -- catalogue entries ----------------------------------------------------------------------

KINDS = ("text_cleanup", "text_title")    # GGUF add-ons on the llama-server runtime (titles.py: B-75)


def _all(kind: str | None = "text_cleanup") -> list[dict]:
    """Every add-on of `kind` in the catalogue (None: every llama-server kind, KINDS), offered or
    not. A cached catalogue from before the add-on existed has none, so the bundled copy is the
    fallback."""
    kinds = KINDS if kind is None else (kind,)
    for doc in (model_store.catalogue(), model_store.bundled_catalogue()):
        found = [a for a in doc.get("addons", []) if a.get("kind") in kinds]
        if found:
            return found
    return []


def _pending(v) -> bool:
    return not v or v == "TODO"


def offered(e: dict) -> bool:
    """Published (no "TODO" or empty version, repo, tag or file) and runnable on this OS (listed
    in `platforms`, with a pinned llama.cpp build under `runtime`)."""
    if any(_pending(e.get(k)) for k in ("version", "repo", "revision", "file")):
        return False
    rt = e.get("runtime") or {}
    return model_store.PLATFORM in e.get("platforms", []) and model_store.PLATFORM in rt and bool(rt.get("build"))


def entries(kind: str | None = "text_cleanup") -> list[dict]:
    """The clean-up models (or add-ons of `kind`; None: all) this computer can use: the
    `default: true` one first, then catalogue order."""
    out = [e for e in _all(kind) if offered(e)]
    return sorted(out, key=lambda e: not e.get("default"))


def entry(aid: str) -> dict:
    """The offered entry with id `aid`, of any llama-server kind."""
    for e in entries(None):
        if e["id"] == aid:
            return e
    raise RuntimeError(f"the catalogue offers no clean-up model {aid!r}")


def chosen(pick: str | None = None) -> dict | None:
    """The model *Clean up* uses. `pick` is the user's choice (`tm_cleanup_model`); it counts while
    the catalogue still offers it. Without one: an installed model, the default first (so a 1.013
    install of S1-ASR-Cleanup keeps working); else the `default: true` entry; else the first."""
    es = entries()
    for e in es:
        if pick and e["id"] == pick:
            return e
    for e in es:
        if installed(e["id"]) is not None:
            return e
    return next((e for e in es if e.get("default")), es[0] if es else None)


def ready(pick: str | None = None) -> dict | None:
    """chosen(pick) when it is installed, else None: whether *Clean up* can run."""
    e = chosen(pick)
    return e if e is not None and installed(e["id"]) is not None else None


def supported() -> bool:
    """At least one clean-up model runs here (Linux and Windows on x86-64)."""
    try:
        return bool(entries())
    except (OSError, ValueError):
        return False


def label(e: dict) -> str:
    """The name shown in the app. Licence: it must read "S1-mini" by "Superwhisper"."""
    return e.get("short_name") or e["name"]


# -- on disk and download -------------------------------------------------------------------
# <models>/<id>/<version>/             the GGUF, manifest.json written last
# <models>/llama.cpp/<build>/          llama-server and its libraries, shared by every model;
#                                      .complete written last
# 1.013 kept the runtime in <models>/s1-asr-cleanup/runtime/<build>/; it is moved (`_adopt`).

def root(aid: str) -> Path:
    """<models>/<id>: beside the speech models, so it moves with the model folder."""
    return model_store.ROOT / aid


def runtime_root() -> Path:
    return model_store.ROOT / RUNTIME_ROOT


def _model_dir(e: dict) -> Path:
    return root(e["id"]) / "".join(c if c.isalnum() or c in "-_." else "_" for c in e["version"])


def _runtime_dir(e: dict) -> Path:
    return runtime_root() / e["runtime"]["build"]


def _adopt(build: str):
    """Move 1.013's runtime (<models>/s1-asr-cleanup/runtime/<build>/) to the shared folder, so an
    existing install isn't downloaded again. A rename on the same disk; anything else there is
    left for download() to clear."""
    old, new = root(LEGACY_ID) / LEGACY_RUNTIME / build, runtime_root() / build
    if not (old / ".complete").is_file() or (new / ".complete").is_file():
        return
    try:
        shutil.rmtree(new, ignore_errors=True)
        new.parent.mkdir(parents=True, exist_ok=True)
        os.replace(old, new)
        shutil.rmtree(old.parent, ignore_errors=True)
    except OSError:
        pass                              # still works: download() fetches the runtime again


def _runtime_ok(rt: Path) -> bool:
    return (rt / ".complete").is_file() and (rt / SERVER).is_file()


def installed(aid: str) -> tuple[Path, Path] | None:
    """(the GGUF file, the llama-server binary) when the offered model `aid` and the runtime are
    both complete, else None."""
    try:
        e = entry(aid)
    except (RuntimeError, OSError, ValueError):
        return None
    folder = _model_dir(e)
    gguf = folder / e["file"]
    if not ((folder / "manifest.json").is_file() and gguf.is_file()):
        return None
    _adopt(e["runtime"]["build"])
    rt = _runtime_dir(e)
    return (gguf, rt / SERVER) if _runtime_ok(rt) else None


def model_files(e: dict) -> dict:
    """{file: {"size", "sha256"}} for the GGUF. Size and SHA-256 come from the catalogue when
    pinned, else from Hugging Face's file list at the tag (the LFS oid is the SHA-256)."""
    if e.get("size") and e.get("sha256"):
        return {e["file"]: {"size": e["size"], "sha256": e["sha256"]}}
    tree = json.loads(model_store._get(f"{model_store.HF}/api/models/{e['repo']}/tree/{e['revision']}"))
    for t in tree:
        if t.get("path") == e["file"]:
            sha = (t.get("lfs") or {}).get("oid") or e.get("sha256")
            return {e["file"]: {"size": t["size"], "sha256": sha}}
    raise RuntimeError(f"{e['repo']} at {e['revision']} has no {e['file']}")


def _extract(archive: Path, dest: Path):
    """The server and its libraries from a llama.cpp release archive, flattened into `dest`
    (tar.gz on Linux: one top folder, with .so symlinks; zip on Windows: files at the root)."""
    want = re.compile(r"^(llama-server(\.exe)?|.*\.so(\.\d+)*|.*\.dll)$")
    links = []
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                name = info.filename.rsplit("/", 1)[-1]
                if name and not info.is_dir() and want.match(name):
                    with z.open(info) as src, open(dest / name, "wb") as dst:
                        shutil.copyfileobj(src, dst)
    else:
        with tarfile.open(archive) as t:
            for m in t.getmembers():
                name = m.name.rsplit("/", 1)[-1]
                if not name or not want.match(name):
                    continue
                if m.issym():
                    links.append((name, m.linkname.rsplit("/", 1)[-1]))
                elif m.isfile():
                    with t.extractfile(m) as src, open(dest / name, "wb") as dst:
                        shutil.copyfileobj(src, dst)
    for name, target in links:
        p = dest / name
        if p.exists() or p.is_symlink() or not (dest / target).exists():
            continue
        try:
            os.symlink(target, p)
        except OSError:                   # a file system without symlinks
            shutil.copy2(dest / target, p)
    if not (dest / SERVER).is_file():
        raise RuntimeError(f"{archive.name} has no {SERVER}")
    if sys.platform != "win32":
        (dest / SERVER).chmod(0o755)


_runtime_lock = threading.Lock()       # two models downloading at once fetch the runtime once


def download(aid: str, on_progress=None, cancel: threading.Event | None = None) -> Path:
    """Fetch the shared llama.cpp runtime (if not already there) and model `aid`, verify both,
    then make them the installed ones (older versions of that model and runtime builds no
    catalogue entry pins are deleted). on_progress(done_bytes, total, name)."""
    e = entry(aid)
    rt_info = e["runtime"][model_store.PLATFORM]
    rt, folder = _runtime_dir(e), _model_dir(e)
    files = model_files(e)
    _adopt(e["runtime"]["build"])
    rt_size = 0 if _runtime_ok(rt) else rt_info["size"]
    total = rt_size + sum(f["size"] for f in files.values())

    def prog(offset):
        return (lambda d, _t, n: on_progress(offset + d, total, n)) if on_progress else None

    with _runtime_lock:
        if not _runtime_ok(rt):
            archive = rt_info["url"].rsplit("/", 1)[-1]
            stage = runtime_root() / ".download"
            model_store.fetch_files(stage, {archive: {"size": rt_info["size"], "sha256": rt_info["sha256"]}},
                                    lambda _n: rt_info["url"], prog(0), cancel)
            shutil.rmtree(rt, ignore_errors=True)
            rt.mkdir(parents=True)
            _extract(stage / archive, rt)
            (rt / ".complete").write_text(e["runtime"]["build"] + "\n")
            shutil.rmtree(stage, ignore_errors=True)
    url = f"{model_store.HF}/{e['repo']}/resolve/{e['revision']}/"
    model_store.fetch_files(folder, files, lambda n: url + n, prog(rt_size), cancel)
    (folder / "manifest.json").write_text(json.dumps(
        {"id": aid, "version": e["version"], "repo": e["repo"], "revision": e["revision"],
         "files": files}, indent=2))
    for d in root(aid).iterdir():             # older versions (and 1.013's runtime folder, if left)
        if d.is_dir() and d.name != folder.name:
            shutil.rmtree(d, ignore_errors=True)
    builds = {(a.get("runtime") or {}).get("build") for a in _all(None)}
    with _runtime_lock:
        for d in runtime_root().iterdir():
            if d.is_dir() and d.name not in builds:
                shutil.rmtree(d, ignore_errors=True)
    return folder


def remove(aid: str):
    """Delete model `aid` (stopping its llama-server first); the shared runtime goes too once no
    llama-server add-on (clean-up or title) is left."""
    stop(aid)
    shutil.rmtree(root(aid), ignore_errors=True)
    if not any((_model_dir(e) / "manifest.json").is_file() for e in _all(None)
               if not any(_pending(e.get(k)) for k in ("version", "file"))):
        shutil.rmtree(runtime_root(), ignore_errors=True)
        shutil.rmtree(root(LEGACY_ID) / LEGACY_RUNTIME, ignore_errors=True)


# -- the llama-server child process -------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    """One llama-server process for the installed model, started on first use."""

    def __init__(self, gguf: Path, binary: Path, threads: int = 0):
        self.gguf, self.binary = Path(gguf), Path(binary)
        self.threads = threads or max(1, (os.cpu_count() or 2) // 2)
        self.proc: subprocess.Popen | None = None
        self.port = 0
        self.used = time.monotonic()
        self._lock = threading.RLock()

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def _post(self, path: str, body: dict, timeout: float) -> dict:
        req = urllib.request.Request(self._url(path), data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def start(self):
        with self._lock:
            if self.proc is not None and self.proc.poll() is None:
                return
            self.port = _free_port()
            cmd = [str(self.binary), "-m", str(self.gguf), "--host", "127.0.0.1", "--port", str(self.port),
                   "-c", str(CTX), "-np", "1", "-t", str(self.threads), "--no-webui"]
            kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
            self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, cwd=str(self.binary.parent), **kw)
            end = time.monotonic() + START_TIMEOUT_S
            while time.monotonic() < end:
                if self.proc.poll() is not None:
                    self.proc = None
                    raise RuntimeError("the clean-up runtime exited while starting")
                try:
                    with urllib.request.urlopen(self._url("/health"), timeout=2) as r:
                        if r.status == 200:
                            return
                except OSError:
                    pass
                time.sleep(0.25)
            self.stop()
            raise TimeoutError("the clean-up model took too long to load")

    def stop(self):
        with self._lock:
            p, self.proc = self.proc, None
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()             # reap it: no zombie until the next start

    def count(self, text: str) -> int:
        self.start()
        self.used = time.monotonic()
        return len(self._post("/tokenize", {"content": text}, 30)["tokens"])

    def complete(self, prompt: str, n_predict: int, timeout: float,
                 stop: tuple = (END_OF_TURN,)) -> tuple[str, str]:
        self.start()
        try:
            r = self._post("/completion", {"prompt": prompt, "n_predict": n_predict, "temperature": 0,
                                           "top_k": 1, "stop": list(stop), "cache_prompt": True},
                           timeout)
        except TimeoutError:
            self.stop()                    # don't leave it generating into the next request
            raise TimeoutError("the clean-up model timed out") from None
        finally:
            self.used = time.monotonic()
        return r.get("content", ""), r.get("stop_type", "eos")


_servers: dict[str, Server] = {}   # one llama-server per add-on id (clean-up, title), kept between uses
_server_lock = threading.Lock()
_reaper: threading.Thread | None = None


def server(aid: str) -> Server:
    """The running (or startable) server for add-on `aid`, kept between transcripts. A newer
    install of `aid` (another GGUF or runtime) stops the old process; the next request starts one
    with the new files. Raises when `aid` isn't installed."""
    global _reaper
    have = installed(aid)
    if have is None:
        raise FileNotFoundError("the model isn't downloaded")
    with _server_lock:
        s = _servers.get(aid)
        if s is None or (s.gguf, s.binary) != tuple(Path(p) for p in have):
            if s is not None:
                s.stop()
            s = _servers[aid] = Server(*have)
        if _reaper is None or not _reaper.is_alive():
            _reaper = threading.Thread(target=_reap, daemon=True, name="cleanup-idle")
            _reaper.start()
        return s


def _reap():
    """Stop each llama-server (and free its memory) after IDLE_S without a request."""
    while True:
        time.sleep(30)
        for s in list(_servers.values()):
            if s.proc is not None and time.monotonic() - s.used > IDLE_S:
                s.stop()


def stop(aid: str | None = None):
    """Stop the server for `aid`, or every one (app quit), if it runs."""
    for k, s in list(_servers.items()):
        if aid is None or k == aid:
            s.stop()


def run(text: str, keep: tuple = (), aid: str | None = None) -> Result:
    """Clean `text` with model `aid` (default: chosen()); any failure keeps the raw text
    (Result.error). Result.model and .version say which model it was."""
    try:
        e = entry(aid) if aid else chosen()
        if e is None:
            raise FileNotFoundError("the clean-up model isn't downloaded")
        s = server(e["id"])
    except Exception as ex:
        return Result(text, 1, 1, str(ex))
    r = clean(text, s, keep)
    r.model, r.version, r.name = e["id"], e["version"], label(e)
    return r
