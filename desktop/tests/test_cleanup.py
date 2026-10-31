"""Dictation clean-up (B-40): a choice of clean-up models (stock S1-mini by Superwhisper, the
default, and the experimental fine-tune S1-ASR-Cleanup) as optional Utilities add-ons run on
finished Transcription-tab transcripts (hebrish/cleanup.py).

The runtime (llama-server) and the model are always faked here: nothing is downloaded and no
process is started. The real model was smoke-tested by hand (desktop/docs/maintaining.md,
"Clean-up model")."""

import importlib.util
import io
import json
import os
import tarfile
import threading
import time
import zipfile
from pathlib import Path

import pytest

from hebrish import cleanup as C
from hebrish import model_store

TRAINING = (Path(__file__).resolve().parents[3] / "ASR-Post-Processor-Model" / "training" / "s1mini_lora.py")


# -- prompt ------------------------------------------------------------------------------

def test_prompt_is_the_training_format():
    assert C.render_prompt("so um hi there") == (
        "<|im_start|>system\nYou are a text normalizer for speech-to-text transcripts. The input begins "
        "with a control line specifying the styling, structure, and context settings; clean the "
        "transcript to match those settings and output only the cleaned text.<|im_end|>\n"
        "<|im_start|>user\n[Styling: semi-formal] [Structure: prose] [Context: general] [Layers: 1,2]\n"
        "so um hi there<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n")


def test_prompt_matches_the_training_script_when_checked_out():
    """Byte-identical to ASR-Post-Processor-Model's render_prompt(text, "1,2"); runs only where
    that repo is checked out beside this one (not in CI)."""
    if not TRAINING.exists():
        pytest.skip("ASR-Post-Processor-Model not checked out")
    spec = importlib.util.spec_from_file_location("s1mini_lora", TRAINING)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert C.SYSTEM_PROMPT == mod.SYSTEM_PROMPT
    assert C.CONTROL_LINE == mod.control_line("1,2")
    for text in ("hello", "two lines\nof text", ""):
        assert C.render_prompt(text) == mod.render_prompt(text, "1,2")


def test_max_tokens_is_the_cards_ceiling():
    assert C.max_tokens(0) == 32
    assert C.max_tokens(100) == 162
    assert C.max_tokens(900) == 1202


# -- chunks, guard, tidy ---------------------------------------------------------------------

def words(s):
    return len(s.split())


def test_short_text_is_one_chunk():
    assert C.split_chunks("  one two three.  ", words, limit=10) == ["one two three."]
    assert C.split_chunks("   ", words) == []


def test_long_text_splits_at_sentence_ends():
    text = "A b c. D e f. G h i? J k l! M n o."
    chunks = C.split_chunks(text, words, limit=8)
    assert chunks == ["A b c. D e f.", "G h i? J k l!", "M n o."]
    assert " ".join(chunks) == text


def test_a_sentence_over_the_limit_is_never_cut():
    long = " ".join(["w"] * 20) + "."
    assert C.split_chunks(long + " Short one.", words, limit=8) == [long, "Short one."]


def test_accept():
    assert C.accept("so um hi", "So, hi.")
    assert not C.accept("so um hi", "  ")
    assert C.accept("", "")
    assert not C.accept("so um hi", "So, hi", stop="limit")
    # personal dictionary: a word in the input must survive
    assert C.accept("ask about arnona", "Ask about Arnona.", keep=("arnona",))
    assert not C.accept("ask about arnona", "Ask about the tax.", keep=("arnona",))
    assert not C.accept("ask Kubernetes", "Ask kubernetes.", keep=("Kubernetes",))   # capital: exact
    assert C.accept("nothing here", "Nothing here.", keep=("arnona",))               # not in input


def test_tidy():
    assert C.tidy("Hello there.<|im_end|>") == "Hello there."
    assert C.tidy("<think>\n\n</think>\n\nHi.") == "Hi."
    assert C.tidy("One.\n\n\n\nTwo  words.\n \nThree.") == "One.\n\nTwo words.\n\nThree."


# -- clean() with a fake runtime ---------------------------------------------------------------

class FakeClient:
    """count() is words; complete() answers from `replies` (a function of the transcript)."""

    def __init__(self, reply=lambda t: (t.capitalize() + ".", "eos")):
        self.reply = reply
        self.calls = []

    def count(self, text):
        return words(text)

    def complete(self, prompt, n_predict, timeout):
        transcript = prompt.split(C.CONTROL_LINE + "\n", 1)[1].split(C.END_OF_TURN, 1)[0]
        self.calls.append((transcript, n_predict, timeout))
        r = self.reply(transcript)
        if isinstance(r, Exception):
            raise r
        return r


def test_clean_replaces_the_text():
    c = FakeClient(lambda t: ("So, hi there.<|im_end|>", "eos"))
    r = C.clean("so um hi there", c)
    assert (r.text, r.chunks, r.kept_raw, r.cleaned) == ("So, hi there.", 1, 0, True)
    assert c.calls[0][1] == C.max_tokens(4)


@pytest.mark.parametrize("reply", [("", "eos"), ("So, hi", "limit"), TimeoutError("timed out"),
                                   OSError("connection refused")])
def test_any_failure_keeps_the_raw_text(reply):
    r = C.clean("so um hi there", FakeClient(lambda t: reply))
    assert r.text == "so um hi there" and r.kept_raw == 1 and not r.cleaned and r.error


def test_dictionary_word_dropped_keeps_the_raw_text():
    r = C.clean("pay the arnona", FakeClient(lambda t: ("Pay the tax.", "eos")), keep=("arnona",))
    assert r.text == "pay the arnona" and r.error == "changed a dictionary word"


def test_count_failure_returns_the_text_unchanged():
    class Broken(FakeClient):
        def count(self, text):
            raise OSError("not running")
    r = C.clean("so um hi", Broken())
    assert r.text == "so um hi" and not r.cleaned


def test_chunks_fall_back_one_by_one(monkeypatch):
    monkeypatch.setattr(C, "MAX_INPUT_TOKENS", 4)
    monkeypatch.setattr(C, "split_chunks", lambda t, count: [s.strip() for s in t.split("|")])
    replies = {"first part": ("First part.", "eos"), "second part": ("", "eos"), "third part": ("Third part.", "eos")}
    r = C.clean("first part | second part | third part", FakeClient(lambda t: replies[t]))
    assert r.text == "First part.\n\nsecond part\n\nThird part."
    assert (r.chunks, r.kept_raw, r.cleaned) == (3, 1, True)


def test_run_without_the_add_on_keeps_the_text(tmp_path, monkeypatch):
    monkeypatch.setattr(model_store, "ROOT", tmp_path)
    assert C.ready() is None
    r = C.run("so um hi")
    assert r.text == "so um hi" and not r.cleaned and "isn't downloaded" in r.error


# -- catalogue -------------------------------------------------------------------------------

REAL = {a["id"]: a for a in model_store.bundled_catalogue()["addons"]}
STOCK = REAL["s1-mini"]
TUNE = REAL["s1-asr-cleanup"]


@pytest.fixture
def cat(monkeypatch):
    """Serve `addons` as the cached catalogue; with no arguments: published stock + fine-tune."""
    monkeypatch.setattr(model_store, "PLATFORM", "linux")

    def use(*addons):
        addons = addons or (STOCK, TUNE)
        monkeypatch.setattr(model_store, "catalogue", lambda: {"lines": [], "addons": list(addons)})
    use()
    return use


def test_catalogue_entries():
    """The shipped catalogue: stock S1-mini by Superwhisper is the default, the fine-tune is
    experimental, both share one llama.cpp build."""
    es = [a for a in model_store.bundled_catalogue()["addons"] if a["kind"] == "text_cleanup"]
    assert [e["id"] for e in es] == [C.DEFAULT_ID, C.LEGACY_ID]
    stock, tune = es
    assert stock["default"] is True and stock["experimental"] is False
    assert tune["default"] is False and tune["experimental"] is True
    for e in es:
        # licence: named "S1-mini" by "Superwhisper", exact capitalisation
        assert "S1-mini by Superwhisper" in e["short_name"] and e["base_label"] == "S1-mini by Superwhisper"
        assert C.label(e) == e["short_name"]
        assert {"linux", "windows"} <= set(e["platforms"]) and "desktop" in e["devices"]
        for os_ in ("linux", "windows"):
            rt = e["runtime"][os_]
            assert rt["url"].startswith("https://github.com/ggml-org/llama.cpp/releases/download/" + e["runtime"]["build"] + "/")
            assert rt["size"] > 0 and len(rt["sha256"]) == 64
    assert stock["short_name"] == "S1-mini by Superwhisper"
    assert stock["runtime"] == tune["runtime"], "one shared runtime"
    for e in es:
        assert e["file"].endswith(".gguf") and e["size"] > 0 and len(e["sha256"]) == 64


def test_shipped_catalogue_offers_both_on_desktop(monkeypatch):
    for os_ in ("linux", "windows"):
        monkeypatch.setattr(model_store, "PLATFORM", os_)
        assert [e["id"] for e in C.entries()] == [C.DEFAULT_ID, C.LEGACY_ID]
    assert C.chosen()["id"] in (C.DEFAULT_ID, C.LEGACY_ID)


def test_todo_entries_are_not_offered(cat):
    """An entry not yet published says "TODO" (as stock S1-mini did until 2026-10-30): not
    offered, and chosen() falls back to what is, even when it was picked."""
    cat({**STOCK, "version": "TODO", "repo": "TODO", "revision": "TODO", "file": "TODO",
         "size": None, "sha256": None, "download_mb": None}, TUNE)
    assert [e["id"] for e in C.entries()] == [C.LEGACY_ID]
    assert C.chosen()["id"] == C.LEGACY_ID and C.chosen(C.DEFAULT_ID)["id"] == C.LEGACY_ID
    with pytest.raises(RuntimeError):
        C.entry(C.DEFAULT_ID)


@pytest.mark.parametrize("change", [{"version": "TODO"}, {"file": "TODO"}, {"repo": None},
                                    {"platforms": ["windows", "android"]},
                                    {"runtime": {k: v for k, v in TUNE["runtime"].items() if k != "linux"}}])
def test_unpublished_or_other_os_entries_are_not_offered(cat, change):
    cat(STOCK, {**TUNE, **change})
    assert [e["id"] for e in C.entries()] == [C.DEFAULT_ID]


def test_default_entry_comes_first(cat):
    cat(TUNE, STOCK)
    assert [e["id"] for e in C.entries()] == [C.DEFAULT_ID, C.LEGACY_ID]


def test_older_cached_catalogue_falls_back_to_the_bundled_entries(monkeypatch):
    monkeypatch.setattr(model_store, "catalogue", lambda: {"lines": []})
    assert C.LEGACY_ID in {e["id"] for e in C._all()}


def test_android_and_speech_models_ignore_addons():
    """The add-ons are not speech models: they never show up among the variants."""
    ids = {m.id for m in model_store.variants()}
    assert C.LEGACY_ID not in ids and C.DEFAULT_ID not in ids


# -- download and install, with fetch_files faked -------------------------------------------

def _tar(members) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in members:
            info = tarfile.TarInfo(name)
            if isinstance(data, tuple):           # ("link", target)
                info.type, info.linkname = tarfile.SYMTYPE, data[1]
                t.addfile(info)
            else:
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _zip(members) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members:
            z.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def fake_fetch(tmp_path, monkeypatch, cat):
    """model_store.fetch_files writes `blobs[name]` instead of downloading; the runtime archive
    and both GGUFs are there."""
    monkeypatch.setattr(model_store, "ROOT", tmp_path / "models")
    monkeypatch.setattr(C, "SERVER", "llama-server")
    blobs, fetched = {}, []
    build = TUNE["runtime"]["build"]
    blobs[TUNE["runtime"]["linux"]["url"].rsplit("/", 1)[-1]] = _tar([
        (f"llama-{build}/llama-server", b"#!/bin/sh\n"),
        (f"llama-{build}/llama-cli", b"not wanted"),
        (f"llama-{build}/libllama.so.0.8.0", b"lib"),
        (f"llama-{build}/libllama.so.0", ("link", "libllama.so.0.8.0")),
        (f"llama-{build}/LICENSE", b"mit"),
    ])
    blobs[TUNE["file"]] = b"TUNE"
    blobs[STOCK["file"]] = b"GGUF"

    def fetch(dest, files, url_for, on_progress=None, cancel=None):
        dest.mkdir(parents=True, exist_ok=True)
        for name, info in files.items():
            fetched.append((name, url_for(name), info))
            (dest / name).write_bytes(blobs[name])
            if on_progress:
                on_progress(len(blobs[name]), len(blobs[name]), name)
    monkeypatch.setattr(model_store, "fetch_files", fetch)
    return blobs, fetched


def test_download_installs_runtime_and_model(fake_fetch):
    blobs, fetched = fake_fetch
    e = TUNE
    old = model_store.ROOT / C.LEGACY_ID / "v0.9"
    old.mkdir(parents=True)
    stale = C.runtime_root() / "b1"
    stale.mkdir(parents=True)
    seen = []
    C.download(C.LEGACY_ID, lambda d, t, n: seen.append((d, t, n)))
    gguf, server = C.installed(C.LEGACY_ID)
    assert gguf.read_bytes() == b"TUNE" and server.name == "llama-server"
    assert gguf.parent == model_store.ROOT / C.LEGACY_ID / e["version"]
    rt = server.parent
    assert rt == model_store.ROOT / C.RUNTIME_ROOT / e["runtime"]["build"], "the shared runtime folder"
    assert sorted(p.name for p in rt.iterdir()) == [".complete", "libllama.so.0", "libllama.so.0.8.0", "llama-server"]
    assert (rt / "libllama.so.0").read_bytes() == b"lib"
    if os.name != "nt":
        assert os.access(server, os.X_OK)
    assert not old.exists(), "older model versions are deleted"
    assert not stale.exists(), "runtime builds no entry pins are deleted"
    assert not (C.runtime_root() / ".download").exists(), "the archive is deleted after extraction"
    urls = [u for _n, u, _i in fetched]
    assert urls[0] == e["runtime"]["linux"]["url"]
    assert urls[1] == f"https://huggingface.co/{e['repo']}/resolve/{e['revision']}/{e['file']}"
    assert fetched[1][2] == {"size": e["size"], "sha256": e["sha256"]}
    assert seen[-1][1] == e["runtime"]["linux"]["size"] + e["size"]      # one progress total
    manifest = json.loads((gguf.parent / "manifest.json").read_text())
    assert manifest["id"] == C.LEGACY_ID and manifest["version"] == e["version"]
    # a second download (a new model version) keeps the runtime
    fetched.clear()
    C.download(C.LEGACY_ID)
    assert [n for n, _u, _i in fetched] == [e["file"]]


def test_second_model_shares_the_runtime(fake_fetch):
    _blobs, fetched = fake_fetch
    C.download(C.DEFAULT_ID)
    fetched.clear()
    C.download(C.LEGACY_ID)
    assert [n for n, _u, _i in fetched] == [TUNE["file"]], "runtime fetched once"
    a, b = C.installed(C.DEFAULT_ID), C.installed(C.LEGACY_ID)
    assert a[1] == b[1] and a[0] != b[0]
    assert a[0].parent == model_store.ROOT / C.DEFAULT_ID / STOCK["version"]


def _install_1013(build=TUNE["runtime"]["build"]):
    """What Desktop 1.013 left on disk after downloading S1-ASR-Cleanup."""
    folder = model_store.ROOT / C.LEGACY_ID / TUNE["version"]
    folder.mkdir(parents=True)
    (folder / TUNE["file"]).write_bytes(b"TUNE")
    (folder / "manifest.json").write_text("{}")
    rt = model_store.ROOT / C.LEGACY_ID / "runtime" / build
    rt.mkdir(parents=True)
    (rt / "llama-server").write_bytes(b"#!/bin/sh\n")
    (rt / ".complete").write_text(build + "\n")
    return rt


def test_1013_runtime_is_adopted_not_downloaded_again(fake_fetch):
    _blobs, fetched = fake_fetch
    _install_1013()
    gguf, server = C.installed(C.LEGACY_ID)            # moved on first look
    assert server == C.runtime_root() / TUNE["runtime"]["build"] / "llama-server" and server.is_file()
    assert not (model_store.ROOT / C.LEGACY_ID / "runtime").exists()
    C.download(C.DEFAULT_ID)
    assert [n for n, _u, _i in fetched] == [STOCK["file"]], "no runtime download"


def test_1013_runtime_of_another_build_is_cleared(fake_fetch):
    _blobs, fetched = fake_fetch
    _install_1013("b1")
    assert C.installed(C.LEGACY_ID) is None             # the model is there, its runtime build isn't
    C.download(C.LEGACY_ID)
    assert fetched[0][1] == TUNE["runtime"]["linux"]["url"]
    assert not (model_store.ROOT / C.LEGACY_ID / "runtime").exists()
    assert C.installed(C.LEGACY_ID) is not None


def test_windows_zip_is_flattened(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "SERVER", "llama-server.exe")
    monkeypatch.setattr(C.sys, "platform", "win32")
    a = tmp_path / "llama-b1-bin-win-cpu-x64.zip"
    a.write_bytes(_zip([("llama-server.exe", b"MZ"), ("ggml.dll", b"dll"), ("llama-cli.exe", b"no")]))
    dest = tmp_path / "rt"
    dest.mkdir()
    C._extract(a, dest)
    assert sorted(p.name for p in dest.iterdir()) == ["ggml.dll", "llama-server.exe"]


def test_archive_without_a_server_fails(tmp_path):
    a = tmp_path / "x.tar.gz"
    a.write_bytes(_tar([("x/llama-cli", b"")]))
    (tmp_path / "rt").mkdir()
    with pytest.raises(RuntimeError, match="no llama-server"):
        C._extract(a, tmp_path / "rt")


def test_size_and_sha_from_hugging_face_when_not_pinned(monkeypatch):
    e = {**STOCK, "size": None, "sha256": None}
    tree = [{"path": e["file"], "size": 123, "lfs": {"oid": "ab" * 32}}, {"path": "README.md", "size": 5}]
    monkeypatch.setattr(model_store, "_get", lambda url, timeout=20: json.dumps(tree).encode())
    assert C.model_files(e) == {e["file"]: {"size": 123, "sha256": "ab" * 32}}


def test_remove_keeps_the_runtime_until_the_last_model_goes(fake_fetch, monkeypatch):
    stopped = []
    monkeypatch.setattr(C, "stop", lambda *a: stopped.append(1))
    C.download(C.DEFAULT_ID)
    C.download(C.LEGACY_ID)
    C.remove(C.LEGACY_ID)
    assert stopped and not C.root(C.LEGACY_ID).exists()
    assert C.installed(C.DEFAULT_ID) is not None, "the other model and the runtime stay"
    C.remove(C.DEFAULT_ID)
    assert not C.root(C.DEFAULT_ID).exists() and not C.runtime_root().exists()


# -- which model Clean up uses ---------------------------------------------------------------

def test_chosen_without_anything_installed_is_the_default(fake_fetch):
    assert C.chosen()["id"] == C.DEFAULT_ID
    assert C.ready() is None


def test_1013_user_keeps_the_fine_tune(fake_fetch):
    """A 1.013 user who downloaded S1-ASR-Cleanup and never picked: it stays in use, nothing new
    to download."""
    _install_1013()
    assert C.chosen()["id"] == C.LEGACY_ID and C.ready()["id"] == C.LEGACY_ID


def test_installed_default_wins_without_a_pick(fake_fetch):
    C.download(C.LEGACY_ID)
    C.download(C.DEFAULT_ID)
    assert C.chosen()["id"] == C.DEFAULT_ID


def test_explicit_pick_wins(fake_fetch, cat):
    C.download(C.DEFAULT_ID)
    assert C.chosen(C.LEGACY_ID)["id"] == C.LEGACY_ID
    assert C.ready(C.LEGACY_ID) is None, "picked but not downloaded: Clean up can't run"
    C.download(C.LEGACY_ID)
    assert C.ready(C.LEGACY_ID)["id"] == C.LEGACY_ID
    assert C.chosen("gone-from-catalogue")["id"] == C.DEFAULT_ID
    cat(TUNE, {**STOCK, "version": "TODO"})          # a pick no longer offered falls through
    assert C.chosen(C.DEFAULT_ID)["id"] == C.LEGACY_ID


def test_run_uses_the_chosen_model_and_says_which(fake_fetch, monkeypatch):
    C.download(C.DEFAULT_ID)
    C.download(C.LEGACY_ID)
    got = []
    monkeypatch.setattr(C, "server", lambda aid: got.append(aid) or FakeClient())
    r = C.run("so um hi")
    assert got == [C.DEFAULT_ID] and (r.model, r.version, r.name) == (C.DEFAULT_ID, STOCK["version"],
                                                                      "S1-mini by Superwhisper")
    r = C.run("so um hi", aid=C.LEGACY_ID)
    assert got[-1] == C.LEGACY_ID and r.version == TUNE["version"] and "S1-mini by Superwhisper" in r.name


def test_server_restarts_when_the_model_changes(fake_fetch, monkeypatch):
    C.download(C.DEFAULT_ID)
    C.download(C.LEGACY_ID)
    stopped = []
    monkeypatch.setattr(C.Server, "stop", lambda self: stopped.append(self.gguf.name))
    monkeypatch.setattr(C, "_servers", {})
    a = C.server(C.DEFAULT_ID)
    assert C.server(C.DEFAULT_ID) is a and not stopped, "same model: same process"
    b = C.server(C.LEGACY_ID)
    assert b is not a and b.gguf.name == TUNE["file"] and not stopped, "one process per model (2026-10-31)"
    assert b.binary == a.binary, "one shared runtime"
    assert C.server(C.DEFAULT_ID) is a
    C.stop(C.DEFAULT_ID)
    assert stopped == [STOCK["file"]], "stop(aid) stops only that model's server"


# -- Server, with the HTTP side faked --------------------------------------------------------

def test_server_request_is_greedy_and_capped(tmp_path, monkeypatch):
    s = C.Server(tmp_path / "m.gguf", tmp_path / "llama-server", threads=2)
    monkeypatch.setattr(s, "start", lambda: None)
    sent = []

    def post(path, body, timeout):
        sent.append((path, body, timeout))
        return {"tokens": [1, 2, 3]} if path == "/tokenize" else {"content": "Hi.", "stop_type": "eos"}
    monkeypatch.setattr(s, "_post", post)
    assert s.count("hi") == 3
    assert s.complete("PROMPT", 50, 12.0) == ("Hi.", "eos")
    path, body, timeout = sent[1]
    assert path == "/completion" and timeout == 12.0
    assert body["prompt"] == "PROMPT" and body["n_predict"] == 50
    assert body["temperature"] == 0 and body["top_k"] == 1 and body["stop"] == [C.END_OF_TURN]


def test_server_timeout_stops_the_process(tmp_path, monkeypatch):
    s = C.Server(tmp_path / "m.gguf", tmp_path / "llama-server")
    monkeypatch.setattr(s, "start", lambda: None)
    stopped = []
    monkeypatch.setattr(s, "stop", lambda: stopped.append(1))

    def post(*_a):
        raise TimeoutError()
    monkeypatch.setattr(s, "_post", post)
    with pytest.raises(TimeoutError):
        s.complete("P", 10, 0.1)
    assert stopped


def test_server_command_line(tmp_path, monkeypatch):
    """The child process: loopback only, one slot, no web UI; a process that exits is an error."""
    got = {}

    class Proc:
        def __init__(self, cmd, **kw):
            got["cmd"], got["kw"] = cmd, kw

        def poll(self):
            return 1                       # exited at once

    monkeypatch.setattr(C.subprocess, "Popen", Proc)
    s = C.Server(tmp_path / "m.gguf", tmp_path / "llama-server", threads=3)
    with pytest.raises(RuntimeError, match="exited"):
        s.start()
    cmd = got["cmd"]
    assert cmd[0] == str(tmp_path / "llama-server") and cmd[cmd.index("-m") + 1] == str(tmp_path / "m.gguf")
    assert cmd[cmd.index("--host") + 1] == "127.0.0.1" and "--no-webui" in cmd
    assert cmd[cmd.index("-np") + 1] == "1" and cmd[cmd.index("-t") + 1] == "3"
    assert cmd[cmd.index("-c") + 1] == str(C.CTX)
    assert s.proc is None


def test_importing_the_app_needs_no_runtime():
    """Nothing llama.cpp-related is imported or started until the add-on is used."""
    assert all(s.proc is None for s in C._servers.values())


# -- the Transcription tab ---------------------------------------------------------------------

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget  # noqa: E402

from hebrish import config, paragraphs  # noqa: E402
from hebrish.ui import transcribe  # noqa: E402
from hebrish.ui.window import card, muted  # noqa: E402

app = QApplication.instance() or QApplication([])


class FakeEngine:
    loaded_dir = "x"

    def __init__(self, pieces):
        self.pieces = pieces
        self.last_progress = (0, 1)

    def transcribe_chunks(self, samples, cancel, vad=True):
        for i, p in enumerate(self.pieces, 1):
            self.last_progress = (i * 40 * 16000, len(self.pieces) * 40 * 16000)
            yield p


class FakeWin:
    def __init__(self):
        self.said = []
        self.addon_rows = {}

    def status(self, text):
        self.said.append(text)


class FakeCtl:
    state = "idle"

    def __init__(self, cfg, pieces=()):
        self.cfg, self.win, self.engine = cfg, FakeWin(), FakeEngine(list(pieces))
        self.remembered = []

    def remember(self, text, **kw):
        self.remembered.append((text, kw))
        return 7

    def __getattr__(self, name):                 # stop_monitor, notify, sync_tray_*: no-ops
        return lambda *a, **k: None


@pytest.fixture
def page(monkeypatch):
    from hebrish import audio
    monkeypatch.setattr(audio, "input_devices", lambda: [])
    monkeypatch.setattr(transcribe.longform, "free_seconds", lambda: 10 ** 6)
    monkeypatch.setattr(transcribe.dictionary, "load", lambda: [])
    made = []

    def make(installed=True, on=False, pieces=("so hi there", "and then we left"), model=STOCK):
        monkeypatch.setattr(C, "ready", lambda pick=None: model if installed else None)
        if config.CONFIG_PATH.exists():
            config.CONFIG_PATH.unlink()
        cfg = config.Config()
        cfg.set("tm_cleanup", on)
        cfg.set("tm_paragraphs", paragraphs.TIME)
        host = QWidget()
        p = transcribe.TranscribePage(FakeCtl(cfg, pieces), card, muted)
        QVBoxLayout(host).addWidget(p)
        host.show()
        app.processEvents()
        made.append(host)
        return p

    yield make
    for h in made:
        h.close()
        h.deleteLater()
    app.processEvents()


def _run(p):
    import numpy as np
    p.transcribe(np.zeros(16000 * 80, np.float32))
    end = time.monotonic() + 10
    while p.cancel is not None and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert p.cancel is None, "transcription didn't finish"


def test_clean_up_is_off_by_default():
    assert config.DEFAULTS["tm_cleanup"] is False


def test_checkbox_hidden_until_downloaded(page):
    p = page(installed=False, on=True)
    assert p.tidy.isHidden() and p.para.isEnabled()


def test_checkbox_greys_out_paragraphs(page):
    p = page(installed=True, on=False)
    assert not p.tidy.isHidden() and not p.tidy.isChecked() and p.para.isEnabled()
    p.tidy.setChecked(True)
    assert p.cfg["tm_cleanup"] is True and not p.para.isEnabled()
    p.tidy.setChecked(False)
    assert p.para.isEnabled()


def test_off_means_no_clean_up(page, monkeypatch):
    called = []
    monkeypatch.setattr(C, "run", lambda *a, **k: called.append(a))
    p = page(installed=True, on=False)
    _run(p)
    assert not called
    assert p.text.toPlainText() == "so hi there\n\nand then we left"     # Time-based, as before


@pytest.mark.parametrize("model", [STOCK, TUNE])
def test_cleaned_transcript_replaces_the_raw_one(page, monkeypatch, model):
    sent = []

    def run(text, keep=(), aid=None):
        sent.append((text, aid))
        return C.Result("So, hi there.\n\nAnd then we left.", 1, 0, "", aid, model["version"], C.label(model))
    monkeypatch.setattr(C, "run", run)
    p = page(installed=True, on=True, model=model)
    _run(p)
    assert sent == [("so hi there and then we left", model["id"])], "one block, the chosen model"
    assert p.text.toPlainText() == "So, hi there.\n\nAnd then we left."
    text, kw = p.ctl.remembered[0]
    assert text == "So, hi there.\n\nAnd then we left."
    assert kw["extra"]["cleanup"] == f"{model['id']} {model['version']}"
    assert p._last is None, "a cleaned transcript is not re-flowed"
    assert any(f"Cleaned up with {model['short_name']}." in s for s in p.ctl.win.said)


def test_tooltip_names_the_chosen_model(page):
    p = page(installed=True, model=STOCK)
    assert "with S1-mini by Superwhisper:" in p.tidy.toolTip()
    p = page(installed=True, model=TUNE)
    assert f"with {TUNE['short_name']} (experimental):" in p.tidy.toolTip()


def test_failed_clean_up_keeps_the_transcript_and_its_paragraphs(page, monkeypatch):
    monkeypatch.setattr(C, "run", lambda text, keep=(), aid=None: C.Result(text, 1, 1, "timed out"))
    p = page(installed=True, on=True)
    _run(p)
    # Time-based layout, as with clean-up off: the second piece is 40 s on, so a new paragraph
    assert p.text.toPlainText() == "so hi there\n\nand then we left"
    assert p.ctl.remembered[0][1]["extra"] is None
    assert any("Clean-up failed (timed out)" in s for s in p.ctl.win.said)


# -- Models → Utilities: a row per clean-up model ------------------------------------------------

from hebrish.ui.window import MainWindow  # noqa: E402


class Utilities(QWidget):
    """Just enough of MainWindow for the Utilities page."""
    UTILITIES = MainWindow.UTILITIES
    CLEANUP_HEADING = MainWindow.CLEANUP_HEADING
    _cleanup_item = staticmethod(MainWindow._cleanup_item)
    _title_item = staticmethod(MainWindow._title_item)
    for _n in ("_utilities_page", "_utility_row", "_check", "_update_addons", "_use_cleanup", "_delete_addon"):
        locals()[_n] = getattr(MainWindow, _n)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.ctl = type("Ctl", (), {"addon_busy": {}, "addon_done": {}, "apply_vad": lambda s: None,
                                    "download_addon": lambda s, a: None})()
        self.synced = 0
        self.transcribe = type("T", (), {"sync_cleanup": lambda _s: setattr(self, "synced", self.synced + 1)})()
        self.page = self._utilities_page()

    def update_model(self):
        self._update_addons()


def test_utilities_rows_and_choice(fake_fetch, monkeypatch):
    if config.CONFIG_PATH.exists():
        config.CONFIG_PATH.unlink()
    cfg = config.Config()
    _install_1013()
    w = Utilities(cfg)
    assert w.cleanup_ids == [C.DEFAULT_ID, C.LEGACY_ID], "a row per offered model, the default first"
    assert w.title_ids == ["title-gemma-270m"] and "title-gemma-270m" in w.addon_rows, "B-75: the title model's row"
    w.update_model()
    stock, tune = w.addon_rows[C.DEFAULT_ID], w.addon_rows[C.LEGACY_ID]
    assert tune["chip"].isVisibleTo(w.page) and not tune["pick"].isVisibleTo(w.page), "the 1.013 install is in use"
    assert stock["dl"].isVisibleTo(w.page) and f"{STOCK['download_mb']} MB" in stock["status"].text()
    assert w.cleanup_check.isVisibleTo(w.page)
    C.download(C.DEFAULT_ID)
    w.update_model()
    assert stock["chip"].isVisibleTo(w.page) and tune["pick"].isVisibleTo(w.page), "installed default wins"
    stops = []
    monkeypatch.setattr(C, "stop", lambda *a: stops.append(1))
    tune["pick"].click()
    assert cfg["tm_cleanup_model"] == C.LEGACY_ID and stops and w.synced
    assert tune["chip"].isVisibleTo(w.page) and stock["pick"].isVisibleTo(w.page)
    from hebrish.ui import window
    monkeypatch.setattr(window.QMessageBox, "question", lambda *a, **k: window.QMessageBox.Yes)
    w._delete_addon(C.LEGACY_ID, "x")
    assert cfg["tm_cleanup_model"] is None and C.installed(C.LEGACY_ID) is None
    assert stock["chip"].isVisibleTo(w.page)


def test_utilities_names_follow_the_licence(cat):
    texts = {e["id"]: MainWindow._cleanup_item(e) for e in C.entries()}
    assert texts[C.DEFAULT_ID][1] == "S1-mini by Superwhisper"
    assert texts[C.LEGACY_ID][1] == TUNE["short_name"] and "Experimental" in texts[C.LEGACY_ID][2]
    assert "Experimental" not in texts[C.DEFAULT_ID][2]


# -- 2026-10-31: text in one go, Next recording, Save with a title, Save cleaned copy -----------

def _wait(p, attr="_saving"):
    end = time.monotonic() + 10
    while getattr(p, attr) and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()


def test_text_arrives_in_one_go_and_next_recording(page, monkeypatch):
    p = page(installed=False)
    ONE = "so hi there\n\nand then we left"          # Time-based: 40 s pieces
    shown = []
    p.text.textChanged.connect(lambda: shown.append(p.text.toPlainText()))
    _run(p)
    assert shown == [ONE], "one change, the whole transcript, not piece by piece"
    assert p.pbar.isHidden(), "a job under SHOW_PROGRESS_S never shows the bar"
    _run(p)
    assert p.text.toPlainText() == ONE + "\n\n" + ONE
    assert len(p._doc["raw"]) == 2
    p.next.setCurrentIndex(p.next.findData("new"))
    assert p.cfg["tm_next"] == "new"
    _run(p)
    assert p.text.toPlainText() == ONE and len(p._doc["raw"]) == 1


def test_save_with_title_and_cleaned_copy(page, monkeypatch, tmp_path):
    import json
    p = page(installed=True)
    p.cfg.set("transcripts_dir", str(tmp_path))
    monkeypatch.setattr(transcribe.titles, "ready", lambda: {"id": "title-gemma-270m"})
    asked = []
    monkeypatch.setattr(transcribe.titles, "title", lambda text, n: asked.append(n) or "Leaving Early")
    _run(p)
    p.text.appendPlainText("Edited.")
    p._save()
    _wait(p)
    files = sorted(f.name for f in tmp_path.rglob("*") if f.is_file())
    assert asked == [60] and any(f.startswith("leaving_early_") and f.endswith(".raw.md") for f in files)
    md = next(f for f in tmp_path.rglob("leaving_early_*.md") if ".raw" not in f.name)
    t = md.read_text()
    assert "# Leaving Early\n" in t and "## " in t and 'generator: "Hebrish ' in t and "Edited." in t
    p._save()                                    # unchanged: no second file
    _wait(p)
    assert len(list(tmp_path.rglob("*.md"))) == 2 and "Already saved" in p.ctl.win.said[-1]
    monkeypatch.setattr(C, "entries", lambda kind="text_cleanup": [STOCK])
    monkeypatch.setattr(C, "installed", lambda aid: ("g", "b"))
    p._fill_copy_models()
    assert not p.btn_clean_copy.isHidden() and p.copy_model.currentData() == STOCK["id"]
    monkeypatch.setattr(C, "run", lambda text, keep=(), aid=None: C.Result("So hi there. And then we left.", 1, 0,
                                                                          model=aid, version="v1", name="S1-mini by Superwhisper"))
    p._clean_copy()
    _wait(p)
    cleaned = md.with_name(md.stem + ".cleaned.md")
    assert cleaned.is_file() and "So hi there. And then we left." in cleaned.read_text()
    assert "Edited." in md.read_text(), "the original is kept as it was"
    doc = json.loads(md.with_suffix(".json").read_text())
    assert [v["kind"] for v in doc["versions"]] == ["transcript", "raw", "cleaned"]
    assert doc["title"] == "Leaving Early" and doc["versions"][2]["cleanup_model"] == "S1-mini by Superwhisper v1"
