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

    def edit_history(self, rid, text):
        from hebrish import history
        if history.get(self.history_path, rid) is None:
            raise LookupError(f"no transcript {rid}")
        self.edits = getattr(self, "edits", []) + [(rid, text)]
        return {"id": rid, "text": text, "changed": True}

    def delete_history(self, rid):
        if rid == 99:
            raise LookupError("no transcript 99")
        return {"id": rid, "deleted": True}

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


def test_language_field_reaches_the_app(monkeypatch):
    """Hebrew switching (2026-11-16): OpenAI's `language` picks the Hebrew model; anything but he/en is 400,
    and the app's refusal (Hebrew model not downloaded) comes back as its status."""
    monkeypatch.setattr(local_api.audio, "load_file", _read_wav)
    seen = []

    def transcribe(samples, language=None):
        seen.append(language)
        if language == "he" and len(seen) > 2:
            raise local_api.ApiError(409, "the Hebrew model isn't downloaded")
        return "שלום" if language == "he" else "hello"
    a = local_api.LocalApi(transcribe, lambda: {"id": "x", "version": "1"}, _free_port())
    assert a.start()
    try:
        body, h = _multipart({"language": "he"}, _wav())
        st, _, d = _req(a, "POST", "/v1/audio/transcriptions", body, h)
        assert st == 200 and json.loads(d) == {"text": "שלום"}
        st, _, d = _req(a, "POST", "/v1/audio/transcriptions?language=iw&response_format=verbose_json", _wav(),
                        {"Content-Type": "audio/wav"})
        assert st == 200 and json.loads(d)["language"] == "he"
        st, _, _ = _req(a, "POST", "/v1/audio/transcriptions?language=fr", _wav(), {"Content-Type": "audio/wav"})
        assert st == 400
        st, _, d = _req(a, "POST", "/v1/audio/transcriptions?language=he", _wav(), {"Content-Type": "audio/wav"})
        assert st == 409
        assert seen == ["he", "he", "he"]
    finally:
        a.stop()


def test_history_writes_route_to_the_app(ctl):
    """B-108: PATCH and DELETE /v1/history/{id} go to the app (its own History connection)."""
    st, j = _json(ctl, "PATCH", "/v1/history/2", {"text": "I listen to My Weird Prompts"})
    assert st == 200 and j["changed"] is True and ctl.fake.edits == [(2, "I listen to My Weird Prompts")]
    assert _json(ctl, "PATCH", "/v1/history/2", {"text": "  "})[0] == 400
    assert _json(ctl, "PATCH", "/v1/history/99", {"text": "x"})[0] == 404
    assert _json(ctl, "PATCH", "/v1/history/x", {"text": "x"})[0] == 400
    assert _json(ctl, "DELETE", "/v1/history/1") == (200, {"id": 1, "deleted": True})
    assert _json(ctl, "DELETE", "/v1/history/99")[0] == 404
    assert _json(ctl, "DELETE", "/v1/history")[0] == 404           # never the whole history
    assert _json(ctl, "PATCH", "/v1/history", {"text": "x"})[0] == 404
    ctl.fake.on = False
    assert _json(ctl, "PATCH", "/v1/history/2", {"text": "x"})[0] == 403
    assert _json(ctl, "DELETE", "/v1/history/2")[0] == 403
    assert _req(ctl, "DELETE", "/v1/history/2", headers={"Origin": "https://example.com"})[0] == 403


# -- GET /v1/app/events (B-108) ----------------------------------------------------------------

def _stream(api):
    c = http.client.HTTPConnection("127.0.0.1", api.port, timeout=5)
    c.request("GET", "/v1/app/events")
    r = c.getresponse()
    return c, r


def _next_event(r) -> dict:
    ev = {}
    while True:
        line = r.readline().decode()
        if line in ("\n", ""):
            if ev or line == "":
                return ev
            continue
        if line.startswith(":"):
            ev.setdefault("comments", 0)
            ev["comments"] += 1
            continue
        k, _, v = line.rstrip("\n").partition(": ")
        ev[k] = json.loads(v) if k == "data" else v


def _wait(pred, timeout=5.0):
    import time
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def test_events_stream_published_events(ctl):
    c, r = _stream(ctl)
    assert r.status == 200 and r.getheader("Content-Type").startswith("text/event-stream")
    assert _next_event(r)["event"] == "ready"
    assert _wait(lambda: ctl.streams == 1)
    ctl.publish("take", {"text": "שלום world", "history_id": 4})
    ctl.publish("state", {"state": "idle", "paused": False})
    a, b = _next_event(r), _next_event(r)
    assert a["event"] == "take" and a["data"] == {"text": "שלום world", "history_id": 4}
    assert b["event"] == "state" and int(b["id"]) == int(a["id"]) + 1
    c.close()


def test_events_end_on_stop_and_leave_no_thread(tmp_path):
    import threading
    before = threading.active_count()
    fake = FakeControl(tmp_path / "history.db")
    a = local_api.LocalApi(lambda s: "", lambda: None, _free_port(), fake)
    assert a.start()
    c, r = _stream(a)
    assert _next_event(r)["event"] == "ready"
    a.stop()
    assert _next_event(r) == {"event": "closed", "data": {"reason": "the app's local API stopped"}}
    assert r.read() == b""                                      # the server closed the connection
    c.close()
    assert _wait(lambda: threading.active_count() <= before) and a.streams == 0


def test_events_end_when_control_goes_off_or_the_client_leaves(ctl, monkeypatch):
    monkeypatch.setattr(local_api, "HEARTBEAT_S", 0.1)
    c, r = _stream(ctl)
    _next_event(r)
    assert _next_event(r).get("comments")                      # a heartbeat
    ctl.fake.on = False
    ev = _next_event(r)
    while ev.get("comments") and "event" not in ev:
        ev = _next_event(r)
    assert ev["event"] == "closed" and ev["data"]["reason"] == "control is off"
    c.close()
    assert _wait(lambda: ctl.streams == 0)
    ctl.fake.on = True
    c, r = _stream(ctl)
    _next_event(r)
    assert _wait(lambda: ctl.streams == 1)
    r.close()
    c.close()                                                   # found by the next heartbeat write
    assert _wait(lambda: ctl.streams == 0)


def test_events_refused_when_off_and_capped(ctl, monkeypatch):
    ctl.fake.on = False
    assert _json(ctl, "GET", "/v1/app/events")[0] == 403
    assert _req(ctl, "GET", "/v1/app/events", headers={"Origin": "https://example.com"})[0] == 403
    ctl.fake.on = True
    monkeypatch.setattr(local_api, "MAX_STREAMS", 1)
    c, r = _stream(ctl)
    _next_event(r)
    assert _json(ctl, "GET", "/v1/app/events")[0] == 503
    c.close()


def test_slow_stream_is_closed_not_blocking(monkeypatch):
    monkeypatch.setattr(local_api, "EVENT_BACKLOG", 2)
    a = local_api.LocalApi(lambda s: "", lambda: None, _free_port())
    st = a._subscribe()
    for i in range(5):
        a.publish("state", {"n": i})                            # never blocks
    assert a.streams == 0 and st.why.startswith("too slow")


# -- allowed web origins (B-109) -------------------------------------------------------------

WEB = "https://label.example.com"


class WebControl(FakeControl):
    """FakeControl plus the dictation route and take_state, as api_control.Control has them."""
    recording = False

    def take_state(self):
        return {"state": "recording" if self.recording else "idle", "paused": False}

    def handle(self, method, path, body):
        if path == "/v1/app/dictation":
            self.recording = {"start": True, "stop": False, "toggle": not self.recording}[body["action"]]
            return 200, {"action": body["action"], **self.take_state()}
        return super().handle(method, path, body)


@pytest.fixture
def web(tmp_path):
    fake = WebControl(tmp_path / "history.db")
    origins = [WEB]
    a = local_api.LocalApi(lambda s: "", lambda: None, _free_port(), fake, lambda: origins)
    assert a.start()
    a.fake, a.origins = fake, origins
    yield a
    a.stop()


def _resp(api, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", api.port, timeout=10)
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers or {})
    r = c.getresponse()
    data = r.read()
    c.close()
    return r, (json.loads(data) if data else None)


def test_allowed_origin_gets_health_and_dictation_with_cors(web):
    r, j = _resp(web, "GET", "/health", headers={"Origin": WEB})
    assert r.status == 200 and j["state"] == "idle" and j["paused"] is False
    assert r.getheader("Access-Control-Allow-Origin") == WEB and r.getheader("Vary") == "Origin"
    r, j = _resp(web, "POST", "/v1/app/dictation", {"action": "toggle"},
                 {"Origin": WEB, "Content-Type": "application/json"})
    assert r.status == 200 and j == {"action": "toggle", "state": "recording", "paused": False}
    assert r.getheader("Access-Control-Allow-Origin") == WEB
    assert _resp(web, "GET", "/health", headers={"Origin": WEB})[1]["state"] == "recording"
    r, j = _resp(web, "POST", "/v1/app/dictation", {"action": "stop"}, {"Origin": WEB})
    assert r.status == 200 and j["state"] == "idle"


def test_allowed_origin_dictation_still_needs_control(web):
    web.fake.on = False
    r, j = _resp(web, "POST", "/v1/app/dictation", {"action": "stop"}, {"Origin": WEB})
    assert r.status == 403 and "Settings" in j["error"]["message"]
    assert r.getheader("Access-Control-Allow-Origin") == WEB


def test_unknown_origin_is_refused_without_cors(web):
    for method, path, body in (("GET", "/health", None), ("POST", "/v1/app/dictation", {"action": "stop"}),
                               ("OPTIONS", "/v1/app/dictation", None)):
        r, _ = _resp(web, method, path, body, {"Origin": "https://evil.example"})
        assert r.status == 403 and r.getheader("Access-Control-Allow-Origin") is None, (method, path)
    # a prefix or a different scheme of an allowed origin is not it
    assert _resp(web, "GET", "/health", headers={"Origin": "http://label.example.com"})[0].status == 403
    assert _resp(web, "GET", "/health", headers={"Origin": WEB + ".evil.example"})[0].status == 403


def test_allowed_origin_gets_nothing_else(web):
    for method, path, body in (("GET", "/v1/history", None), ("GET", "/v1/history/1", None),
                               ("GET", "/v1/dictionary", None), ("GET", "/v1", None), ("GET", "/", None),
                               ("GET", "/v1/app/status", None), ("GET", "/v1/app/events", None),
                               ("GET", "/v1/app/dictation", None), ("POST", "/health", {}),
                               ("POST", "/v1/app/settings", {"vad": True}),
                               ("DELETE", "/v1/history/1", None), ("PATCH", "/v1/history/1", {"text": "x"})):
        r, j = _resp(web, method, path, body, {"Origin": WEB})
        assert r.status == 403 and "web pages" in j["error"]["message"], (method, path)
    r, _ = _resp(web, "POST", "/v1/audio/transcriptions", None, {"Origin": WEB})
    assert r.status == 403
    assert web.fake.recording is False


def test_preflight_headers(web):
    for path, method in (("/v1/app/dictation", "POST"), ("/health", "GET")):
        r, body = _resp(web, "OPTIONS", path, headers={
            "Origin": WEB, "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type", "Access-Control-Request-Private-Network": "true"})
        assert r.status == 204 and body is None
        assert r.getheader("Access-Control-Allow-Origin") == WEB and r.getheader("Vary") == "Origin"
        assert r.getheader("Access-Control-Allow-Methods") == "GET, POST, OPTIONS"
        assert r.getheader("Access-Control-Allow-Headers") == "Content-Type"
        assert r.getheader("Access-Control-Allow-Private-Network") == "true"
        assert r.getheader("Access-Control-Max-Age") == "600"
    assert _resp(web, "OPTIONS", "/v1/history", headers={"Origin": WEB})[0].status == 403


def test_no_origin_is_unchanged_and_list_is_read_live(web):
    r, j = _resp(web, "GET", "/v1/history")
    assert r.status == 200 and r.getheader("Access-Control-Allow-Origin") is None
    assert _req(web, "OPTIONS", "/health")[0] == 501             # as before B-109: no OPTIONS
    web.origins.clear()
    assert _resp(web, "GET", "/health", headers={"Origin": WEB})[0].status == 403
    web.origins.append(WEB)
    assert _resp(web, "GET", "/health", headers={"Origin": WEB})[0].status == 200


def test_default_is_no_web_origin(api):
    assert _resp(api, "GET", "/health", headers={"Origin": WEB})[0].status == 403
    from hebrish.config import DEFAULTS
    assert DEFAULTS["local_api_web_origins"] == []


def test_parse_web_origins():
    pytest.importorskip("PySide6")       # Linux CI has no PySide6 (desktop-v1.042's first tag failed on it)
    from hebrish.ui.window import parse_web_origins
    assert parse_web_origins("https://Label.Example.com/, http://localhost:8080 https://x.org/path ftp://a "
                             "https://label.example.com") == ["https://label.example.com", "http://localhost:8080"]
