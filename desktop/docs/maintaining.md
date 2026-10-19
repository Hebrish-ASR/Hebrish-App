# Maintaining

Written 2026-10-18. (V) = verified on daniellaptop (KDE Plasma Wayland, Python 3.14.4,
sherpa-onnx 1.13.8); (I) = inferred / not yet tested.

## Layout

| Module | Role |
| --- | --- |
| `model_store.py` | HF check, download/verify, installed versions. No Qt import, so it is testable and also a CLI |
| `engine.py` | sherpa-onnx `OfflineRecognizer` (nemo_transducer): normalise, chunk, pad, `transcribe_chunks` generator |
| `audio.py` | sounddevice capture (pause/resume, level meter), file decoding (ffmpeg, else soundfile), WAV save, beeps |
| `hotkey.py` | the shared hold / toggle / hybrid state machine, on evdev-style key names |
| `hotkey_evdev.py` / `hotkey_win.py` | per-OS key sources: `/dev/input` on Linux, a pynput low-level hook on Windows |
| `inserter.py` + `inserter_linux.py` / `inserter_win.py` | clipboard, then a paste chord (uinput / SendInput) |
| `autostart.py` | XDG autostart entry / HKCU `Run` key |
| `ui/app.py` | `Controller`, tray, single instance + `--toggle` over `QLocalServer`, `--selftest`, `main()` |
| `ui/window.py`, `ui/transcribe.py`, `ui/about.py`, `ui/style.py` | window, tabs, About copy and numbers, QSS. `about.HEBRISH_LINKS` is the one list of hebrish.app URLs (site, `contact?topic=word/samples/involved`, and `mailto:feedback@hebrish.app` links for bug / feature / feedback with app and OS version in the body; since 0.1.1). The app icon `data/icons/parlance.svg` is the Hebrish mark, copied from `Hebrish-Mgmt/brand/logo/mark.svg`, read by the About tab, the Model tab and the tray submenu |

Threads: the hotkey source, decoding, the HF check and downloads run off the GUI thread.
They report back only through `Signal`s, whose cross-thread emits Qt queues onto the GUI
thread.

**Why Qt (PySide6), from 0.2.0:** 0.1.0 was GTK 3 + AyatanaAppIndicator, which is Linux-only.
Qt gives one UI for Linux and Windows. It is in Ubuntu 26.04's apt (6.10.2), so the .deb
depends on it rather than bundling 200 MB. It is also native on KDE, the main target.

## Model updates

The protocol is shared with Android and documented once, in
[`../../shared/update-protocol.md`](../../shared/update-protocol.md). On the desktop, the
implementation details are these:
- `manifest.json` is written last and marks a version folder as complete.
- `state.json`'s `active` and the optional `prune_except` only run after that.
- The engine reloads when idle. While a take is in flight, the reload is deferred
  (`reload_pending`).

Verified live 2026-10-18 (V):
- The first-run download of v4 (main `edbc85c1ce89`, encoder sha `a6b068a3…`) succeeded.
- After it, a check reports "up to date".

The update branch (old version installed, new weights published) is covered only by
`tests/test_model_store.py` (I for the live path; v5 will be the first real one).

## Findings

(0.1.0, still valid.) Since 0.2.0 the venv and `.deb` use apt's PySide6, not GTK; the `/usr/bin/python3` requirement below stands.


- **Tail padding is required (V).** With less than 0.6 s of silence after the last word,
  Parakeet (v4, sherpa-onnx int8) dropped the *whole final sentence* of a chunk, not just
  the last word. Measured on an 8-sentence, 56 s concatenation: the chunk ending 0.1 s after
  sentence 4 lost it entirely. 0.3 s of padding was not enough, 0.6 s and 1.0 s were.
  `TAIL_PAD_S = 1.0`. This matters beyond chunking: releasing push-to-talk right as you
  finish speaking produces exactly that audio.
- **Short pauses between sentences swallow speech (V, 2026-10-18, 0.2.0).** In one decode,
  sentence A + 0.3 s + sentence B lost the first half of B ("Hi Dana, I wanted to thank you
  for recommending the mehanechet"), though B decodes perfectly alone. Gaps of 0.6, 1.0
  and 2.0 s lost nothing. It isn't the chunker or MP3: it reproduced with WAV and no
  chunk boundary. `engine.stretch_pauses` pads every inner quiet run of 0.12–0.6 s to
  0.6 s. Sentences recovered, out of 8 hard words in an 8-sentence, 53 s file:

  | Input | Plain | min_run 0.12 | 0.2 | 0.25 |
  | --- | --- | --- | --- | --- |
  | 0.3 s gaps | 6 | **8** | 8 | 7 |
  | 0.2 s gaps | – | **7** | 7 | 7 |
  | no gaps | 6 | **7** | 6 | 6 |
  | MP3 of the above | 7 | **7** | 6 | 6 |

  With 0.12, the only single-sentence clip whose transcript changed got better
  ("Bokartov" → "Boker Tov"). The audio decoded grows by ~1.2×. "Quiet" is adaptive:
  below 15% of the way from the 10th to the 90th percentile frame RMS. The test clips are
  trimmed training recordings joined back to back, which is harsher than natural speech
  (I: real pauses are usually longer, so the gain may be smaller in practice).
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

## Releasing

1. Bump `__version__` in `parlance/__init__.py` and write
   `../.github/desktop-release-notes.md`.
2. Push the tag `desktop-v<ver>`. CI (`.github/workflows/desktop.yml`) runs the tests on
   Linux and Windows, builds the Windows zip with PyInstaller, runs the frozen exe's
   `--selftest`, and creates the release with the zip attached.
3. On Ubuntu 26.04, run `./build-deb.sh`. It writes `dist/parlance_<ver>-1_amd64.deb`,
   bundles sherpa-onnx + sherpa-onnx-core, and is pinned to the build machine's python3
   minor (3.14). Then run `gh release upload desktop-v<ver> dist/*.deb`. CI can't build it
   because the GitHub runners' Ubuntu has an older python3.

The download links live in these places. Update them when a version changes:
- the root README;
- the project hub `English-Hebrew-Codeswitching-Parakeet-Finetune` README;
- the HF model card;
- `Speech-Tech-Index`;
- `English-Hebrew-Code-Switching-Index` (README and `data/index.json`).

The package has `Conflicts`/`Replaces` on the predecessors (`voice-to-hebrish`,
`codeswitch-dictation`, and `parakeet-dictation` from Parakeet-Type-Ubuntu), so only one Linux
dictation app is ever installed. On first start (no `~/.config/parlance/config.json` yet),
`config.migrate_legacy()` copies Voice To Hebrish's (or Codeswitch Dictation's) settings and transcript history, and
**moves** its downloaded versions into `models/codeswitch/`, then selects that model, so
nothing is downloaded again.

**Trap (V, 2026-10-18, seen when Codeswitch Dictation 0.1.0 became Voice To Hebrish 0.2.0):** if the old app is
still running when the new one first starts, the move pulls the model out from under it. The
old app then sees no model and downloads 660 MB again into its own folder. Quit the old app
(and purge its package) before the first Parlance start.

## Models

The catalogue is `../shared/models.json`, bundled as `parlance/data/models.json`
(`tests/test_shared.py` fails if the copies differ). Each update check first re-fetches it
from `catalogue_url` (raw GitHub, `main`) into `~/.local/share/parlance/catalogue.json`; an
unparseable or wrong-`schema` copy is ignored and the bundled one is used. So **publishing a
model needs no app release**: push the HF repo (files: `encoder.int8.onnx`,
`decoder.int8.onnx`, `joiner.int8.onnx`, `tokens.txt`, optional `version.json`), then flip its
entry to `"status": "available"` with `repo` and `subdir`, re-copy the bundled file, push.

- `subdir` may be empty: the stock mirror (`csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8`)
  keeps its files at the repo root. `Model.path()` joins without stray slashes.
- `version_label` is the label for a repo without `version.json` (stock: `v2`).
- Layout: `models/<id>/<version>-<sha12>/`. `state.json` holds `model` (the selected id) and
  `active` (`{id: dirname}`). Pruning old versions never crosses model ids.
- A model in the middle of a download can't be switched away from (the picker is disabled).

Verified 2026-10-19 (V): stock downloaded through `parlance-model download stock` (630 MB,
SHA-256 checked) and decoded the mirror's `test_wavs/0.wav` correctly with the unchanged
engine settings (`feature_dim=128`, greedy search). Code-switch `check` returned v5, r5-en30.

It ships `/usr/lib/udev/rules.d/70-parlance-uinput.rules` (uaccess on
uinput, the same rule Steam uses) for the paste device. The hotkey still needs the
`input` group, because a uaccess rule on keyboards would let any seat app read keystrokes.

Verified 2026-10-18 (V): 0.1.0 installed with apt on daniellaptop. `ldd` shows no missing
libs in the bundled .so files, and `--toggle` record → transcribe ran from `/usr/bin`.

## Testing

- `.venv/bin/python -m pytest tests`: offline tests of the update logic, the hotkey state
  machine, chord parsing, and drift from `shared/models.json`.
- UI: render the tabs off-screen with `QT_QPA_PLATFORM=offscreen` and `window.grab()`.
  Drive the Transcribe tab with `win.transcribe.transcribe_file(path)`.
- To smoke-test without touching real settings or colliding with another dictation tool,
  run with `XDG_CONFIG_HOME=<tmp>` and a config of
  `{"hotkey": "KEY_F20", "insert": "clipboard"}`. Inject F20 through a throwaway
  `evdev.UInput`. Wait ≥4 s after creating the device: the listener rescans every 3 s.
- When killing a test instance, don't `pkill -f parlance`: the pattern also
  matches the shell running the command.

## Display name: Hebrish (0.1.2, 2026-10-19)

User-facing name is **Hebrish** so app search finds it; everything that identifies the install keeps `parlance`. Desktop: `config.APP_NAME` (window, tray, About, Linux autostart entry) and `Name=` in `packaging/parlance.desktop` (with `parlance` kept in `Keywords=`). Unchanged: the package and command `parlance`, `APP_ID`, config/data dirs, `Icon=parlance`, and `config.AUTOSTART_KEY = "Parlance"`, the Windows Run-key value name, so an existing autostart entry is still found. Release assets keep the Parlance file names.
