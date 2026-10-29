"""Dictation clean-up (B-40): S1-ASR-Cleanup, a fine-tune of S1-mini by Superwhisper, as an
optional Utilities add-on run on finished Transcription-tab transcripts (hebrish/cleanup.py).

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
    assert C.installed() is None
    r = C.run("so um hi")
    assert r.text == "so um hi" and not r.cleaned and "isn't downloaded" in r.error


# -- catalogue -------------------------------------------------------------------------------

def test_catalogue_entry():
    e = C.entry()
    assert e["id"] == C.MODEL_ID and e["kind"] == "text_cleanup"
    # licence: named "S1-mini" by "Superwhisper", exact capitalisation
    assert "S1-mini by Superwhisper" in e["name"] and e["base_label"] == "S1-mini by Superwhisper"
    assert "S1-mini by Superwhisper" in C.DISPLAY_NAME and C.DISPLAY_NAME == e["name"]
    assert e["platforms"] == ["linux", "windows"] and e["devices"] == ["desktop"]
    assert e["file"].endswith(".gguf") and e["size"] > 0 and len(e["sha256"]) == 64
    assert e["card"] == C.CARD
    for os_ in ("linux", "windows"):
        rt = e["runtime"][os_]
        assert rt["url"].startswith("https://github.com/ggml-org/llama.cpp/releases/download/" + e["runtime"]["build"] + "/")
        assert rt["size"] > 0 and len(rt["sha256"]) == 64


def test_older_cached_catalogue_falls_back_to_the_bundled_entry(monkeypatch):
    monkeypatch.setattr(model_store, "catalogue", lambda: {"lines": []})
    assert C.entry()["id"] == C.MODEL_ID


def test_android_and_speech_models_ignore_addons():
    """The add-on is not a speech model: it never shows up among the variants."""
    assert C.MODEL_ID not in {m.id for m in model_store.variants()}


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
def fake_fetch(tmp_path, monkeypatch):
    """model_store.fetch_files writes `blobs[name]` instead of downloading."""
    monkeypatch.setattr(model_store, "ROOT", tmp_path / "models")
    blobs, fetched = {}, []

    def fetch(dest, files, url_for, on_progress=None, cancel=None):
        dest.mkdir(parents=True, exist_ok=True)
        for name, info in files.items():
            fetched.append((name, url_for(name), info))
            (dest / name).write_bytes(blobs[name])
            if on_progress:
                on_progress(len(blobs[name]), len(blobs[name]), name)
    monkeypatch.setattr(model_store, "fetch_files", fetch)
    return blobs, fetched


def test_download_installs_runtime_and_model(fake_fetch, monkeypatch):
    monkeypatch.setattr(model_store, "PLATFORM", "linux")
    monkeypatch.setattr(C, "SERVER", "llama-server")
    blobs, fetched = fake_fetch
    e = C.entry()
    build = e["runtime"]["build"]
    blobs[e["runtime"]["linux"]["url"].rsplit("/", 1)[-1]] = _tar([
        (f"llama-{build}/llama-server", b"#!/bin/sh\n"),
        (f"llama-{build}/llama-cli", b"not wanted"),
        (f"llama-{build}/libllama.so.0.8.0", b"lib"),
        (f"llama-{build}/libllama.so.0", ("link", "libllama.so.0.8.0")),
        (f"llama-{build}/LICENSE", b"mit"),
    ])
    blobs[e["file"]] = b"GGUF"
    old = model_store.ROOT / C.MODEL_ID / "v0.9"
    old.mkdir(parents=True)
    seen = []
    C.download(lambda d, t, n: seen.append((d, t, n)))
    gguf, server = C.installed()
    assert gguf.read_bytes() == b"GGUF" and server.name == "llama-server"
    rt = server.parent
    assert sorted(p.name for p in rt.iterdir()) == [".complete", "libllama.so.0", "libllama.so.0.8.0", "llama-server"]
    assert (rt / "libllama.so.0").read_bytes() == b"lib"
    if os.name != "nt":
        assert os.access(server, os.X_OK)
    assert not old.exists(), "older model versions are deleted"
    assert not (rt.parent / ".download").exists(), "the archive is deleted after extraction"
    urls = [u for _n, u, _i in fetched]
    assert urls[0] == e["runtime"]["linux"]["url"]
    assert urls[1] == f"https://huggingface.co/{e['repo']}/resolve/{e['revision']}/{e['file']}"
    assert fetched[1][2] == {"size": e["size"], "sha256": e["sha256"]}
    assert seen[-1][1] == e["runtime"]["linux"]["size"] + e["size"]      # one progress total
    manifest = json.loads((gguf.parent / "manifest.json").read_text())
    assert manifest["version"] == e["version"] and manifest["revision"] == e["revision"]
    # a second download (a new model version) keeps the runtime
    fetched.clear()
    C.download()
    assert [n for n, _u, _i in fetched] == [e["file"]]


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
    e = {**C.entry(), "size": None, "sha256": None}
    tree = [{"path": e["file"], "size": 123, "lfs": {"oid": "ab" * 32}}, {"path": "README.md", "size": 5}]
    monkeypatch.setattr(model_store, "_get", lambda url, timeout=20: json.dumps(tree).encode())
    assert C.model_files(e) == {e["file"]: {"size": 123, "sha256": "ab" * 32}}


def test_remove_stops_the_server_and_deletes(fake_fetch, monkeypatch):
    stopped = []
    monkeypatch.setattr(C, "stop", lambda: stopped.append(1))
    C.root().mkdir(parents=True)
    C.remove()
    assert stopped and not C.root().exists()


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
    assert C._server is None or C._server.proc is None


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

    def make(installed=True, on=False, pieces=("so hi there", "and then we left")):
        monkeypatch.setattr(C, "installed", lambda: ("m.gguf", "llama-server") if installed else None)
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


def test_cleaned_transcript_replaces_the_raw_one(page, monkeypatch):
    sent = []

    def run(text, keep=()):
        sent.append(text)
        return C.Result("So, hi there.\n\nAnd then we left.", 1, 0)
    monkeypatch.setattr(C, "run", run)
    p = page(installed=True, on=True)
    _run(p)
    assert sent == ["so hi there and then we left"], "one block, no Time-based paragraph breaks"
    assert p.text.toPlainText() == "So, hi there.\n\nAnd then we left."
    text, kw = p.ctl.remembered[0]
    assert text == "So, hi there.\n\nAnd then we left."
    assert kw["extra"]["cleanup"].startswith(C.MODEL_ID)
    assert p._last is None, "a cleaned transcript is not re-flowed"
    assert any("S1-mini by Superwhisper" in s for s in p.ctl.win.said)


def test_failed_clean_up_keeps_the_transcript_and_its_paragraphs(page, monkeypatch):
    monkeypatch.setattr(C, "run", lambda text, keep=(): C.Result(text, 1, 1, "timed out"))
    p = page(installed=True, on=True)
    _run(p)
    # Time-based layout, as with clean-up off: the second piece is 40 s on, so a new paragraph
    assert p.text.toPlainText() == "so hi there\n\nand then we left"
    assert p.ctl.remembered[0][1]["extra"] is None
    assert any("Clean-up failed (timed out)" in s for s in p.ctl.win.said)
