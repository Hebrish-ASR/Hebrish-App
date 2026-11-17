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
                                   the app's loaded model answers. `language` (2026-11-16): `he`
                                   uses the Hebrew model (409 when it isn't downloaded); `en` or
                                   none, the main model. The keyboard layout never decides here.

The text is what Transcription Mode gives for the same file before paragraphs: voice detection per
`vad`, then the disfluency chop and the personal dictionary per piece, pieces joined by spaces.
No clean-up model, no paragraphs, nothing kept in History. Qt-free: the controller passes in
`transcribe(samples) -> str` and `info() -> dict | None`.

Control endpoints (B-87; B-108 filled the gaps, 2026-11-17): everything in ROUTES past the
transcription ones, for coding agents and controllers: history (read, correct, delete), dictionary,
dictation actions, Transcription Mode on a file, microphones, models, settings, updates, and change
events. A second opt-in (`local_api_control`, off by default): with it off they answer 403, because
a user who turned on transcription did not agree to serve their transcripts. Same guards, no token
(Daniel's 2026-10-31 decision for this port). `GET /v1` lists the routes, so an agent needs no docs.
The controller passes in `control` (hebrish.ui.api_control.Control). History reads and the
dictionary are served from their files here; history writes go through the app's own History
connection, which is tied to the GUI thread. Control raises LookupError (404), ValueError (400),
RuntimeError (409).

GET /v1/app/events is a Server-Sent Events stream: the Controller calls `publish` (any thread, never
blocks), each open stream holds one HTTP thread until the client leaves, the server stops, control
goes off or the client falls EVENT_BACKLOG behind; at most MAX_STREAMS at once.
"""

import json
import logging
import os
import queue
import sys
import tempfile
import threading
import time
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import __version__, audio, dictionary, history


class _Server(ThreadingHTTPServer):
    # HTTPServer sets SO_REUSEADDR, which on Windows lets a second socket bind a port already in
    # use (the other app keeps getting the requests and start() wrongly reports success). Found by
    # test_port_in_use_is_reported on the windows CI job, 2026-10-31.
    allow_reuse_address = sys.platform != "win32"

log = logging.getLogger(__name__)

HOST = "127.0.0.1"
DEFAULT_PORT = 8723
MAX_BODY = 1024 * 1024 * 1024          # 1 GB: a long recording as WAV; ffmpeg reads the rest
FORMATS = ("json", "text", "verbose_json")
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
MAX_JSON = 1024 * 1024
MAX_PAGE = 1000
# GET /v1/app/events (B-108): Server-Sent Events. Each stream holds one HTTP thread, so they are
# capped; a stream ends on disconnect (found by the heartbeat write within HEARTBEAT_S), stop(),
# control turned off, or a client too slow to keep EVENT_BACKLOG events queued.
MAX_STREAMS = 8
HEARTBEAT_S = 15.0
EVENT_BACKLOG = 256
EVENTS = {
    "ready": "Sent first: app version and the dictation state",
    "state": "Dictation state changed: {state, paused}",
    "take": "A dictation take finished: {text, history_id, language, seconds} or {text: null, error}",
    "history": "History changed: {action: added|edited|deleted|cleared, id, source}",
    "model": "A model download: {id, status: downloading|installed|failed|cancelled, error}",
}

# (method, path, needs local_api_control, what it does). Served as GET /v1.
ROUTES = [
    ("GET", "/health", False, "App version, loaded model, whether control is on"),
    ("GET", "/v1/models", False, "The loaded model, OpenAI list shape"),
    ("POST", "/v1/audio/transcriptions", False, "Transcribe a file, OpenAI shape"),
    ("POST", "/v1/app/transcribe", True, 'Transcription Mode on a file. Body {"path": "/abs/file.mp3", "paragraphs": '
     '"none"|"time"|"model", "cleanup": bool, "save_history": false, "save_file": false}; paragraphs and cleanup '
     'default to the Transcription tab\'s settings. Answers when done (minutes for a long file)'),
    ("GET", "/v1/app/events", True, "Server-Sent Events (text/event-stream) instead of polling: "
     + "; ".join(f"{k}: {v}" for k, v in EVENTS.items()) + f". A comment line every {HEARTBEAT_S:.0f} s"),
    ("GET", "/v1/app/status", True, "State (idle, recording, busy), paused, model, app update, model downloads "
     "with progress (fraction, MB), input language"),
    ("POST", "/v1/app/dictation", True, 'Body {"action": ...}: start, stop, toggle, pause, resume, retake, discard, '
     'send (stop, then the send key), paste_last. The action keys: uses the mic, types into the focused window. '
     '409 when there is no take to act on'),
    ("GET", "/v1/app/update", True, "Check for a newer app (network)"),
    ("POST", "/v1/app/update", True, "Install it. apt only: the user approves a system prompt; poll /v1/app/status"),
    ("POST", "/v1/app/restart", True, "Restart into a version already installed, when idle"),
    ("GET", "/v1/app/models", True, "Every model: id, name, installed, disk_mb, current, recommended, downloading, progress"),
    ("GET", "/v1/app/language", True, "Input language: setting (auto|en|he), the Hebrew model's state, the last take's language"),
    ("POST", "/v1/app/language", True, 'Body {"input_language": "auto"|"en"|"he"}: Follow keyboard, English, Hebrew'),
    ("POST", "/v1/app/models/select", True, 'Body {"id": ..., "download": false}: switch model; poll /v1/app/status '
     'for download progress'),
    ("POST", "/v1/app/models/remove", True, 'Body {"id": ...}: delete a downloaded model (not the one in use, '
     'not one downloading)'),
    ("GET", "/v1/app/settings", True, "The settings this API may change, their values and what each does"),
    ("POST", "/v1/app/settings", True, 'Body {"out_clipboard": false, ...}: change settings; all checked first, then applied together'),
    ("GET", "/v1/app/mics", True, "Microphones: the connected ones (choices), and what dictation (audio_device) and "
     "Transcription Mode (tm_audio_device) use now"),
    ("POST", "/v1/app/mics", True, 'Body {"audio_device": ..., "tm_audio_device": ...}: "" system default, '
     '"@preferred" the preferred order, or a connected mic by value or key'),
    ("GET", "/v1/app/models/updates", True, "Check every downloaded model and add-on (network)"),
    ("POST", "/v1/app/models/updates", True, "Download what the check finds; poll /v1/app/status"),
    ("GET", "/v1/history", True, "Transcripts. Query: q, limit (max 1000), offset, since, until (unix time), source, edited=1"),
    ("GET", "/v1/history/{id}", True, "One transcript"),
    ("PATCH", "/v1/history/{id}", True, 'Body {"text": ...}: correct a transcript; the model\'s first text stays in `original` (edited=1 finds it)'),
    ("DELETE", "/v1/history/{id}", True, "Delete a transcript"),
    ("GET", "/v1/dictionary", True, "The personal dictionary (find and replace)"),
    ("POST", "/v1/dictionary", True, 'Body {"word": ..., "heard": [...]}: add a word, or add phrases to it'),
    ("POST", "/v1/dictionary/preview", True, 'Body {"word": ..., "heard": [...], "limit": 20}: what it would change in History; writes nothing'),
    ("DELETE", "/v1/dictionary", True, "Query word=..., optionally heard=...: remove a word or one phrase"),
]


def _matches(pattern: str, path: str) -> bool:
    """A ROUTES path against a request path: `{id}` is one non-empty segment."""
    if "{" not in pattern:
        return pattern == path
    head = pattern.split("{")[0]
    rest = path[len(head):]
    return path.startswith(head) and bool(rest) and "/" not in rest


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


def _number(value, kind, name: str):
    try:
        return kind(value)
    except (TypeError, ValueError):
        raise ApiError(400, f"{name} must be a number") from None


def _text(fields: dict, name: str) -> str:
    v = fields.get(name)
    if not isinstance(v, str) or not v.strip():
        raise ApiError(400, f"`{name}` is required")
    return v.strip()


def _phrases(body: dict) -> list[str]:
    v = body.get("heard", [])
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list) or not all(isinstance(h, str) for h in v):
        raise ApiError(400, "`heard` must be a list of strings")
    return v


class LocalApi:
    def __init__(self, transcribe, info, port: int = DEFAULT_PORT, control=None):
        self.transcribe, self.info, self.port, self.control = transcribe, info, port, control
        self._server: _Server | None = None
        self._thread: threading.Thread | None = None
        self.error: str | None = None          # why the last start failed (port in use, ...)
        self._streams: set[_Stream] = set()
        self._streams_lock = threading.Lock()
        self._seq = 0

    def publish(self, event: str, data: dict):
        """Send an event to every open GET /v1/app/events stream. Any thread; never blocks: a
        stream whose queue is full is closed instead."""
        with self._streams_lock:
            self._seq += 1
            item = (self._seq, event, data)
            for st in list(self._streams):
                try:
                    st.q.put_nowait(item)
                except queue.Full:
                    st.close("too slow: events were dropped")
                    self._streams.discard(st)

    def close_streams(self, why: str = "closed"):
        """End every event stream (stop, or control turned off)."""
        with self._streams_lock:
            for st in self._streams:
                st.close(why)
            self._streams.clear()

    @property
    def streams(self) -> int:
        return len(self._streams)

    def _subscribe(self) -> "_Stream":
        with self._streams_lock:
            if len(self._streams) >= MAX_STREAMS:
                raise ApiError(503, f"{MAX_STREAMS} event streams are open already")
            st = _Stream()
            self._streams.add(st)
            return st

    def _unsubscribe(self, st: "_Stream"):
        with self._streams_lock:
            self._streams.discard(st)

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
            self._server = _Server((HOST, self.port), Handler)
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
        self.close_streams("the app's local API stopped")
        srv, self._server = self._server, None
        if srv:
            srv.shutdown()
            srv.server_close()
            log.info("local API stopped")


class _Stream:
    def __init__(self):
        self.q: queue.Queue = queue.Queue(EVENT_BACKLOG)
        self.why: str | None = None

    def close(self, why: str):
        self.why = why
        try:
            self.q.put_nowait(None)            # wake the stream's thread
        except queue.Full:
            pass                               # it is busy draining, and sees `why` next


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
        url = urlsplit(self.path)
        path = url.path.rstrip("/")
        info = self.owner.info()
        if path in ("", "/health"):
            self._send(200, {"status": "ok" if info else "no_model", "app": __version__, "model": info,
                             "control": self._control_on()})
        elif path == "/v1":
            self._send(200, {"app": __version__, "control": self._control_on(), "routes": [
                {"method": m, "path": p, "control": c, "does": d} for m, p, c, d in ROUTES]})
        elif path == "/v1/models":
            data = [{"id": info["id"], "object": "model", "owned_by": "hebrish",
                     "version": info.get("version")}] if info else []
            self._send(200, {"object": "list", "data": data})
        else:
            self._control("GET", path, parse_qs(url.query), None)

    def do_POST(self):
        if not self._guard():
            return
        url = urlsplit(self.path)
        if url.path.rstrip("/") != "/v1/audio/transcriptions":
            self._control("POST", url.path.rstrip("/"), parse_qs(url.query), self._json_body())
            return
        try:
            self._transcribe(parse_qs(url.query))
        except ApiError as e:
            self._error(e.status, str(e))
        except Exception as e:      # the model or ffmpeg failed: say so, keep serving
            log.exception("local API transcription failed")
            self._error(500, str(e) or e.__class__.__name__)

    def do_DELETE(self):
        if not self._guard():
            return
        url = urlsplit(self.path)
        self._control("DELETE", url.path.rstrip("/"), parse_qs(url.query), None)

    def do_PATCH(self):
        if not self._guard():
            return
        url = urlsplit(self.path)
        self._control("PATCH", url.path.rstrip("/"), parse_qs(url.query), self._json_body())

    def _control_on(self) -> bool:
        c = self.owner.control
        return bool(c and c.enabled())

    def _json_body(self):
        """Read the body whatever happens next, so a refused request leaves the connection clean.
        Returns the parsed JSON, or the ApiError to raise once the route is known."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0 or n > MAX_JSON:
            self.close_connection = True
            return ApiError(413 if n > 0 else 400, "bad body size")
        raw = self.rfile.read(n) if n else b"{}"
        try:
            body = json.loads(raw)
        except ValueError:
            return ApiError(400, "the body must be JSON")
        return body if isinstance(body, dict) else ApiError(400, "the body must be a JSON object")

    def _control(self, method: str, path: str, query: dict, body):
        try:
            if not any(_matches(p, path) for m, p, c, _ in ROUTES if c and m == method):
                raise ApiError(404, f"no route {method} {path}; GET /v1 lists them")
            if not self._control_on():
                raise ApiError(403, "control is off: in Hebrish, Settings → Local API, tick "
                                    "\"Let agents read history and control the app\"")
            if isinstance(body, ApiError):
                raise body
            q = {k: v[-1] for k, v in query.items()}
            if method == "GET" and path == "/v1/app/events":
                self._events()
                return
            status, out = self._route(method, path, q, body or {})
            self._send(status, out)
        except ApiError as e:
            self._error(e.status, str(e))
        except LookupError as e:
            self._error(404, str(e.args[0]) if e.args else "not found")
        except ValueError as e:
            self._error(400, str(e))
        except RuntimeError as e:         # the app can't do it right now, or not on this install
            self._error(409, str(e))
        except Exception as e:
            log.exception("local API control failed")
            self._error(500, str(e) or e.__class__.__name__)

    def _route(self, method: str, path: str, q: dict, body: dict) -> tuple[int, dict]:
        c = self.owner.control
        if path == "/v1/history":
            return 200, self._history(q, c.history_path)
        if path.startswith("/v1/history/"):
            rid = _number(path.rsplit("/", 1)[1], int, "id")
            if method == "PATCH":
                return 200, c.edit_history(rid, _text(body, "text"))
            if method == "DELETE":
                return 200, c.delete_history(rid)
            row = history.get(c.history_path, rid)
            if row is None:
                raise ApiError(404, f"no transcript {rid}")
            return 200, row
        if path == "/v1/dictionary/preview":
            entry = {"word": _text(body, "word"), "heard": _phrases(body)}
            limit = _number(body.get("limit", 20), int, "limit")
            return 200, dictionary.preview([entry], history.texts(c.history_path), min(max(limit, 0), 200))
        if path == "/v1/dictionary":
            if method == "GET":
                return 200, {"object": "list", "data": dictionary.load(), "path": str(dictionary.PATH)}
            if method == "POST":
                entry, created = dictionary.add(_text(body, "word"), _phrases(body))
                c.dictionary_changed()
                return (201 if created else 200), {"entry": entry, "created": created}
            if not dictionary.remove(_text(q, "word"), q.get("heard")):
                raise ApiError(404, "no such word or phrase in the dictionary")
            c.dictionary_changed()
            return 200, {"removed": True}
        return c.handle(method, path, body)

    def _events(self):
        """GET /v1/app/events: one event per `publish`, `id: <n>` numbered across the app's run. The
        connection closes when the stream ends; reconnect for more (no replay: GET /v1/app/status
        and /v1/history catch up)."""
        st = self.owner._subscribe()          # ApiError 503 at the cap, before any header is sent
        self.close_connection = True
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            c = self.owner.control
            ready = {"app": __version__, **(c.take_state() if hasattr(c, "take_state") else {})}
            self._event(0, "ready", ready)
            while True:
                try:
                    item = st.q.get(timeout=HEARTBEAT_S)
                except queue.Empty:
                    item = ()
                if st.why is None and not self._control_on():
                    st.why = "control is off"
                if st.why is not None:
                    self._event(0, "closed", {"reason": st.why})
                    break
                if item:
                    self._event(*item)
                else:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
        except OSError:                        # the client went away (broken pipe, reset)
            pass
        except Exception:                      # headers are out: no error reply possible, just end
            log.exception("local API event stream failed")
        finally:
            self.owner._unsubscribe(st)

    def _event(self, seq: int, event: str, data: dict):
        head = f"id: {seq}\n" if seq else ""
        self.wfile.write(f"{head}event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode())
        self.wfile.flush()

    @staticmethod
    def _history(q: dict, path) -> dict:
        limit = _number(q.get("limit", 50), int, "limit")
        offset = _number(q.get("offset", 0), int, "offset")
        if not 0 < limit <= MAX_PAGE or offset < 0:
            raise ApiError(400, f"limit is 1 to {MAX_PAGE}, offset 0 or more")
        found = history.query(
            path, q=q.get("q", ""), limit=limit, offset=offset, source=q.get("source"),
            since=_number(q["since"], float, "since") if "since" in q else None,
            until=_number(q["until"], float, "until") if "until" in q else None,
            edited=q.get("edited", "") in ("1", "true"))
        return {"object": "list", "limit": limit, "offset": offset, **found}

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
        lang = (fields.get("language") or "").strip().lower()
        if lang in ("iw", "he-il", "heb"):
            lang = "he"
        if lang not in ("", "he", "en"):
            raise ApiError(400, "language must be he or en (or left out: the main model)")
        t0 = time.monotonic()
        text = self.owner.transcribe(samples, language=lang) if lang else self.owner.transcribe(samples)
        took = time.monotonic() - t0
        seconds = len(samples) / audio.SAMPLE_RATE
        if fmt == "text":
            self._send(200, text + "\n", "text/plain")
        elif fmt == "json":
            self._send(200, {"text": text})
        else:
            self._send(200, {"task": "transcribe", "text": text, "duration": round(seconds, 3),
                             "processing_s": round(took, 3), "model": self.owner.info(),
                             "language": lang or "en"})
