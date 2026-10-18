# Maintaining

Written 2026-10-18. (V) = verified on daniellaptop (KDE Plasma Wayland, Python 3.14.4,
sherpa-onnx 1.13.8); (I) = inferred / not yet tested.

## Layout

| Module | Role |
| --- | --- |
| `model_store.py` | HF check, download/verify, installed versions. No GTK import, so it is testable and also a CLI |
| `engine.py` | sherpa-onnx `OfflineRecognizer` (nemo_transducer), normalise, chunk, tail-pad |
| `audio.py` | sounddevice capture at 16 kHz mono, beeps |
| `hotkey.py` | evdev listener thread: hold / toggle / hybrid state machine, key capture |
| `inserter.py` | wl-copy (xclip on X11), then a paste chord through a uinput device |
| `app.py` | `Gtk.Application` (single instance, `--toggle`, `--hidden`), tray, window, controller |

All slow work runs on threads and returns to GTK through `GLib.idle_add` (`ui()` wrapper).

## Model updates: same protocol as the Android app

Source: `danielrosehill/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching`, subfolder
`sherpa-onnx/int8/` on `main`. This is the repo and folder Codeswitch Voice uses, *not* the
separate `-sherpa-onnx-int8` repo that Parakeet-Type-Ubuntu pins. The training repo's
`export_sherpa` writes `version.json` (`{"version": "v4", "run": "r4-en30"}`) there.

1. `GET /api/models/<repo>/revision/main` returns `sha`.
2. `GET /api/models/<repo>/tree/<sha>/sherpa-onnx/int8` returns each file's `size` and
   `lfs.oid` (SHA-256). `tokens.txt` has no `lfs`, so only its size is compared.
3. `GET /<repo>/resolve/<sha>/sherpa-onnx/int8/version.json` gives the label. If it is
   missing, the label is `rev <sha7>`.

An update is offered **only when the weights differ** (`Manifest.same_weights`), not when
`main` moves. Model-card and eval commits move `main` constantly.

A download goes into `models/<version>-<sha12>/`, pinned to that `sha`, with `.part` files
that resume. Each file is size-checked and SHA-256-checked. `manifest.json` is written last
and marks the folder as complete. Only then do `state.json`'s `active` and the optional
`prune_except` run. The engine reloads when idle; while a take is in flight the reload is
deferred (`reload_pending`).

Verified live 2026-10-18 (V):
- The first-run download of v4 (main `edbc85c1ce89`, encoder sha `a6b068a3…`) succeeded.
- After it, a check reports "up to date".

The update branch (old version installed, new weights published) is covered only by
`tests/test_model_store.py` (I for the live path; v5 will be the first real one).

## Findings

- **Tail padding is required (V).** With less than 0.6 s of silence after the last word,
  Parakeet (v4, sherpa-onnx int8) dropped the *whole final sentence* of a chunk, not just
  the last word. Measured on an 8-sentence, 56 s concatenation: the chunk ending 0.1 s after
  sentence 4 lost it entirely. 0.3 s of padding was not enough, 0.6 s and 1.0 s were.
  `TAIL_PAD_S = 1.0`. This matters beyond chunking: releasing push-to-talk right as you
  finish speaking produces exactly that audio.
- **Identical repeated audio collapses (V, harmless).** Six back-to-back copies of the same
  waveform decode as about two sentences even without chunking. It is a test-input artifact
  and has nothing to do with the splitter. Test long takes with *distinct* sentences.
- Long takes are decoded in ≤30 s pieces, cut at the quietest 100 ms window in the last
  5 s of each piece. The 56 s test decoded in 4.4 s on the laptop CPU (V).
- **The venv must use `/usr/bin/python3` (V).** `uv venv --system-site-packages` without
  `--python` picked a uv-managed 3.13, and then `gi` and `evdev` (distro packages built
  for 3.14) didn't import. `install.sh` pins the interpreter.
- **`install.sh` and `pipefail` (V):** `ldconfig -p | grep -q` reported libportaudio as
  missing when it was installed. `grep -q` exits on the first match, `ldconfig` gets
  SIGPIPE, and the pipeline fails. Use a here-string instead.
- **Paste, not typing (V).** Typed keycodes are turned into characters by the active
  layout, so with Hebrew selected "pensia" would come out in Hebrew letters. A Ctrl+V
  keycode works on any layout. The uinput paste reached a focused GTK window on KWin
  Wayland (V). Terminals need `ctrl+shift+v` (set *Paste shortcut*); per-app detection
  is deliberately left out.
- `/dev/uinput` on this machine is `root:input 0660` plus a logind uaccess ACL for the
  seat user, so it is writable without udev rules (V). Other distros may need a rule (I).
- evdev reading is non-exclusive: the hotkey also reaches other apps and other dictation
  tools. Voxtype on the same machine uses F13, which is also this app's default hotkey.
  Pick a different key if both run.
- The hotkey listener ignores its own uinput device by name (`OWN_DEVICE_NAME`).
  Otherwise it would hear its own paste chord.
- With a modifier as the hotkey (e.g. Right Ctrl), pressing another key while holding it
  cancels the take, so Right-Ctrl+C stays a shortcut.
- `libayatana-appindicator is deprecated` is printed at startup. It is harmless: the GIR
  binding for the -glib replacement isn't packaged on Ubuntu yet (I).

## Testing

- `.venv/bin/python -m pytest tests`: offline tests of the update logic.
- To smoke-test without touching real settings or colliding with another dictation tool,
  run with `XDG_CONFIG_HOME=<tmp>` and a config of
  `{"hotkey": "KEY_F20", "insert": "clipboard"}`. Inject F20 through a throwaway
  `evdev.UInput`. Wait ≥4 s after creating the device: the listener rescans every 3 s.
- When killing a test instance, don't `pkill -f codeswitch-dictation`: the pattern also
  matches the shell running the command.
