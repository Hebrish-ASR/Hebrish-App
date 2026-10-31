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
