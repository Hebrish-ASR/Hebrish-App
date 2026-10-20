# Maintaining

Written 2026-10-18. (V) = verified on daniellaptop (KDE Plasma Wayland, Python 3.14.4,
sherpa-onnx 1.13.8); (I) = inferred / not yet tested.

## Layout

| Module | Role |
| --- | --- |
| `model_store.py` | HF check, download/verify, installed versions. No Qt import, so it is testable and also a CLI |
| `engine.py` | sherpa-onnx `OfflineRecognizer` (nemo_transducer): normalise, cut at pauses (`live_cut`, `split_points`), pad, `transcribe_chunks` generator |
| `audio.py` | sounddevice capture (pause/resume, level meter, `peek`/`consume` for live insertion), file decoding (ffmpeg, else soundfile), WAV save, beeps |
| `hotkey.py` | the shared state machine for the two keys (toggle, push-to-talk) and the action keys, on evdev-style key names |
| `hotkey_evdev.py` / `hotkey_win.py` | per-OS key sources: `/dev/input` on Linux, a pynput low-level hook on Windows |
| `inserter.py` + `inserter_linux.py` / `inserter_win.py` | clipboard, then a paste chord (uinput / SendInput) |
| `autostart.py` | XDG autostart entry / HKCU `Run` key |
| `ui/app.py` | `Controller`, tray, single instance + `--toggle` over `QLocalServer`, `--selftest`, `main()` |
| `ui/overlay.py` | the floating overlay widget, `OverlayHost` (in-process or an XWayland child), and the child's `__main__` |
| `ui/splash.py` | the start-up screen |
| `ui/meter.py` | the Dictate tab's level meter (zones, peak tick, clip lamp) |
| `ui/window.py`, `ui/transcribe.py`, `ui/about.py`, `ui/style.py` | window, tabs, About copy and numbers, QSS. `about.HEBRISH_LINKS` is the one list of hebrish.app URLs (site, `contact?topic=word/samples/involved`, and `mailto:feedback@hebrish.app` links for bug / feature / feedback with app and OS version in the body; since 0.1.1). The app icon `data/icons/hebrish.svg` is the Hebrish mark, copied from `Hebrish-Mgmt/brand/logo/mark.svg`, read by the About tab, the Model tab and the tray submenu |

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

## Two hotkeys (0.3.0, 2026-10-20)

Daniel asked for separate shortcuts for tap-tap and push-to-talk. Config: `hotkey` (toggle;
`hold_to_talk` keeps the old hybrid behaviour, on by default), `ptt_hotkey` (hold only), either
`""` = off. The old `mode` key is mapped by `config.upgrade()` (hold → the key moves to
`ptt_hotkey`; toggle → `hold_to_talk: false`; hybrid → nothing), applied when loading the config
and in both imports. Rules in `HotkeyMachine.key`: while one hotkey is down the other is ignored;
the PTT key never stops a take the toggle key started; Settings won't let one key be both (the
other slot is cleared). The Parlance import skips both key fields. Tests: `tests/test_hotkey.py`.

## Action keys, live insertion, beeps (0.4.0, 2026-10-21)

Daniel asked (2026-10-21) for one key per action for a macropad, for text to appear during long
takes on CPU-only machines, for quiet hours and a beep volume, and for a sign that a setting was
saved.

- **Action keys:** config `key_start`, `key_stop`, `key_pause`, `key_retake`, `key_discard`
  (`""` = off; list in `hotkey.ACTIONS`, every key slot in `hotkey.SLOTS`). `HotkeyMachine.key`
  handles them first, on press only, and returns. So they never count as a chord and never
  cancel a modifier take. They go through `Signals.action` to `Controller.do_action`, which the
  overlay buttons also use. *Start* while paused resumes. Assigning a key to a slot clears it
  from every other slot. The Parlance import skips them like the other keys.
- **Decode worker:** every decode is a job `(take, samples, final)` on one queue, handled in
  order by one thread (`Controller._worker`). `start()` and `cancel()` bump `_take`; jobs from an
  older take are decoded as empty (dropped). The final job emits `transcribed` with all of the
  take's pieces joined, for the history. Pieces before the final one are inserted with a
  trailing space whatever `trailing_space` says.
- **Live insertion** (`live_insert_s`, 0 = off; 10 by default since 0.5.0): a 500 ms timer while recording
  calls `engine.live_cut(recorder.peek(), interval)`. Once the unconsumed audio is at least
  `interval` long, it looks in the last 6 s (not the newest 0.3 s) for the longest quiet run. If
  that run is at least 0.6 s, it cuts in its middle. With no such pause by interval + 15 s, it
  cuts at the quietest 100 ms. `Recorder.consume(cut)` removes the piece and queues it. Discard
  and Retake can't take back text already inserted (said in Settings).
- **Pause cuts for whole takes too:** `split_points` now runs the same `live_cut` over a
  finished take (grow by 0.5 s until it cuts, pieces ≥10 s; a remainder ≤25 s is one piece).
  The Transcribe tab still starts a paragraph about every 30 s of audio (`PARAGRAPH_S`).
- **Threads:** `num_threads` 0 = auto = `os.cpu_count() // 2`, between 1 and 8 (`config.threads`).
  0.3.x configs all hold the old default 4, which had no UI. `upgrade()` turns a 4 into 0 in a file
  without `live_insert_s`.
- **Beeps:** `beep_volume` % (50 = the old amplitude 0.25), `quiet_hours` with `quiet_from` /
  `quiet_to` "HH:MM", which may cross midnight (`config.in_quiet_hours`). Only
  `Controller.cue` plays dictation sounds (0.4.0: `_beep`; see 0.5.0 below). The volume slider plays a test beep on release.
- **Toast:** `Config.on_set` is called after every `Config.set`. The window shows "Settings
  saved" for 1.6 s, only while it is visible, and not for `overlay_pos` (dragging the overlay).

Measured 2026-10-21 (V) on daniellaptop (Ryzen 7 5700U, 8 cores / 16 threads), Jachnun v1.0
int8, with the six clips in `Parakeet-blends-wt/spaces/parakeet-demo/examples/` (references in
`examples.json`) concatenated into ~50 s takes, in six random orders, with 0.25, 0.4 or 0.7 s
gaps. Total: 786 reference words; the WER normalisation is lowercase with punctuation stripped:

| Decode | Errors | WER |
| --- | --- | --- |
| 0.3.x: 30 s pieces, quietest-100 ms cut | 126 | 16.0% |
| live, 10 s, pause ≥0.3 s | 10 | 1.3% |
| live, 15 s, pause ≥0.3 s | 24 | 3.1% |
| live, 10 s, pause ≥0.6 s | 9 | 1.1% |
| live, 15 s, pause ≥0.6 s | 10 | 1.3% |
| 0.4.0 whole take (pause-cut `split_points`) | 8 | 1.0% |

The 0.3.x losses were whole sentences: a piece ending mid-sentence dropped that unfinished
sentence (the same failure as "Tail padding" above, from the other side). With 0.3 s pauses,
the cuts landed inside sentences and lost words the same way, hence 0.6 s. Speed is unchanged
(4.75 s for a ~50 s take, whole). Threads, on 51 s of speech: 2 → 7.26 s, 4 → 4.94, 6 → 4.73,
8 → 4.41, 12 → 5.29, 16 → 5.79.

Live, end to end through the real `Controller`, with a fake recorder playing a 52 s take in
real time and live insertion at 10 s: pieces were inserted at 11.6, 20.6, 29.3, 37.5 and 45.9 s.
The last one landed 1.09 s after stop, where decoding the whole take took ~5 s. The history got
one entry of 131 words. (I) Real speech has longer pauses between sentences than these
back-to-back clips, so cuts should land at sentence ends more often. Not yet tried with a live mic.

**VAD (not added; decided 2026-10-21).** `live_cut` and `stretch_pauses` already work as an
energy VAD: quiet is relative to the take's own 10th/90th-percentile frame RMS. Silero VAD
through `sherpa_onnx.VoiceActivityDetector` (~2 MB model) would be sturdier in steady noise
(fans, cafés), but it would be one more download and the cut points above already measure at
1% WER. Revisit if cuts misfire in noisy rooms. Trimming silence to save decode time isn't
worth it: dictation is mostly speech, and the pauses have to stay (see "Short pauses").

## Floating overlay (0.3.0, 2026-10-20)

Daniel: "an optional overlay to match the android app". `ui/overlay.py`. Config `overlay`
(`off` default | `active` = while a take is open, busy or just inserted | `always` = also an idle
mic button), `overlay_pos` (the mic square's top-left in screen coordinates; `None` = bottom
centre, 72 px above the work area), `overlay_opacity` (idle only). The Controller pushes one dict
(`_overlay_push`) on every state change and at 15 Hz while recording (level, seconds). Model
loading counts as idle for the overlay, so start-up doesn't show "Transcribing…". Overlay
actions: `toggle`, `pause` (`Recorder.pause/resume`, which closes the mic stream), `retake`
(cancel + start), `discard` (cancel). It is painted by hand (no child widgets), so nothing in
it can take focus.

**Why a child process on Wayland.** The overlay must never take keyboard focus: the paste goes to
the focused window. xdg-shell lets a client neither position a toplevel, nor keep it above other
windows, nor map it without focus (Mutter focuses new windows; Qt's
`WindowDoesNotAcceptFocus` has no Wayland equivalent). wlr-layer-shell would do it but GNOME
doesn't implement it and PySide6 has no LayerShellQt binding. So on a Wayland session
`OverlayHost` starts `python -m hebrish.ui.overlay` with `QT_QPA_PLATFORM=xcb` and
`PYTHONPATH` = the parent's `sys.path` (the .deb's `/usr/lib/hebrish` is only on the path via
the launcher script). There the window has `X11BypassWindowManagerHint`, i.e. override-redirect:
XWayland compositors map those where they ask, above managed windows, and never focus them. The
main window stays native Wayland. Protocol: JSON lines; the parent sends only changed keys (the
full state on a (re)start), the child sends `{"action": …}` and `{"pos": [x, y]}`; EOF on stdin
quits it; it is restarted up to 3 times. On Windows and X11 sessions it runs in-process
(Windows: `WindowDoesNotAcceptFocus` = `WS_EX_NOACTIVATE`). With Wayland and no `$DISPLAY` the
overlay is unavailable and Settings says why.

Verified 2026-10-20 (V): all states render off-screen (`QT_QPA_PLATFORM=offscreen`); clicks and
drags map to actions and positions, and the child protocol round-trips (`tests/test_overlay.py`,
skipped on Linux CI, which has no PySide6); the child starts on xcb under KDE Plasma Wayland
with the bypass flag set (no window mapped). **Not yet verified live (I):** placement, stacking
and no-focus on KWin and Mutter, and how it scales under GNOME fractional scaling (XWayland
windows may be blurry or sized at 1x there). Run it once on each before relying on it.

## Wayland (0.3.0, 2026-10-20)

Ubuntu 26.04 defaults to GNOME on Wayland; Daniel's machine is KDE Plasma on Wayland. How
each part works there:

| Part | Wayland route | Status |
| --- | --- | --- |
| Main window | native Wayland (Qt `wayland` plugin). The .deb now Depends on `qt6-wayland`: without it Qt silently falls back to XWayland | (V) KDE |
| Window icon / grouping | `app.setDesktopFileName("hebrish")` = the xdg app_id, matching `hebrish.desktop` | (V) KDE |
| Raising the window from a second launch | the second instance forwards its `XDG_ACTIVATION_TOKEN` over the local socket (`show <token>`); the first puts it in its environment, where Qt's Wayland plugin uses it once for xdg-activation. Without a token, compositors refuse to raise and may only flash the taskbar entry | (I) |
| Hotkeys | evdev from `/dev/input` (needs the `input` group): compositor-independent, reports release | (V) KDE; (I) GNOME, same kernel path |
| Paste | Ctrl+V through a uinput device | (V) KWin; (I) Mutter, same kernel path |
| Clipboard while unfocused | `inserter_linux.clipboard_command()`: `wl-copy` where the compositor has data-control (KWin, wlroots, Hyprland); on GNOME `xclip` first, because Mutter has no data-control and wl-copy's fallback grabs focus with a temporary surface. The .deb Depends on both | (V) KDE; (I) GNOME |
| Overlay | XWayland override-redirect child, above | (I) live |
| Splash | a normal toplevel; the compositor places it (usually centred) | (V) KDE |
| Tray | StatusNotifierItem over D-Bus. Ubuntu's GNOME shows it through its default-enabled AppIndicator extension; stock GNOME without that extension has no tray (close leaves the app running: start it again or use `hebrish --toggle`) | (V) KDE; (I) Ubuntu GNOME |

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
- Long takes were decoded in ≤30 s pieces, cut at the quietest 100 ms window in the last
  5 s of each piece. The 56 s test decoded in 4.4 s on the laptop CPU (V). **Replaced in 0.4.0**
  by pause cuts every ~10–25 s: see "Live insertion and pause cuts".
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
  tools. Voxtype on the same machine and Parlance both use F13, so Hebrish's default is F14
  (since 0.2.0). Pick a different key if another tool uses it.
- The hotkey listener ignores its own uinput device by name (`OWN_DEVICE_NAME`,
  `hebrish-keyboard`), and Parlance's (`parlance-keyboard`), via `IGNORED_DEVICES`.
  Otherwise it would hear its own, or the other app's, paste chord.
- With a modifier as the hotkey (e.g. Right Ctrl), pressing another key while holding it
  cancels the take, so Right-Ctrl+C stays a shortcut.
- `libayatana-appindicator is deprecated` is printed at startup. It is harmless: the GIR
  binding for the -glib replacement isn't packaged on Ubuntu yet (I).

## Releasing

1. Bump `__version__` in `hebrish/__init__.py` and write
   `../.github/desktop-release-notes.md`.
2. Push the tag `desktop-v<ver>`. CI (`.github/workflows/desktop.yml`) runs the tests on
   Linux and Windows, builds the Windows zip with PyInstaller, runs the frozen exe's
   `--selftest`, and creates the release with the zip attached.
3. On Ubuntu 26.04, run `./build-deb.sh`. It writes `dist/hebrish_<ver>-1_amd64.deb`,
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
dictation app is ever installed (the separate `parlance` package is not a predecessor and is deliberately not listed: see "Hebrish and Parlance"). On first start (no `~/.config/hebrish/config.json` yet, and nothing imported from Parlance),
`config.migrate_legacy()` copies Voice To Hebrish's (or Codeswitch Dictation's) settings and transcript history, and
**moves** its downloaded versions into `models/codeswitch/`, then selects that model, so
nothing is downloaded again.

**Trap (V, 2026-10-18, seen when Codeswitch Dictation 0.1.0 became Voice To Hebrish 0.2.0):** if the old app is
still running when the new one first starts, the move pulls the model out from under it. The
old app then sees no model and downloads 660 MB again into its own folder. Quit the old app
(and purge its package) before the first Hebrish start.

## Models

The catalogue is `../shared/models.json`, bundled as `hebrish/data/models.json`
(`tests/test_shared.py` fails if the copies differ). Each update check first re-fetches it
from `catalogue_url` (raw GitHub, `main`; builds up to 0.1.2 use the pre-2026-10-19 repo name `Parlance-Dictation` and depend on GitHub's rename redirect, see `android/docs/maintaining.md`, "Repo name") into `~/.local/share/hebrish/catalogue.json`; an
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

Verified 2026-10-19 (V): stock downloaded through `parlance-model download stock` (the command's name at the time) (630 MB,
SHA-256 checked) and decoded the mirror's `test_wavs/0.wav` correctly with the unchanged
engine settings (`feature_dim=128`, greedy search). Code-switch `check` returned v5, r5-en30.

It ships `/usr/lib/udev/rules.d/70-hebrish-uinput.rules` (uaccess on
uinput, the same rule Steam uses) for the paste device. The hotkey still needs the
`input` group, because a uaccess rule on keyboards would let any seat app read keystrokes.

Verified 2026-10-18 (V): 0.1.0 installed with apt on daniellaptop. `ldd` shows no missing
libs in the bundled .so files, and `--toggle` record → transcribe ran from `/usr/bin`.

## Testing

- `.venv/bin/python -m pytest tests`: offline tests of the update logic, the hotkey state
  machine and config upgrade, chord parsing, the overlay (off-screen), and drift from
  `shared/models.json`.
- UI: render the tabs off-screen with `QT_QPA_PLATFORM=offscreen` and `window.grab()`.
  Drive the Transcribe tab with `win.transcribe.transcribe_file(path)`.
- To smoke-test without touching real settings or colliding with another dictation tool,
  run with `XDG_CONFIG_HOME=<tmp>` and a config of
  `{"hotkey": "KEY_F20", "insert": "clipboard"}`. Inject F20 through a throwaway
  `evdev.UInput`. Wait ≥4 s after creating the device: the listener rescans every 3 s.
- When killing a test instance, don't `pkill -f hebrish`: the pattern also
  matches the shell running the command.

## Display name: Hebrish (0.1.2, 2026-10-19)

0.1.2 changed only the user-facing name (`config.APP_NAME`, `Name=` in the .desktop file) and
deliberately kept every identifier `parlance` (package, command, `APP_ID`, dirs, icon, autostart
key) so existing installs carried over. **Reversed 2026-10-19, for 0.2.0** (next section).

## Hebrish and Parlance (0.2.0, 2026-10-19)

Decision, 2026-10-19: every internal `parlance` identifier is now `hebrish`, for clarity, done
while installs were near zero (0.1.2 shipped the same day). Parlance was then re-created as a
separate, live app (`danielrosehill/Parlance-Dictation`, local `../../Parlance-Dictation`)
that keeps every `parlance` identifier; Parlance 0.2.0 upgrades the 0.1.x `parlance` package in
place. Daniel wants both installed at once, so the rename is a split, not a replacement:

- Identifiers: package and commands `hebrish` / `hebrish-model`, Python package `hebrish`,
  `APP_ID = "app.hebrish.Dictation"`, dirs `~/.config/hebrish`, `~/.local/share/hebrish`
  (`%APPDATA%\Hebrish`, `%LOCALAPPDATA%\Hebrish`, log `hebrish.log`), single-instance socket
  `hebrish-<user>`, uinput device `hebrish-keyboard`, icon and .desktop `hebrish`, udev rule
  `70-hebrish-uinput.rules`, Linux autostart `hebrish.desktop`, Windows Run value `Hebrish`,
  exe `Hebrish.exe`, `HEBRISH_SELFTEST_OUT` in CI.
- The .deb has **no** Conflicts/Replaces/Breaks/Provides for `parlance`. Checked 2026-10-19
  against Parlance-Dictation's `build-deb.sh` (V): it installs `/usr/bin/parlance{,-model}`,
  `/usr/lib/parlance/`, `parlance.desktop`, `parlance.svg`, `70-parlance-uinput.rules` and
  `/usr/share/doc/parlance`; every Hebrish path is named `hebrish`, so none collide. The two udev
  rules are identical and harmless together.
- **First-start import, `config.import_parlance()`** (called first in both `main()`s, before
  the Windows log creates `DATA_DIR`): config.json is copied if Hebrish has none, minus
  `hotkey` and unknown keys; `state.json` and `history.json` are copied and `models/` is
  `copytree`d with `os.link` (falling back to `copy2` per file when linking fails: cross-device,
  or no hardlink support) if Hebrish has no `state.json` and no `models/` yet. Those file
  checks, not "dir absent", because `install.sh` creates `DATA_DIR/venv` first. Parlance's
  dirs are only read, never moved or deleted. `*.part` files and the venv are not copied.
  Sharing inodes is safe because both apps download to `<file>.part` then rename, and prune by
  unlinking a version folder; neither writes into a finished model file. Tests:
  `tests/test_migration.py`. Review for removal at 0.3.0.
- `migrate_legacy()` (voice-to-hebrish / codeswitch-dictation) runs after the import and does
  nothing once a Parlance config was imported.
- Autostart: Hebrish manages only `hebrish.desktop` / the `Hebrish` value. Parlance's entries
  belong to Parlance and are not touched, so a 0.1.x user who had autostart on keeps it for
  Parlance and turns it on in Hebrish separately.
- Hotkey: default F14 (Parlance keeps F13; evdev reads without grabbing, so a shared key starts
  both), and the imported config drops `hotkey`.
- `tests/conftest.py` points `XDG_*`, `APPDATA`, `LOCALAPPDATA` at a temp dir before any test
  module imports `hebrish.config`, and asserts the paths landed there. Before it, the first
  module to import `config` fixed the paths; on 2026-10-19 a run that imported it before
  `test_model_store` set the env wrote into the real `~/.config/hebrish` and the legacy test's
  cleanup deleted the real `~/.config/voice-to-hebrish` and `~/.local/share/voice-to-hebrish`.

## Dictate tab, sounds, voice detection, model folder (0.5.0, 2026-10-21)

Daniel asked (2026-10-21, after using 0.4.0 on Ubuntu) for: insert as you go on by default at
~10 s; the tagline to say who it is for; a Models tab with a download button and an icon per
model, without having to switch model first; spoken status prompts instead of the pips, which
sometimes sounded odd; history off by default; a user-chosen model folder, with the default
shown; recording on the main screen into a text box and only file upload on the second tab; a
voice-detection toggle; the mic in use, with a switcher; a level pane showing clipping and the
good zone; and a byline with a link to danielrosehill.com near the top of About. UI ideas came
from his Voice Notepad app (`AI-Transcription-Notepad`: `tts_announcer.py`, `mic_test_widget.py`).

- **Config upgrade:** `beeps` (bool) became `feedback` (`beeps` | `voice` | `off`). A stored
  config without `feedback` predates 0.5.0, so `config.upgrade()` maps `beeps` to it and sets
  `live_insert_s` 10 (when it was 0) and `keep_history` false, once. That is deliberate: the new
  defaults reach existing installs too (Daniel's request). Tests: `test_upgrade_to_0_5_0_defaults`.
- **Tabs:** Dictate / File / History (only while `keep_history`) / Models / Settings / About;
  `MainWindow.pages` maps names to widgets (`present_tab("model")` etc.). The Dictate tab's text
  box gets every decoded piece through `Signals.piece`. Output `app` (`insert`) skips the
  inserter, so the text goes only there. The File tab (`ui/transcribe.py`) lost its own
  3-hour recorder (`long_recorder`); the take cap (`audio.DICTATION_MAX_S`) went from 15 to 60
  minutes, and `_live_tick` stops a take at the cap (before, the recorder silently stopped
  appending at 15 minutes).
- **Sounds:** `Controller.cue(event)`. Beeps mode cues only `recording` (880 Hz) and
  `transcribing` (620 Hz). Voice mode plays `data/voice/<event>.wav` for every event in
  `audio.VOICE_PROMPTS`, never on success (the text is visible), except `copied` when the output
  is the clipboard. The WAVs are committed, generated by `scripts/make_voice.py` (edge-tts,
  en-GB-RyanNeural, Voice Notepad's voice; needs network once, never at run time). They are in
  `pyproject` package-data; `--selftest` fails if any is missing, so the Windows freeze
  (`--collect-data hebrish`) is checked in CI. (I) Why the 0.4.0 pips sounded odd: not measured.
  The new `audio.beep` adds 25 ms of leading silence (fresh PipeWire/Pulse streams often swallow
  or click the first milliseconds), raised-cosine 12 ms / 45 ms edges instead of 10 ms linear
  fades, 110 ms instead of 70, and a quiet octave.
- **Voice detection** (`vad`, default on; `engine.has_speech`, `engine.shorten_silences`):
  energy-based, no model download. Speech frames: RMS above -46 dBFS and above floor + a third
  of (95th percentile - floor). Under 0.25 s of speech frames, or a 95th percentile under -40
  dBFS: not decoded, `_done` gets `NO_SPEECH` (cue `no_speech`, status line). Silences over
  1.5 s are cut to 0.8 s, above `PAUSE_TARGET_S` and `LIVE_PAUSE_S`, so pause cuts don't change.
  Applied per decode job, so per live piece too, and to File-tab transcripts. Verified
  2026-10-21 (V) off-screen through the real `Controller`: 2 s of hiss → `NO_SPEECH`; two voice
  prompts with 6 s of hiss between → both phrases decoded. (I) Not yet tried with a live mic.
- **Level meter** (`ui/meter.py`): `Recorder` now keeps `rms`, `peak` and `clipped_at` per
  block. Zones in dBFS of block RMS: below -40 too quiet, -40 to -12 good (Voice Notepad's
  guidance, -30 to -12 for speech, widened at the bottom for quiet laptop mics), -12 to -3 loud,
  above red. Clip lamp: a block peak ≥0.98, held 1.5 s. *Test mic* opens `Controller.monitor`
  (a `Recorder(max_s=0)` that keeps no audio), closed before any take starts.
- **Mic in use:** for "System default", `audio.default_input_name()` asks `pactl` on Linux
  (PortAudio on PipeWire sees only a device called "default"); on Windows it is PortAudio's
  default input name.
- **Models tab:** one row per available catalogue model (`_model_row`), rebuilt only when the
  catalogue's ids change. Download → `Controller.download_model(mid)` (fetch the manifest off
  the GUI thread, then the usual `download`); `downloading_id` says which row shows progress.
  Use → `use_model` (only for a downloaded model). Icons: `data/icons/model-<id>.svg`;
  Jachnun's and Sabich's are copies of `Hebrish-Mgmt/brand/logo/{jachnun,sabich}.svg`, stock's
  is a plain hand-drawn wave (not a brand mark).
- **Model folder** (`models_dir`, "" = `config.MODELS_DIR`): `model_store.ROOT` replaces the
  `MODELS_DIR` constant in every path; the app calls `model_store.set_root(config.models_root(cfg))`
  at start, and `hebrish-model` does too. Changing it asks whether to move the downloaded
  models (`shutil.move` per model folder, off the GUI thread, engine unloaded meanwhile);
  "No" leaves them and the app looks only in the new folder. `state.json` keeps version folder
  names, not paths, so it stays valid after a move. The Parlance import and legacy migration
  still write to the default folder (they run on first start, before anyone could choose one).

