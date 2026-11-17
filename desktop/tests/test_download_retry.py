"""fetch_files retries transient network errors and resumes the .part (2026-11-17, the desktop port of
Android's DownloadRetry). A local HTTP server misbehaves on cue; sleep is faked so the tests take no time."""

import hashlib
import http.server
import os
import sys
import threading
import urllib.error

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from hebrish import model_store as ms  # noqa: E402

BODY = bytes(range(256)) * 4096          # 1 MiB
SHA = hashlib.sha256(BODY).hexdigest()


class Server:
    """script: list of actions, one per request: "ok", "cut" (send half the body, then close),
    or an int HTTP status. Once exhausted, every request is "ok"."""

    def __init__(self, script):
        self.script, self.ranges = list(script), []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                action = outer.script.pop(0) if outer.script else "ok"
                rng = self.headers.get("Range")
                outer.ranges.append(rng)
                if isinstance(action, int):
                    self.send_response(action)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                start = int(rng[6:-1]) if rng else 0
                body = BODY[start:]
                self.send_response(206 if rng else 200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if action == "cut":
                    self.wfile.write(body[:len(body) // 2])
                    self.wfile.flush()
                    self.close_connection = True
                    return
                self.wfile.write(body)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/"

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def serve():
    servers = []

    def make(script):
        servers.append(Server(script))
        return servers[-1]
    yield make
    for s in servers:
        s.close()


def fetch(tmp_path, srv, **kw):
    names, now = [], [0.0]

    def sleep(s):
        now[0] += s
    ms.fetch_files(tmp_path, {"w.onnx": {"size": len(BODY), "sha256": SHA}}, lambda n: srv.url + n,
                   lambda d, t, n: names.append(n), sleep=sleep, clock=lambda: now[0], **kw)
    return names


def test_a_cut_connection_resumes_from_the_part(tmp_path, serve):
    srv = serve(["cut"])
    names = fetch(tmp_path, srv)
    assert (tmp_path / "w.onnx").read_bytes() == BODY
    assert srv.ranges[0] is None and srv.ranges[1] == f"bytes={len(BODY) // 2}-"
    assert any(n.startswith(ms.RETRYING) for n in names)


@pytest.mark.parametrize("code", [500, 503, 429, 408])
def test_server_errors_are_retried(tmp_path, serve, code):
    srv = serve([code, code])
    fetch(tmp_path, srv)
    assert (tmp_path / "w.onnx").read_bytes() == BODY
    assert len(srv.ranges) == 3


def test_a_404_is_not_retried(tmp_path, serve):
    srv = serve([404])
    with pytest.raises(urllib.error.HTTPError):
        fetch(tmp_path, srv)
    assert len(srv.ranges) == 1


def test_gives_up_after_no_progress(tmp_path, serve, monkeypatch):
    srv = serve([503] * 100)
    now = [0.0]

    def sleep(s):
        now[0] += s
    with pytest.raises(RuntimeError, match="no progress"):
        ms.fetch_files(tmp_path, {"w.onnx": {"size": len(BODY), "sha256": SHA}}, lambda n: srv.url + n,
                       sleep=sleep, clock=lambda: now[0])
    assert ms.NO_PROGRESS_S < now[0] < ms.NO_PROGRESS_S + 2 * max(ms.BACKOFF_S)


def test_a_complete_part_is_not_fetched_again(tmp_path, serve):
    srv = serve([])
    (tmp_path / "w.onnx.part").write_bytes(BODY)
    fetch(tmp_path, srv)
    assert srv.ranges == [] and (tmp_path / "w.onnx").read_bytes() == BODY


def test_cancel_during_backoff(tmp_path, serve):
    srv = serve([503] * 10)
    cancel = threading.Event()

    def sleep(s):
        cancel.set()
    with pytest.raises(ms.Cancelled):
        ms.fetch_files(tmp_path, {"w.onnx": {"size": len(BODY), "sha256": SHA}}, lambda n: srv.url + n,
                       cancel=cancel, sleep=sleep)


def test_backoff_steps():
    assert [ms.backoff_s(i) for i in range(7)] == [2, 4, 8, 15, 30, 30, 30]
