"""Dictation clean-up (B-40): S1-ASR-Cleanup, a fine-tune of S1-mini by Superwhisper, run on a
finished Transcription-tab transcript when the user has downloaded it and turned it on. Desktop only.

The licence (Apache 2.0 plus a naming term) requires that wherever the app names or describes the
model it is identified as "S1-mini" by "Superwhisper", exact capitalisation (`DISPLAY_NAME`).

- The add-on is listed in the catalogue under `addons` (../shared/catalogue.json, id
  `s1-asr-cleanup`): the GGUF file on Hugging Face (repo, tag, file name) and the llama.cpp build
  that runs it (a pinned CPU build of `llama-server` per OS, with size and SHA-256).
- Runtime: the stock `llama-server` from ggml-org/llama.cpp's GitHub releases, downloaded with
  the model into <models>/s1-asr-cleanup/runtime/<build>/ and started on first use as a child
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

MODEL_ID = "s1-asr-cleanup"
DISPLAY_NAME = "S1-ASR-Cleanup (fine-tune of S1-mini by Superwhisper)"   # licence: keep "S1-mini" by "Superwhisper"
CARD = "https://huggingface.co/danielrosehill/S1-ASR-Cleanup"
RUNTIME_DIR = "runtime"
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


# -- catalogue entry ---------------------------------------------------------------------

def entry() -> dict:
    """The add-on's catalogue entry. A cached catalogue from before the add-on existed has no
    `addons`, so the bundled copy is the fallback."""
    for doc in (model_store.catalogue(), model_store.bundled_catalogue()):
        for a in doc.get("addons", []):
            if a.get("id") == MODEL_ID:
                return a
    raise RuntimeError("the catalogue has no clean-up model")


def supported() -> bool:
    """This OS has a pinned llama.cpp build (Linux and Windows on x86-64)."""
    try:
        e = entry()
    except (RuntimeError, OSError, ValueError):
        return False
    return model_store.PLATFORM in e.get("platforms", []) and model_store.PLATFORM in e["runtime"]


# -- on disk and download -------------------------------------------------------------------

def root() -> Path:
    """<models>/s1-asr-cleanup: beside the speech models, so it moves with the model folder."""
    return model_store.ROOT / MODEL_ID


def _model_dir(e: dict) -> Path:
    return root() / "".join(c if c.isalnum() or c in "-_." else "_" for c in e["version"])


def _runtime_dir(e: dict) -> Path:
    return root() / RUNTIME_DIR / e["runtime"]["build"]


def installed() -> tuple[Path, Path] | None:
    """(the GGUF file, the llama-server binary) when both are complete, else None. The model is
    complete once its manifest.json is written (last); the runtime once its `.complete` marker is."""
    try:
        e = entry()
    except (RuntimeError, OSError, ValueError):
        return None
    folder, rt = _model_dir(e), _runtime_dir(e)
    gguf, server = folder / e["file"], rt / SERVER
    if (folder / "manifest.json").is_file() and gguf.is_file() and (rt / ".complete").is_file() and server.is_file():
        return gguf, server
    return None


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


def download(on_progress=None, cancel: threading.Event | None = None) -> Path:
    """Fetch the llama.cpp runtime (if not already there) and the model, verify both, then make
    them the installed ones (older versions are deleted). on_progress(done_bytes, total, name)."""
    e = entry()
    if not supported():
        raise RuntimeError("the clean-up model isn't available on this computer")
    rt_info = e["runtime"][model_store.PLATFORM]
    rt, folder = _runtime_dir(e), _model_dir(e)
    files = model_files(e)
    rt_size = 0 if (rt / ".complete").is_file() else rt_info["size"]
    total = rt_size + sum(f["size"] for f in files.values())

    def prog(offset):
        return (lambda d, _t, n: on_progress(offset + d, total, n)) if on_progress else None

    if rt_size:
        archive = rt_info["url"].rsplit("/", 1)[-1]
        stage = root() / RUNTIME_DIR / ".download"
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
        {"id": MODEL_ID, "version": e["version"], "repo": e["repo"], "revision": e["revision"],
         "files": files}, indent=2))
    for d in root().iterdir():                # older model versions; the runtime folder stays
        if d.is_dir() and d.name not in (folder.name, RUNTIME_DIR):
            shutil.rmtree(d, ignore_errors=True)
    for d in (root() / RUNTIME_DIR).iterdir():
        if d.is_dir() and d.name != rt.name:
            shutil.rmtree(d, ignore_errors=True)
    return folder


def remove():
    stop()
    shutil.rmtree(root(), ignore_errors=True)


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

    def complete(self, prompt: str, n_predict: int, timeout: float) -> tuple[str, str]:
        self.start()
        try:
            r = self._post("/completion", {"prompt": prompt, "n_predict": n_predict, "temperature": 0,
                                           "top_k": 1, "stop": [END_OF_TURN], "cache_prompt": True},
                           timeout)
        except TimeoutError:
            self.stop()                    # don't leave it generating into the next request
            raise TimeoutError("the clean-up model timed out") from None
        finally:
            self.used = time.monotonic()
        return r.get("content", ""), r.get("stop_type", "eos")


_server: Server | None = None
_server_lock = threading.Lock()
_reaper: threading.Thread | None = None


def server() -> Server:
    """The running (or startable) server for the installed add-on, kept between transcripts.
    Raises when the add-on isn't installed."""
    global _server, _reaper
    have = installed()
    if have is None:
        raise FileNotFoundError("the clean-up model isn't downloaded")
    with _server_lock:
        if _server is None or (_server.gguf, _server.binary) != have:
            if _server is not None:
                _server.stop()
            _server = Server(*have)
        if _reaper is None or not _reaper.is_alive():
            _reaper = threading.Thread(target=_reap, daemon=True, name="cleanup-idle")
            _reaper.start()
        return _server


def _reap():
    """Stop llama-server (and free its ~1 GB) after IDLE_S without a request."""
    while True:
        time.sleep(30)
        s = _server
        if s is not None and s.proc is not None and time.monotonic() - s.used > IDLE_S:
            s.stop()


def stop():
    """Stop the server if it runs (app quit, the add-on deleted)."""
    s = _server
    if s is not None:
        s.stop()


def run(text: str, keep: tuple = ()) -> Result:
    """Clean `text` with the installed add-on; any failure keeps the raw text (Result.error)."""
    try:
        s = server()
    except Exception as e:
        return Result(text, 1, 1, str(e))
    return clean(text, s, keep)
