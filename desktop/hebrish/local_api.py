"""Local transcription API (R-2026-10-31-2, B-73): the loaded model, served over HTTP on this
computer only, so scripts and coding agents (the `transcribe-with-hebrish` skill) can transcribe
audio files without a cloud service.

Opt-in (`local_api`, off by default) and unauthenticated by design (Daniel, 2026-10-31): it binds
127.0.0.1 only, so nothing on the network reaches it. Two cheap guards keep web pages out, since a
page in the browser can POST to localhost: a request with an `Origin` header (browsers send one on
cross-site POSTs) is refused, and the Host header must be localhost / 127.0.0.1 (DNS rebinding).

Endpoints (OpenAI-compatible where one exists, so existing clients work unchanged):
  GET  /health                     {"status": "ok", "app": ..., "model": {...} | null}
  GET  /v1/models                  the loaded model, OpenAI list shape
  POST /v1/audio/transcriptions    multipart/form-data with `file` (OpenAI shape), or the raw
                                   audio as the body (any Content-Type but multipart). Optional
                                   `response_format`: json (default) | text | verbose_json; as a
                                   form field or a query parameter. `model` is accepted and ignored:
                                   the app's loaded model answers.

The text is what Transcription Mode gives for the same file before paragraphs: voice detection per
`tm_vad`, then the disfluency chop and the personal dictionary per piece, pieces joined by spaces.
No clean-up model, no paragraphs, nothing kept in History. Qt-free: the controller passes in
`transcribe(samples) -> str` and `info() -> dict | None`.
"""

import json
import logging
import os
import tempfile
import threading
import time
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import __version__, audio

log = logging.getLogger(__name__)

HOST = "127.0.0.1"
DEFAULT_PORT = 8723
MAX_BODY = 1024 * 1024 * 1024          # 1 GB: a long recording as WAV; ffmpeg reads the rest
FORMATS = ("json", "text", "verbose_json")
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _multipart(body: bytes, content_type: str) -> dict[str, tuple[bytes, str | None]]:
    """name -> (bytes, filename or None)."""
    msg = BytesParser(policy=HTTP).parsebytes(
        b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + body)
    if not msg.is_multipart():
        raise ApiError(400, "malformed multipart body")
    out = {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if name:
            out[name] = (part.get_payload(decode=True) or b"", part.get_filename())
    return out


class LocalApi:
    def __init__(self, transcribe, info, port: int = DEFAULT_PORT):
        self.transcribe, self.info, self.port = transcribe, info, port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.error: str | None = None          # why the last start failed (port in use, ...)

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}"

    def start(self) -> bool:
        if self._server:
            return True
        api = self

        class Handler(_Handler):
            owner = api
        try:
            self._server = ThreadingHTTPServer((HOST, self.port), Handler)
        except OSError as e:
            self.error = f"Couldn't listen on {HOST}:{self.port}: {e.strerror or e}"
            log.warning(self.error)
            return False
        self._server.daemon_threads = True
        self.error = None
        self._thread = threading.Thread(target=self._server.serve_forever, name="local-api", daemon=True)
        self._thread.start()
        log.info("local API on %s", self.url)
        return True

    def stop(self):
        srv, self._server = self._server, None
        if srv:
            srv.shutdown()
            srv.server_close()
            log.info("local API stopped")


class _Handler(BaseHTTPRequestHandler):
    owner: LocalApi
    server_version = f"Hebrish/{__version__}"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        log.debug("local API: " + fmt, *args)

    def _send(self, status: int, body, ctype="application/json"):
        data = (json.dumps(body, ensure_ascii=False) + "\n").encode() if ctype == "application/json" \
            else str(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: int, message: str):
        self._send(status, {"error": {"message": message, "type": "invalid_request_error"
                                      if status < 500 else "server_error"}})

    def _guard(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        host = host.split("]")[0] + "]" if host.startswith("[") else host.split(":")[0]
        if host not in _LOCAL_HOSTS:
            self._error(403, "only localhost requests are served")
            return False
        if self.headers.get("Origin"):
            self._error(403, "browser requests are not served")
            return False
        return True

    def do_GET(self):
        if not self._guard():
            return
        path = urlsplit(self.path).path.rstrip("/")
        info = self.owner.info()
        if path in ("", "/health"):
            self._send(200, {"status": "ok" if info else "no_model", "app": __version__, "model": info})
        elif path == "/v1/models":
            data = [{"id": info["id"], "object": "model", "owned_by": "hebrish",
                     "version": info.get("version")}] if info else []
            self._send(200, {"object": "list", "data": data})
        else:
            self._error(404, f"no route {path}")

    def do_POST(self):
        if not self._guard():
            return
        url = urlsplit(self.path)
        if url.path.rstrip("/") != "/v1/audio/transcriptions":
            self._error(404, f"no route {url.path}")
            return
        try:
            self._transcribe(parse_qs(url.query))
        except ApiError as e:
            self._error(e.status, str(e))
        except Exception as e:      # the model or ffmpeg failed: say so, keep serving
            log.exception("local API transcription failed")
            self._error(500, str(e) or e.__class__.__name__)

    def _transcribe(self, query: dict):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "bad Content-Length") from None
        if n <= 0:
            raise ApiError(411 if "Content-Length" not in self.headers else 400, "send the audio as the body")
        if n > MAX_BODY:
            raise ApiError(413, f"audio over {MAX_BODY // 2**20} MB")
        body = self.rfile.read(n)
        ctype = self.headers.get("Content-Type", "")
        fields = {k: v[-1] for k, v in query.items()}
        name = None
        if ctype.lower().startswith("multipart/form-data"):
            parts = _multipart(body, ctype)
            if "file" not in parts:
                raise ApiError(400, "multipart body has no `file` field")
            body, name = parts.pop("file")
            fields.update({k: v.decode(errors="replace") for k, (v, _) in parts.items()})
        fmt = fields.get("response_format", "json")
        if fmt not in FORMATS:
            raise ApiError(400, f"response_format must be one of {', '.join(FORMATS)}")
        if self.owner.info() is None:
            raise ApiError(503, "no model is loaded in Hebrish yet")
        suffix = os.path.splitext(name or "")[1] or ".audio"
        with tempfile.TemporaryDirectory(prefix="hebrish-api-") as tmp:
            path = os.path.join(tmp, "in" + suffix)
            with open(path, "wb") as f:
                f.write(body)
            try:
                samples = audio.load_file(path)
            except Exception as e:
                raise ApiError(400, f"couldn't read the audio: {e}") from None
        t0 = time.monotonic()
        text = self.owner.transcribe(samples)
        took = time.monotonic() - t0
        seconds = len(samples) / audio.SAMPLE_RATE
        if fmt == "text":
            self._send(200, text + "\n", "text/plain")
        elif fmt == "json":
            self._send(200, {"text": text})
        else:
            self._send(200, {"task": "transcribe", "text": text, "duration": round(seconds, 3),
                             "processing_s": round(took, 3), "model": self.owner.info()})
