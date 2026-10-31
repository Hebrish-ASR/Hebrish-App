# Windows: local API "started" on a port another app already held

- **Date:** 2026-10-31
- **Platform:** desktop, Windows
- **Status:** fixed, unreleased (next stable)
- **Found by:** the `windows` job of `.github/workflows/desktop.yml` (run 41223255915, the first
  `stable=true` dispatch), test `tests/test_local_api.py::test_port_in_use_is_reported`.

## What was broken

`hebrish/local_api.py` built its server with `http.server.ThreadingHTTPServer`, which sets
`allow_reuse_address = 1` (SO_REUSEADDR). On Linux that only allows rebinding a port in
TIME_WAIT. On Windows SO_REUSEADDR lets a second socket bind a port that is **actively in use**,
so `LocalApi.start()` returned True when another program already listened on 8723. Requests kept
going to the other program, and Settings showed the API as running.

## Fix

A `_Server(ThreadingHTTPServer)` subclass with `allow_reuse_address = sys.platform != "win32"`.
Windows then refuses the bind (WSAEADDRINUSE) and the existing "Couldn't listen on ..." error is
shown. Linux behaviour is unchanged.

## Same run, test-only

`tests/test_transcripts.py::test_hebrish_folder` asserted the XDG `user-dirs.dirs` lookup
(localised Documents folder) on Windows too, where `config.documents_dir()` deliberately skips
it. The XDG part of the test now runs on Linux only. No app change.

## Why it wasn't caught earlier

Before B-81 the Windows build ran on every dev dispatch only when asked (`windows=true`), and no
dispatch had run since these tests were added on 2026-10-31.
