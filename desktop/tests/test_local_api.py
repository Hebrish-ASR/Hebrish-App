"""hebrish.local_api (B-73): the local transcription API, against a fake model."""

import http.client
import io
import json
import socket
import wave

import numpy as np
import pytest

from hebrish import audio, local_api


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wav(seconds=1.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(audio.SAMPLE_RATE)
        t = np.arange(int(seconds * audio.SAMPLE_RATE)) / audio.SAMPLE_RATE
        w.writeframes((np.sin(2 * np.pi * 220 * t) * 8000).astype("<i2").tobytes())
    return buf.getvalue()


def _read_wav(path):
    """Stands in for audio.load_file: CI has neither ffmpeg nor soundfile, and these tests are
    about the HTTP layer (desktop-v1.014's second tag failed on this, 2026-10-31)."""
    with wave.open(path, "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(local_api.audio, "load_file", _read_wav)
    got = []
    info = {"id": "sabich", "name": "Sabich v2.3", "version": "v2.3", "streaming": False}
    state = {"info": info}

    def transcribe(samples):
        got.append(len(samples))
        return "Ani holekh la-makolet"
    a = local_api.LocalApi(transcribe, lambda: state["info"], _free_port())
    assert a.start()
    a.got, a.state = got, state
    yield a
    a.stop()


def _req(api, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", api.port, timeout=10)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, r.getheader("Content-Type"), data


def _multipart(fields: dict, file: bytes, name="take.wav"):
    b = "hebrishboundary"
    out = b""
    for k, v in fields.items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    out += (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            f"Content-Type: audio/wav\r\n\r\n").encode() + file + f"\r\n--{b}--\r\n".encode()
    return out, {"Content-Type": f"multipart/form-data; boundary={b}"}


def test_health_and_models(api):
    st, _, d = _req(api, "GET", "/health")
    assert st == 200 and json.loads(d)["model"]["id"] == "sabich"
    st, _, d = _req(api, "GET", "/v1/models")
    assert json.loads(d)["data"][0]["id"] == "sabich"


def test_multipart_openai_shape(api):
    body, h = _multipart({"model": "whisper-1"}, _wav())
    st, ct, d = _req(api, "POST", "/v1/audio/transcriptions", body, h)
    assert st == 200 and ct.startswith("application/json")
    assert json.loads(d) == {"text": "Ani holekh la-makolet"}
    assert api.got == [audio.SAMPLE_RATE]


def test_raw_body_text_format(api):
    st, ct, d = _req(api, "POST", "/v1/audio/transcriptions?response_format=text", _wav(),
                     {"Content-Type": "audio/wav"})
    assert st == 200 and ct.startswith("text/plain") and d.decode().strip() == "Ani holekh la-makolet"


def test_verbose_json(api):
    body, h = _multipart({"response_format": "verbose_json"}, _wav(2))
    st, _, d = _req(api, "POST", "/v1/audio/transcriptions", body, h)
    j = json.loads(d)
    assert st == 200 and j["duration"] == 2.0 and j["model"]["version"] == "v2.3"


def test_refuses_browsers_and_foreign_hosts(api):
    st, _, _ = _req(api, "POST", "/v1/audio/transcriptions", _wav(), {"Origin": "https://example.com"})
    assert st == 403
    st, _, _ = _req(api, "GET", "/health", headers={"Host": "evil.example:8723"})
    assert st == 403
    assert api.got == []


def test_no_model_and_bad_input(api):
    st, _, _ = _req(api, "POST", "/v1/audio/transcriptions", b"not audio at all")
    assert st == 400
    api.state["info"] = None
    st, _, d = _req(api, "POST", "/v1/audio/transcriptions", _wav())
    assert st == 503 and "no model" in json.loads(d)["error"]["message"]
    st, _, d = _req(api, "GET", "/health")
    assert json.loads(d)["status"] == "no_model"


def test_port_in_use_is_reported(api):
    other = local_api.LocalApi(lambda s: "", lambda: None, api.port)
    assert not other.start() and "Couldn't listen" in other.error


# -- control endpoints (B-87) ----------------------------------------------------------------

class FakeControl:
    def __init__(self, path):
        self.history_path, self.on, self.changed = path, True, 0

    def enabled(self):
        return self.on

    def dictionary_changed(self):
        self.changed += 1

    def handle(self, method, path, body):
        if path == "/v1/app/status":
            return 200, {"state": "idle"}
        if path == "/v1/app/update":
            raise RuntimeError("this install (windows) updates from the download page")
        if path == "/v1/app/models/select":
            raise LookupError("no model 'x'")
        raise ValueError("bad action")


@pytest.fixture
def ctl(tmp_path, monkeypatch):
    from hebrish import dictionary
    from hebrish.history import History
    monkeypatch.setattr(dictionary, "PATH", tmp_path / "dictionary.json")
    h = History(tmp_path / "history.db")
    h.add("My Word Prompts is a podcast", at=100.0, model="sabich v2.3")
    h.add("I listen to my word prompts on the way to the makolet", at=200.0, source="file")
    h.add("Nothing to see here", at=300.0)
    h.update_text(3, "Nothing to read here")
    fake = FakeControl(tmp_path / "history.db")
    a = local_api.LocalApi(lambda s: "", lambda: None, _free_port(), fake)
    assert a.start()
    a.fake = fake
    yield a
    a.stop()
    h.close()


def _json(api, method, path, body=None, headers=None):
    st, _, d = _req(api, method, path, json.dumps(body) if body is not None else None, headers)
    return st, json.loads(d)


def test_routes_are_listed_and_health_says_control(ctl):
    st, j = _json(ctl, "GET", "/v1")
    assert st == 200 and j["control"] is True
    assert {"method": "GET", "path": "/v1/history"}.items() <= next(
        r for r in j["routes"] if r["path"] == "/v1/history").items()
    assert _json(ctl, "GET", "/health")[1]["control"] is True


def test_control_off_refuses_everything_but_transcription(ctl):
    ctl.fake.on = False
    for method, path, body in (("GET", "/v1/history", None), ("GET", "/v1/history/1", None),
                               ("GET", "/v1/dictionary", None), ("GET", "/v1/app/status", None),
                               ("POST", "/v1/dictionary", {"word": "X"}), ("DELETE", "/v1/dictionary?word=X", None)):
        st, j = _json(ctl, method, path, body)
        assert st == 403 and "Settings" in j["error"]["message"], path
    assert _json(ctl, "GET", "/health")[0] == 200
    assert _json(ctl, "GET", "/v1/dictionary")[0] == 403


def test_no_control_object_is_the_old_api(api):
    assert _json(api, "GET", "/v1/history")[0] == 403
    assert _json(api, "GET", "/health")[1]["control"] is False


def test_guards_cover_control(ctl):
    assert _req(ctl, "GET", "/v1/history", headers={"Origin": "https://example.com"})[0] == 403
    assert _req(ctl, "GET", "/v1/history", headers={"Host": "evil.example:8723"})[0] == 403
    assert _req(ctl, "DELETE", "/v1/dictionary?word=X", headers={"Origin": "https://example.com"})[0] == 403


def test_history_paging_search_and_filters(ctl):
    st, j = _json(ctl, "GET", "/v1/history?limit=2")
    assert st == 200 and j["total"] == 3 and [r["id"] for r in j["data"]] == [3, 2]
    assert [r["id"] for r in _json(ctl, "GET", "/v1/history?limit=2&offset=2")[1]["data"]] == [1]
    j = _json(ctl, "GET", "/v1/history?q=makolet")[1]
    assert j["total"] == 1 and "[makolet]" in j["data"][0]["snippet"]
    assert _json(ctl, "GET", "/v1/history?since=150&until=250")[1]["total"] == 1
    assert _json(ctl, "GET", "/v1/history?source=file")[1]["total"] == 1
    j = _json(ctl, "GET", "/v1/history?edited=1")[1]
    assert j["total"] == 1 and j["data"][0]["original"] == "Nothing to see here"
    assert _json(ctl, "GET", "/v1/history/1")[1]["model"] == "sabich v2.3"
    assert _json(ctl, "GET", "/v1/history/99")[0] == 404
    assert _json(ctl, "GET", "/v1/history?limit=0")[0] == 400
    assert _json(ctl, "GET", "/v1/history?limit=x")[0] == 400


def test_dictionary_add_merge_remove(ctl):
    st, j = _json(ctl, "POST", "/v1/dictionary", {"word": "My Weird Prompts", "heard": ["my word prompts"]})
    assert st == 201 and j["created"] is True
    st, j = _json(ctl, "POST", "/v1/dictionary", {"word": "My Weird Prompts", "heard": ["MY WORD PROMPTS", "my ward prompts"]})
    assert st == 200 and j["entry"]["heard"] == ["my word prompts", "my ward prompts"]   # kept, not replaced
    assert ctl.fake.changed == 2
    assert _json(ctl, "DELETE", "/v1/dictionary?word=My%20Weird%20Prompts&heard=my%20ward%20prompts")[0] == 200
    assert _json(ctl, "GET", "/v1/dictionary")[1]["data"][0]["heard"] == ["my word prompts"]
    assert _json(ctl, "DELETE", "/v1/dictionary?word=My%20Weird%20Prompts")[0] == 200
    assert _json(ctl, "DELETE", "/v1/dictionary?word=My%20Weird%20Prompts")[0] == 404
    assert _json(ctl, "POST", "/v1/dictionary", {"heard": ["x"]})[0] == 400
    assert _json(ctl, "POST", "/v1/dictionary", {"word": "X", "heard": [1]})[0] == 400
    assert _req(ctl, "POST", "/v1/dictionary", "not json")[0] == 400


def test_preview_counts_changes_and_writes_nothing(ctl):
    st, j = _json(ctl, "POST", "/v1/dictionary/preview", {"word": "My Weird Prompts", "heard": ["my word prompts"]})
    assert st == 200 and j["rows_scanned"] == 3 and j["rows_changed"] == 2 and j["replacements"] == 2
    assert j["by_source"] == {"my word prompts": 1, "My Word Prompts": 1}
    assert "My Weird Prompts" in j["samples"][0]["after"] and "my word prompts" in j["samples"][0]["before"]
    assert _json(ctl, "GET", "/v1/dictionary")[1]["data"] == []


def test_control_errors_map_to_status(ctl):
    assert _json(ctl, "GET", "/v1/app/status") == (200, {"state": "idle"})
    assert _json(ctl, "POST", "/v1/app/update", {})[0] == 409
    assert _json(ctl, "POST", "/v1/app/models/select", {"id": "x"})[0] == 404
    assert _json(ctl, "POST", "/v1/app/dictation", {"action": "x"})[0] == 400
    assert _json(ctl, "GET", "/v1/nope")[0] == 404
