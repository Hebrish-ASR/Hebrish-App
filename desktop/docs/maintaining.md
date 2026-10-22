# Maintaining

Written 2026-10-18. (V) = verified on daniellaptop (KDE Plasma Wayland, Python 3.14.4,
sherpa-onnx 1.13.8); (I) = inferred / not yet tested.

## Layout

| Module | Role |
| --- | --- |
| `model_store.py` | HF check, download/verify, installed versions. No Qt import, so it is testable and also a CLI |
| `app_update.py` | newer-app check against `latest.json`, how this copy updates (apt / deb-manual / windows / source), the pkexec apt upgrade, relaunch (0.6.2; "App updates in the app") |
| `engine.py` | sherpa-onnx `OfflineRecognizer` (nemo_transducer) or, for Shakshuka, `OnlineRecognizer` (0.7.0): normalise, cut at pauses (`live_cut`, `split_points`), pad, `transcribe_chunks` generator; `LiveStream` for streaming takes |
| `audio.py` | sounddevice capture (pause/resume, level meter, `peek`/`consume` for live insertion), file decoding (ffmpeg, else soundfile), WAV save, beeps |
| `hotkey.py` | the shared state machine for the two keys (toggle, push-to-talk) and the action keys, on evdev-style key names |
| `hotkey_evdev.py` / `hotkey_win.py` | per-OS key sources: `/dev/input` on Linux, a pynput low-level hook on Windows |
| `inserter.py` + `inserter_linux.py` / `inserter_win.py` | clipboard, then a paste chord (uinput / SendInput) |
| `autostart.py` | XDG autostart entry / HKCU `Run` key, toggled from Settings → System or the tray's *Start at login* (both go through `Controller.set_autostart`). `refresh()` rewrites the stored command at every start, because it is the path at the time it was turned on: a portable Windows zip unzipped to a new folder for a new version left the Run key starting the old exe (I, from the code; not seen on Windows hardware). Checkable tray actions connect `triggered` themselves: PySide's `addAction(text, slot)` calls the slot with no `checked` argument, so up to 0.6.3 the tray's *Show overlay* raised `TypeError` and did nothing (V, off-screen, 2026-10-21) |
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
- **Live insertion** (`live_insert_s`, 0 = off; 10 by default from 0.5.0, 7 from 0.7.0): a 500 ms timer while recording
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
- **Inference speed review (V, 2026-10-21, Sabich v1.0, sherpa-onnx 1.13.8, Ryzen 7 5700U).**
  Nothing changed; recorded so it isn't re-measured. (1) `decode_stream` releases the GIL:
  a Python thread ticking every 5 ms during a 20 s decode saw at most a 24 ms gap, so a
  live-insertion decode doesn't starve the sounddevice callback. (2) Batching pieces with
  `decode_streams` is no faster and changes output (six 7–10 s clips: 4 threads 3.65 s
  sequential vs 5.02 s batched, 8 threads 4.66 vs 4.30; 1 of 6 transcripts differed, from the
  padding). Keep one piece at a time. (3) Threads on 48 s of speech, min of 3: 2 → 7.22 s,
  4 → 4.91, 6 → 4.69, 8 → 4.43, which confirms the auto default (`config.threads`). Single
  runs vary by ±0.5 s, so compare minima of several runs.
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

1. Write `../.github/desktop-release-notes.md` (first line `**<ver>: …**`).
2. `scripts/release-tag.sh desktop <ver> --push` (repo root). It sets `__version__`, commits
   only that file and the notes, makes the annotated tag `desktop-v<ver>` and pushes both.
   **The tag is the version's source of truth** (Daniel, 2026-10-21: "using tags to have
   consistent versioning"): the script refuses a version that isn't newer than the last tag,
   and CI's first step, "Tag matches version", fails a tag that differs from `__version__`; the
   Windows job `needs` it, so a mismatched tag never produces a release. Don't tag by hand.
   (Tags need `-a`: plain `git tag` fails here with "no tag message?" because of the git
   config, seen 2026-10-21.) CI (`.github/workflows/desktop.yml`) then runs the tests on
   Linux and Windows (Linux CI has no PySide6: a test importing `hebrish.ui` must
   `pytest.importorskip("PySide6")`, or the tag fails, as 0.7.1's first tag did on 2026-10-22;
   that tag was deleted and re-made, since nothing had been released from it), builds the
   Windows zip with PyInstaller, runs the frozen exe's
   `--selftest`, and creates the release with the zip attached.
3. On Ubuntu 26.04, run `./build-deb.sh`. It writes `dist/hebrish_<ver>-1_amd64.deb`,
   bundles sherpa-onnx + sherpa-onnx-core, and is pinned to the build machine's python3
   minor (3.14). Then run `gh release upload desktop-v<ver> dist/*.deb`. CI can't build it
   because the GitHub runners' Ubuntu has an older python3.
4. Publish the .deb to the APT repository: `scripts/publish-apt.sh dist/hebrish_<ver>-1_amd64.deb`
   (see "APT repository" below). Do it after the CDN upload and `latest.json`, so the in-app
   update notice never points at a version apt can't yet fetch.
5. Screenshots: `.venv/bin/python scripts/screenshots.py`, then upload them (see
   "Screenshots and the AppStream listing").

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

## Version footer and screenshots (0.6.3, 2026-10-21)

- **Footer**: the main window's bottom row is the status text on the left and
  `Hebrish <__version__>` on the right in brand blue, linking to hebrish.app/changelog
  (`MainWindow.version_label`, style `#footer`, `#version`). Daniel asked for the version to be
  "more prominently displayed at the bottom"; before 0.6.3 it was only on Settings and the splash.

### Screenshots and the AppStream listing

- `scripts/screenshots.py` renders Dictate, File, Models, Settings and About **off-screen**
  (`QT_QPA_PLATFORM=offscreen`, `QT_SCALE_FACTOR=2`, 1200x1440) into
  `../docs/screenshots/desktop-*.png`, so nothing appears on the desktop and no real settings
  change: config and data are a temp dir, with `~/.local/share/hebrish/models` symlinked in and
  `state.json`'s `active`/`model` copied. **Run it with `.venv/bin/python`**: system python3 has
  no sherpa-onnx (only the .deb's `/usr/lib/hebrish` does), so the model never loads and the
  script waits forever (V, 2026-10-21). The File tab shows Sabich's real output on public sample
  clip `cdn.hebrish.app/samples/clips/20261015T104852Z_zntv22.wav` ("I need to go to the iriya
  to pay my arnona bill."), never typed text. Careful: `Controller()` runs
  `model_store.prune_all()` on the symlinked real models dir, exactly as the app does at start;
  harmless only because `state.json`'s active versions are copied.
- **AppStream** (`packaging/hebrish.metainfo.xml` → `/usr/share/metainfo/app.hebrish.Dictation.metainfo.xml`):
  what Discover and GNOME Software show for the installed app: summary, description,
  screenshots, links. `build-deb.sh` stamps `<release version=$VERSION>`. Screenshot URLs are
  `https://cdn.hebrish.app/apps/screenshots/desktop-{dictate,file,model,settings}.png`: upload
  each release's files there (R2 key `apps/screenshots/`, `--cache-control "public,
  max-age=3600"`, `image/png`). `appstreamcli validate --no-net` passes (one pedantic note).
  Not done: DEP-11 metadata in the APT repo, which software centres would need to show the
  listing **before** install; today it appears once the package is installed.

## APT repository (2026-10-21)

Ubuntu users get app updates through apt, Discover or GNOME Software instead of reinstalling
the .deb (Daniel, 2026-10-21). Flatpak and Snap were rejected: the app reads `/dev/input`
(hotkeys) and writes `/dev/uinput` (paste), which a sandbox only allows with `--device=all`
plus the `input` group (Flatpak) or classic confinement (Snap), so neither gains anything.

| | |
|---|---|
| URL | `https://cdn.hebrish.app/apt`, suite `stable`, component `main`, `amd64` (R2 bucket `hebrish-cdn`, prefix `apt/`) |
| Signing key | RSA 4096, no expiry, no passphrase, UID `Hebrish APT Repository <info@hebrish.app>` (project identity, no personal name), fingerprint `4745D63577C81400DBB743DFDBD1F5A22CA1B27B` |
| Private key | 1Password "Hebrish APT signing key" (`htiwosgw63aj7hjlsteawbe6ua`), vault "API Keys & Programmatic", field `private_key` (armored); `op` returns it wrapped in quotes, the script strips them |
| Public key | `packaging/apt/hebrish-archive-keyring.{gpg,asc}`, published at `apt/hebrish-archive-keyring.{gpg,asc}` |
| Setup | `packaging/apt/setup.sh`, published at `apt/setup.sh`: `curl -fsSL https://cdn.hebrish.app/apt/setup.sh \| sudo sh` (checks the key fingerprint, writes the sources file, installs) |
| Publish | `scripts/publish-apt.sh <deb>…` (no argument: re-sign what is in the pool) |

- **The package enrols itself (0.6.2+).** `build-deb.sh` ships the keyring at
  `/etc/apt/keyrings/hebrish-archive-keyring.gpg` and `/etc/apt/sources.list.d/hebrish.sources`
  (deb822), **both conffiles**, Chrome-style. So a .deb installed from `/get/ubuntu` gets updates
  too. A user who deletes the sources file keeps it deleted across upgrades (dpkg conffile
  rule); `apt remove` keeps both (the repo stays usable), `apt purge` removes both. The key was
  first planned for `/usr/share/keyrings` and moved before 0.6.2 shipped: there it is an
  ordinary package file, so `apt remove` would delete it while keeping the conffile sources,
  and every later `apt update` would fail on a missing Signed-By file. `setup.sh` and the manual steps on hebrish.app write a
  **byte-identical** file, so installing the package afterwards raises no conffile prompt:
  change all three together (the public `Hebrish-ASR/Hebrish-Agent-Skills` repo copies the
  manual steps too).
- **Pool**: the newest `KEEP=3` versions; older ones are deleted from R2, so apt can roll back
  two versions. Old versions stay on GitHub releases.
- **One suite, `stable`, not per-Ubuntu codenames**: the .deb is pinned to Ubuntu 26.04's
  python3 minor (see Releasing). When a second Ubuntu needs its own build, add per-codename suites
  (`resolute`, …) and point new installs at them; `stable` can stay as resolute's alias.
- **Cache consistency** (R2 behind Cloudflare, indexes cached 60 s): upload order is pool,
  `by-hash/`, `Packages*`, then `Release`/`Release.gpg`/`InRelease`, and Release sets
  `Acquire-By-Hash: yes`, so apt fetches indexes by content hash and a stale or fresh InRelease
  always finds its files. **by-hash needs SHA512 as well as SHA256** (V, 2026-10-21, apt on
  26.04): apt asks for the strongest hash listed first; with only `by-hash/SHA256` it logged
  `Ign:` for Packages and fell back to the plain path. MD5/SHA1 are left out of Release.
- **Testing without root or touching the system's apt** (V, 2026-10-21):
  ```
  T=$(mktemp -d); mkdir -p $T/lists/partial $T/cache/archives/partial
  sed "s|/etc/apt/keyrings/hebrish-archive-keyring.gpg|$PWD/packaging/apt/hebrish-archive-keyring.gpg|" packaging/apt/hebrish.sources > $T/s.sources
  O="-o Dir::State::Lists=$T/lists -o Dir::Cache=$T/cache -o Dir::Etc::sourcelist=$T/s.sources -o Dir::Etc::sourceparts=- -o Debug::NoLocking=1 -o APT::Sandbox::User=$(whoami)"
  apt-get $O update && apt-cache $O policy hebrish && apt-get $O --download-only -y install hebrish
  ```
  A clean run shows `Get:1 … InRelease` and `Get:2 … Packages` with no `Ign:` and no signature
  warning.
- Bootstrapped 2026-10-21 with 0.6.1 (which doesn't enrol itself; 0.6.2 is the first that does).

## Character voices, cue bleed (0.7.0, 2026-10-22)

Daniel asked (2026-10-22) for the Voice prompts in the voices of Herman, Corn and Hilbert (My
Weird Prompts podcast characters, voice clones he owns), and reported that spoken prompts
ended up in the transcript.

- **Packs:** `data/voice/<voice>/<event>.wav`, `audio.VOICES` = herman, corn, hilbert; config
  `voice` (default herman); Settings → Sounds → Voice (enabled only when Feedback is Voice).
  The edge-tts en-GB-RyanNeural set and `scripts/make_voice.py` are gone, so existing Voice users
  hear Herman. 16 kHz mono s16 WAV, 764 KB for all three: kept as WAV because `audio.say` reads
  it with the stdlib `wave` module and the packs are tiny next to a model.
- **Generation:** `scripts/make_voice_characters.py render` (Modal python; Daniel's Modal
  account: deployed app `mwp-recording-app`, function `tts_worker`, Chatterbox) then `pick`
  (desktop venv: transcribes every take with the installed model and keeps the closest).
  Chatterbox invents words on one-word lines: the first single-take run gave "Kept that bit."
  (Copied), "Boom, it was discarded." (Discarded) and three near-silent clips. 4 takes fixed
  Herman and Corn (Corn's Resumed needed 6 more). Hilbert failed on "Copied." and "Discarded."
  even at 10 takes, so he has longer lines (`OVERRIDES`): "Dictation paused.", "Take
  discarded.", "Copied to the clipboard.". Final check (2026-10-22): every clip transcribes to
  its phrase except Hilbert's "Dictation paused." (heard as "Tatian paused.").
- **Bleed fix:** cues play through the speakers while the mic is open (start, retake, resume).
  `Controller.cue()` now returns the playback length (`audio._play` computes it), and
  `Recorder.mute(seconds)` makes `_cb` drop input until then. Applied with `CUE_MARGIN_S` = 0.15
  for output latency. The level meter still moves while muted. Not measured: the real output
  latency on Bluetooth headsets (can be 200 ms+); raise the margin if a prompt's tail still
  shows up. Test: `tests/test_live.py::test_recorder_drops_input_while_a_cue_plays`.

## Shakshuka: streaming dictation (0.7.0, 2026-10-22)

Daniel (2026-10-22): Shakshuka, the Nemotron streaming line, is the default for dictation on the
desktop; Sabich stays the default on Android and the pick for transcribing recordings
(`planning/decisions.md` D-2026-10-22-12). Background and the later "corrections" design:
`research/streaming-revision/`.

- **Engine:** catalogue engine `sherpa_online_transducer` is in `model_store.SUPPORTED_ENGINES`.
  Same four files as the offline engine; `Engine.load(..., streaming=True)` builds an
  `OnlineRecognizer.from_transducer` (no `model_type`; the 560 ms chunk size is in the encoder's
  ONNX metadata, from the export). Weights: CDN manifest `parakeet-shakshuka/latest.json`
  (Shakshuka v1.0, run `r8-nemotron-all`, HF `Hebrish/Shakshuka-sherpa-onnx-int8` @ `2cb192de`).
- **Live path:** with *Insert as you go* on (any preset; the interval is ignored), `_live_tick`
  hands everything recorded since the last tick (500 ms) to the worker, which feeds one
  `LiveStream` per take. `LiveStream.feed` returns only text up to the last space, because the
  result grows in BPE pieces ("ask Av" → "Avi for"); `finish` adds 1 s of silence
  (`TAIL_PAD_S`), calls `input_finished` and returns the rest. Pieces carry their own spaces, so
  the worker pastes them as they are, adding the trailing space only after the last one.
  Off: the whole take is decoded at Stop, as for Parakeet.
- **Append-only, verified (V, 2026-10-22, sherpa-onnx 1.13.8, CPU, 4 threads):** six
  code-switched clips from the demo Space's examples, fed in 100 ms and 500 ms steps: no update
  ever changed text already returned (greedy RNNT only appends). The worker still checks:
  if a result stops starting with what was pasted, it logs a warning and pastes nothing more for
  that text, rather than pasting a contradiction.
- **Speed (V, same machine):** decode RTF 0.19–0.22; a 500 ms feed took at most 245 ms. Driving
  the real `Controller._worker` in real time on a 9 s clip: first paste at 3.1 s ("Reminder,
  ask "), then a paste every ~0.5–1 s, each word about a second after it is spoken (a word goes
  out once the next one starts); the last word 0.6 s after Stop. Load: 3.5 s.
- **No `stretch_pauses` for Shakshuka (V):** padding short pauses (the Parakeet fix in
  *Findings*) changed 3 of 6 clips for the worse on Shakshuka: "Hi, I'm confirming" → "Hi Ann,
  confirming … tomorrow tomorrow", "Reminder, ask Avi for" → "Reminder for", and a lost final
  full stop. Raw and gain-normalised audio decoded identically. So `transcribe_chunks` skips it
  when `engine.streaming`; whole-take text then equals the live text on all six clips.
- **Silence:** 5 s of low noise produced no text, so streaming takes skip the VAD check.
- **Recommendation** (superseded in 0.7.1, D-2026-10-22-18: Sabich is the default again; see
  "Back to Parakeet" below): catalogue `recommended_by_platform` (`linux`, `windows`: `shakshuka`) is
  read by `model_store.recommended_id()` before `recommended` (still `sabich`, which Android and
  0.6.x read). A new desktop install defaults to Shakshuka; an install with a pick, or with a
  model already downloaded, keeps it (`current_id`).
- **Not done yet:** the website chooser note still says Shakshuka is not in the apps (the rules
  must match `Hebrish-App/data/variants.json`, `tests/test_shared.py`); change both at release.
  Android has no streaming engine (backlog B-13); `test_shared` allows that one difference.
  Not measured: Shakshuka's streaming WER on the full test set (ASR-Training `evaluate --stream
  70,6`), and pasting ~2 times a second into every kind of target app.

### Existing installs move to Shakshuka once (0.7.0, 2026-10-22)

Superseded in 0.7.1 (D-2026-10-22-18): those installs are moved back to Sabich once; see "Back to
Parakeet" below.

`recommended_by_platform` only decides for an install with no pick, so on its own it would leave
every existing user (Daniel included, on Sabich) where they were. Daniel, 2026-10-22: Shakshuka for
the typing mode "would make the biggest difference to speed and performance". So
`HebrishApp._streaming_default()` (called from `_first_check`, about 10 s after start, only when a
model is already active) runs once per install, guarded by the state flag
`streaming_default_0_7` in `state.json`:
- current model is already the default, or the default isn't available: set the flag, nothing else;
- Shakshuka already downloaded: `use_model` it, notify, set the flag;
- otherwise `download_model` it in the background (the current model keeps dictating) with
  `switch_after_download = (shakshuka, previous)`; `_downloaded` switches only if the pick is still
  `previous`, so a choice made during the download wins. A failed or cancelled download clears
  the pending switch and leaves the flag unset, so it is retried at the next start.
Never repeated after it succeeds: picking another model afterwards sticks. The File tab uses the
same model; a separate model per mode is I-5. Tests pass; not run interactively (I).

### Back to Parakeet; Shakshuka pastes by phrase (0.7.1, 2026-10-22)

Daniel, the same day, after dictating with 0.7.0 (D-2026-10-22-18, R-2026-10-22-37): Shakshuka was
"very jarring": text came two or three words at a time, the screen flickered on every paste, and
when he paused for thought the last words didn't come out. Parakeet did better for dictation.

- **Why the pause held words (V, from the code):** 0.7.0's `LiveStream._release` sent only text
  up to the last space, because the result grows in BPE pieces. The last word therefore waited
  for the next word to start, and during a pause nothing new arrived to release it.
- **Default:** catalogue `recommended_by_platform` is `sabich` again (copy in
  `hebrish/data/catalogue.json`). `Controller._parakeet_default()` replaces
  `_streaming_default()`: once (state flag `parakeet_default_0_7_1`), an install with 0.7.0's
  flag `streaming_default_0_7` that dictates with a streaming model is moved to the recommended
  model, downloading it in the background first if needed (same `switch_after_download` path).
  0.7.0 didn't record whether Shakshuka was its switch or the user's own pick, so both move; the
  notification says it stays downloaded. Installs that never ran 0.7.0 are left alone.
- **Release rule (`engine.STREAM_RELEASE`, config `stream_release`, default `phrase`):** because the
  result only appends, any prefix can be released and the next release continues it exactly, even
  mid-word. The first version of the rule (`, ; : . ? !`, 1.0 s pause, 4 s cap) was retuned before
  release: see "Insert-as-you-go pacing (0.7.1)" below.
- **Flicker:** fewer pastes should mean less of it, but the cause of the flicker itself isn't
  established (the clipboard tool, the compositor or the target app repainting). Not measured.
- **Parked:** a model per mode (I-5, R-2026-10-22-38).

### Insert-as-you-go pacing (0.7.1, 2026-10-22)

Daniel, the same evening (R-2026-10-22-39): with both models, insert as you go dumped text at the
wrong rhythm. Sabich's pieces took "a bit too long" and "the insertion breaks don't really make a
lot of sense"; word-by-word "is very jarring", and too long a wait leaves you "wondering if it's
actually working". Shakshuka needed the same tuning. Both are front-end only (no model change).

**Method (V).** `scripts/pace_sim.py` joins the six demo clips (131 reference words) with gaps of
quiet noise, "thinking" (0.5, 1.4, 0.4, 2.5, 0.7 s) and "flowing" (0.4-0.5 s), and plays them in
0.5 s ticks through the real cut and release code, Sabich v2.0 and Shakshuka v2.0 int8, 6
threads, on the laptop used for the other measurements here. Each clip also has ~0.5-1 s of
silence at its ends, so the real gaps are longer than the nominal ones.

**What was wrong, Sabich (V).** (1) A piece always ended with a full stop and the next started
with a capital, because each piece is decoded alone: a cut at the comma pause of "after the kids
are asleep, so nothing else is running" pasted "…asleep. So nothing else…", and "…all morning.
since my son…". These are the breaks that "don't make sense". (2) No cut before `interval` s of
audio (7 s at Normal), however long you paused, so a short sentence followed by a pause to think
stayed unpasted until you had said several more seconds.

**What was wrong, Shakshuka 0.7.1 draft (V).** Pastes swung from 1 word ("Reminder, ", "Hi, ") to
19, the 4 s cap released mid-word ("the pargit" / " for the…"), and every sentence end was
followed by a paste of a lone space.

**Changes.**
- `engine.live_split` (replaces the body of `live_cut`, which now wraps it) also returns the length
  of the pause it cut at. A pause of `LIVE_BREAK_S` = 1.0 s or more cuts at once, whatever the
  interval, once the take holds `LIVE_MIN_S` = 2 s and some speech (`has_speech` before the cut,
  and the quiet run must not start the buffer). Pauses of 0.6-1.0 s still wait for the interval.
  `split_points` (whole takes, File tab) is unchanged: it never calls with less than the interval.
- **Held full stop:** `engine.hold_stop` holds back the final `.` (and the space after it) of a
  live piece cut at a pause under 1.0 s. When the next piece arrives, `after_held_stop` joins it:
  if it starts lowercase (the model already heard a continuation) or with a word in `CONTINUES`
  (and, so, because, which, to, of, …; not "the", "it", "I", which often start sentences), the
  sentence goes on, lowercased: "asleep so nothing else". Otherwise ". " goes in front, exactly as
  before. At Stop with nothing more, the held "." is pasted. History gets the same joined text
  (`parts`). Worker tests: `tests/test_live.py::test_worker_*`.
- **Presets** shorter: Fast 3, Normal 5 (default), Relaxed 8 s (were 5, 7, 10). `config.upgrade`
  moves a stored 5, 7 or 10 to the new value of the same preset once (configs without
  `stream_release`, the 0.7.1 key); custom values stay.
- **Shakshuka `phrase`** is now (sentence marks `.?!`, clause marks `,;:`, at least 4 words before a
  clause mark, 0.8 s pause, 2.5 s cap). A sentence end goes out at once; a clause mark only once
  it makes 4 words; at a pause everything; at the cap whole words, keeping the last two back so a
  sentence's last word doesn't follow on its own. Releases end on a word or mark, never on a
  space, so each later one starts with its space and no lone space is pasted. `sentence`: `.?!`
  only, 1.2 s, 6 s. `word`: unchanged. Settings has a "Shakshuka pastes" choice now.
- The Dictate tab's text box no longer adds a space before a piece that starts with a space or a
  mark (`_append_piece`), so streaming pieces and held full stops read right there too.

**Results (V, the harness; "thinking" gaps).**

| | Before | After |
| --- | --- | --- |
| Sabich, Normal | 7 s preset; 9 non-empty pieces, 1 error / 131; 3 seams pasted as ". Capital" mid-sentence | 5 s preset; 9 pieces, 1 / 131; mid-sentence seams joined ("asleep so nothing", "Yehuda and it", "morning since my son"); real sentence ends kept |
| Shakshuka `phrase` | 21 pastes of 0-19 words (3 lone spaces), first at 3.0 s | 19 pastes of 2-11 words, every ~2-2.5 s while speaking, sentence ends at once; first at 4.5 s |
| Shakshuka `word` (0.7.0) | 62 pastes of 1-4 words | unchanged |

Sabich errors were the same at intervals 3, 4, 5 and 7 (1-2 / 131, the extra one a different
word each time), so the shorter presets cost nothing measurable here. These clips have no pauses
inside sentences longer than ~0.5 s, so the interval rarely decides a cut in them; real dictation
has more, which is where the held full stop matters most. **Not yet tried in real dictation (I).**
Known limits: a sentence that really ends at a short pause and whose next sentence starts with a
`CONTINUES` word ("So…", "And…") is joined into one sentence; a mid-sentence pause of 1 s or more
still gives ". Capital" unless the next word is in `CONTINUES`.

## ALL CAPS, and the 0.7.2 polish pass (2026-10-22)

**ALL CAPS** (Daniel, 2026-10-22, R-2026-10-22-40, B-34: "just for fun"): config `all_caps`,
Settings → Dictation, "Dictate in ALL CAPS". `Controller._worker` reads it once per take into `out`
(`str` or `str.upper`) and applies it only to what is pasted (`inserter.insert`) and shown
(`sig.piece`), after the seam and release rules, which need the real case (a capitalised first word
decides `after_held_stop`). History keeps the normal case: it can become training data (Correct,
`keep_audio`), and capitals would teach the wrong case. The File tab ignores it. Android has the same
setting (`core` `OutputStyle`, applied in `TakeDecoder`, which is shared by every output path there,
so on Android the stored last transcript is in capitals). Test:
`tests/test_live.py::test_worker_all_caps_keeps_the_seams`.

**Polish pass** (R-2026-10-22-41): a read-only review of both apps the same evening, fixes applied
where they were safe without a device. Desktop: catalogue text no longer says Shakshuka is the
pick for dictation (shared with Android; installed apps re-fetch it), the chooser rules match the
website again (`test_shared`), Settings never scrolls sideways (horizontal bar off, shorter labels,
details in tooltips), About's privacy text names no model, JSON files are read and written as UTF-8
(Windows code page), the start-at-login command quotes the path, assorted stale strings. Left for
later (need a decision or Windows hardware): Windows ignores neither its own Ctrl+V nor Parlance's
when the hotkey is a modifier (pynput >= 1.8 `injected` flag), MB vs MiB on the Models tab, About's
Jachnun-only benchmark section, letter hotkeys under the Hebrew layout on Windows, a locked Windows
clipboard silently dropping a piece.

## Dictation history: SQLite, search, word counts (0.7.0, 2026-10-22)

**Schema 2 (0.7.3, 2026-10-22, R-2026-10-22-43, B-36):** each row also records `model_rev`, the exact
weights (the active version's manifest `revision`, the Hugging Face commit its files came from), and
`decode`, a JSON object: `app` version, `engine`, `device`, `threads`, `vad`, `all_caps`, and for
dictation `live_insert_s` and (streaming) `stream_release`. Daniel wants to see, as model versions
iterate, which words keep being mistranscribed; the label alone ("sabich Sabich v2.0") can't tell two
builds of one version apart, and the app's cut and release rules change between app versions.
`History._migrate` adds both columns to a schema-1 database once (`ALTER TABLE`; older rows stay
NULL). History export includes them. Consumer: Daniel's private `dictation-history-dataset` skill
(`mine_history.py versions`). Tests: `tests/test_history.py::test_rows_record_the_exact_weights_and_decode`,
`::test_schema_1_database_gains_the_columns_once`.

Daniel, 2026-10-22 (D-2026-10-22-13, R-2026-10-22-13/14/15): the Dictate tab's text box collected
every take into one blob; history was the last 50 transcripts in `history.json`, off by default.
Now:

- **Text box clears per take** (`clear_each_take`, default on): `Controller.start()` calls
  `MainWindow.new_take()` before recording, so the last result stays visible until the next take.
- **Every transcript is kept** (`keep_history`, default on again) in `DATA_DIR/history.db`
  (`hebrish/history.py`): table `dictations` (`uid`, `at`, `text`, `words`, `seconds`, `model`,
  `source` dictate|file|import, `audio`, `original`), an FTS5 index `dictations_fts` kept in step
  by triggers, and `meta` (`schema`, a random `device` id, `created`). `uid` and `device` exist
  so rows can later be merged across devices or backed up without collisions (Drive backup,
  accounts: backlog). The 0.6.x `history.json` is imported once, then renamed
  `history.json.imported`. Configs saved before 0.7.0 (no `clear_each_take`) get
  `keep_history` on once: since 0.5.0 their `false` was the forced default.
- **Search** is FTS5 keyword search: every word must match, each as a prefix, ranked by bm25,
  with matches bolded from `snippet()`. Not semantic: that is a backlog item, because it needs a
  text-embedding model the app doesn't ship (sherpa-onnx has none, and the .deb bundles no
  Python onnxruntime).
- **Word counts**: today, the last 7 days (today included) and all time, from local midnight
  (`History.stats`), with audio minutes and days active.
- **Audio** (`keep_audio`, default off): the decode worker keeps each live piece's samples and
  passes the whole take with `transcribed`; `history-audio/<uid>.wav`, 16 kHz mono int16, about
  1.9 MB a minute. **Correct** in the History tab stores the edited text and keeps the model's
  text in `original` (first edit only), so (audio, original, corrected) triples can become
  training data.
- File-tab transcripts go in too (`source` file, no audio: the file is the audio).
- The History tab shows the database path and size, with Open folder and Export (JSON Lines).
- Rows are hidden before `deleteLater()` when the list refreshes: off-screen renders (and any
  refresh without a trip through the event loop) otherwise painted old rows under new ones.

Verified 2026-10-22: `tests/test_history.py`, and an off-screen render with sample rows (search,
counts, a simulated take with audio). **Not yet verified:** a real take on the installed app,
and query speed on a database of tens of thousands of rows (FTS5 should be fine; untested).

## Insert-as-you-go presets, Stop and send (0.7.0, 2026-10-22)

Daniel asked (2026-10-22) for text to arrive sooner during a take, and for a way to submit a
chat box (his case: Claude Code) without losing the words still being transcribed when he hits
Enter. Decisions: `planning/decisions.md` in this repo.

- **Presets:** `live_insert_s` stays a number of seconds. Settings shows `ui/window.py` `LIVE`:
  Off 0, Fast 5, Normal 7 (default; the old 10 cut by a third), Relaxed 10, and Custom (data
  `-1`, which reveals a 3–60 s spin box). Any stored value that is not a preset (15, 20 and 30
  were the old choices) shows as Custom with that value, so nothing is lost.
- **Migration:** `config.upgrade()` moves a stored 10 to 7 once, only for configs without
  `send_chord` (that key is the 0.7.0 marker). Up to 0.6.3 10 was the default and every config is
  saved whole, so a 10 says nothing about a choice. A 10 picked from Relaxed after 0.7.0 stays.
- **`live_cut` at 5 s** needs no constant changes: it searches the last `LIVE_SEARCH_S` = 6 s, so
  at 5 s the whole take is searched; the 0.6 s pause rule still applies. Test:
  `tests/test_live.py::test_cuts_at_fast_interval`. Not measured: how much accuracy Fast costs
  (shorter pieces, less context per decode, more cut points).
- **Stop and send:** action `send` in `hotkey.ACTIONS`, slot `key_send`. `Controller.do_action`
  sets `_send_take = _take` and stops; pressed while the take is already stopped and still
  decoding (`state == "busy"` and `_stopped_at` set), it marks that take. The decode worker, after
  the final piece's paste, calls `_send()`: 150 ms wait, then `inserter.press(send_chord)`. Only
  when output is `paste` and the take produced text (`parts`). `press()` is new on both inserters
  (`LinuxInserter` via uinput, `WindowsInserter` via pynput), split out of `insert()`.
- **Key sources never grab**, so a Stop and send key also reaches the focused app. Don't bind
  it to Enter itself: that Enter would submit at once. Use a spare key or pedal (F13–F24).
- **Not verified on Windows** (no machine; CI tests only). Android has no equivalent yet:
  `planning/backlog.md`.

## App updates in the app (0.6.2, 2026-10-21)

Model updates are `model_store`'s job; `hebrish/app_update.py` (no Qt) is for the app itself.

- **What it checks:** `GET https://cdn.hebrish.app/downloads/latest.json` (the manifest
  hebrish.app's `/get/<os>` follows) and compares `files.ubuntu.version` (Linux) or
  `files.windows.version` with `hebrish.__version__`, numerically (`parse_version`: a leading
  `v`, a Debian revision and a suffix like `rc1` are dropped, trailing zeros ignored, so
  0.10.0 > 0.9.0). The top-level `version` is never used: Android and desktop version
  separately (on 2026-10-21 Android was 0.7.0, desktop 0.6.1).
- **The GET goes through `model_store._get`**, for its `User-Agent`. Cloudflare's bot filter
  answers 403 to urllib's default `Python-urllib/3.x` on cdn.hebrish.app (V, 2026-10-21: plain
  `urllib.request.urlopen` → 403; `app_update.fetch()` → `files.ubuntu.version` 0.6.1).
- **When:** 30 s after start (one GET, off the GUI thread), then whenever the 10-minute
  `_periodic_check` finds `app_last_check` (state.json) a day old. Off: Settings → App updates
  (`app_update_check`, default on). Manual: Settings → App updates → *Check now*, and the tray's
  *Check for app update*.
- **Not nagging:** a strip under the header (`#updateBar`, `MainWindow.show_app_update`), which
  unlike `banner()` never raises the window or switches tab, with one action and *Not now*.
  *Not now* stores `app_dismissed` = that version in state.json: the strip stays hidden until a
  newer version (a manual check shows it anyway). The tray notification comes once per version
  (`app_notified`), and not for a dismissed one.
- **Classification (`install_method()`), in order:**

  | Method | Rule | Offer |
  | --- | --- | --- |
  | `windows` | `sys.platform == "win32"` and `sys.frozen` (PyInstaller) | *Download page* → `hebrish.app/download#windows` |
  | `source` | Windows unfrozen, or Linux where the `hebrish` package isn't under `/usr/lib/hebrish` (a checkout, `install.sh`'s venv) | text only |
  | `apt` | under `/usr/lib/hebrish` and `/etc/apt/sources.list.d/hebrish.sources` exists | *Update now* (pkexec, below) |
  | `deb-manual` | under `/usr/lib/hebrish`, no sources file (0.6.1 and earlier, or the user deleted it) | *Download page* → `#ubuntu`, saying the new .deb adds the repository |

  The sources file is checked, not the key or apt's lists: it is what the .deb ships and what a
  user deletes to opt out. (I) A sources file that exists but is broken (wrong key) classifies
  as `apt`; the pkexec run then fails and the strip shows apt's last error lines plus the
  terminal command.
- **The `apt` update**, one pkexec call (`app_update.APT_SCRIPT`):

  ```
  pkexec sh -c 'apt-get update -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/hebrish.sources -o Dir::Etc::sourceparts=- -o APT::Get::List-Cleanup=0 && DEBIAN_FRONTEND=noninteractive apt-get install -y --only-upgrade -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold hebrish'
  ```

  Noninteractive + confdef/confold: pkexec gives no terminal, so a dpkg conffile question
  (e.g. after the user edited `hebrish.sources`) would otherwise hang the run; the user's file wins.

  Only the Hebrish source is refreshed: it is a 2-file fetch instead of every source on the
  machine, and a broken unrelated third-party source can't fail the update. `--only-upgrade`
  never installs anything new; dependencies resolve against the lists already on disk.
  Verified 2026-10-21 on Ubuntu 26.04, apt 3.2.0, as a normal user (V):
  - `--print-uris update` with those options lists 13 URIs, all on cdn.hebrish.app. The
    relative form `Dir::Etc::sourcelist=sources.list.d/<x>.sources` (resolved against
    `Dir::Etc`) works too; the absolute path is used for clarity.
  - A `.sources` name is parsed as deb822.
  - **`APT::Get::List-Cleanup=0` is required.** In a scratch `Dir::State::Lists`, an `update`
    restricted to the Hebrish source with the default cleanup deleted the Ubuntu `InRelease`
    and a dummy `Packages` file already there. Without the option, the real run would delete
    every other source's lists, and the `install` (and Software Updater) would see only
    Hebrish's packages until the next full `apt update`. With it, both files stayed.
  - In that scratch dir, the restricted `update` fetched `InRelease` + `Packages` from the live
    repo, and `apt-cache policy hebrish` showed candidate 0.6.1-1.
  - **Not run with pkexec or as root (I).** Not verified: the polkit dialog's text, and the full
    upgrade replacing the running app's files. `pkexec` exits 126 when the dialog is dismissed and
    127 when authorisation fails (pkexec(1)); both map to a message and keep the strip, with
    "Try again".
- **After a 0 exit**, `dpkg-query -W -f='${Version}' hebrish` is checked, because
  `apt-get install --only-upgrade` also exits 0 when the repo has nothing newer. That happens
  when latest.json is updated before `publish-apt.sh` runs (hence Releasing step 4's order). It
  then says "The Hebrish repository doesn't offer X yet".
- **Restart:** on success, if no take is in flight, a dialog offers to restart. Otherwise there is
  a notification, and the tray gets *Restart Hebrish to finish updating* (Settings gets a button).
  `Controller.restart()` → `app_update.relaunch()` starts
  `sh -c 'while kill -0 <pid>; do sleep 0.2; done; exec /usr/bin/hebrish'` in its own session,
  then quits. Waiting for the old pid matters: started at once, the new instance would find the
  old single-instance socket still listening, send it `show` and exit. (V, 2026-10-21: the
  wait-then-exec loop, with a dummy pid and command; the real restart after a real upgrade is
  (I).) Until the restart, `app_installed` stops later checks from offering the same version
  again.
- No pkexec (minimal installs): the strip says to run `sudo apt update && sudo apt install
  --only-upgrade hebrish`.
- `--selftest` (the Windows CI build) also prints `latest app:` from `app_update.fetch()`, so
  the frozen build's TLS and User-Agent path to cdn.hebrish.app is exercised.
- Rendered off-screen (V, 2026-10-21) through the real `Controller` with a fake `Release("0.9.0")`:
  the strip for all four methods and the error state, Settings → App updates, dismiss (hidden,
  stays hidden on a re-check of 0.9.0, shown for 0.9.1). Not tried on Windows.
- Tests: `tests/test_app_update.py` (version order, latest.json parsing, classification with
  fake paths, the apt command, the pkexec exit codes, "repo has nothing newer").

## Models

Since 0.6.0 the catalogue is `../shared/catalogue.json` (schema 2: lines and variants; the
protocol is in `../shared/update-protocol.md`, "Catalogue v2"), bundled as
`hebrish/data/catalogue.json` (`tests/test_shared.py` fails if the copies differ). Each update
check first re-fetches it from `catalogue_v2_url` into `~/.local/share/hebrish/catalogue-v2.json`;
an unparseable or wrong-`schema` copy is ignored and the bundled one is used. Up to 0.5.2 it was
`../shared/models.json` (schema 1) from `catalogue_url` into `catalogue.json` (builds up to 0.1.2
use the pre-2026-10-19 repo name `Parlance-Dictation` and depend on GitHub's rename redirect, see
`android/docs/maintaining.md`, "Repo name"); that file and its cache stay for those builds. So **publishing a
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
  `transcribing` (620 Hz). Voice mode plays `data/voice/<event>.wav` (from 0.7.0 `data/voice/<voice>/<event>.wav`, see "Character voices") for every event in
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
  Use → `use_model` (only for a downloaded model). The row in use has no buttons, so it is
  tinted and outlined in brand green with a "✓ In use" chip (2026-10-21: as a plain row it read
  as greyed out next to rows with buttons); the recommended model's "Switch to …" button is
  `primary`, and the card's intro line names the catalogue's `recommended` model. Icons: `data/icons/model-<id>.svg`;
  Jachnun's and Sabich's are copies of `Hebrish-Mgmt/brand/logo/{jachnun,sabich}.svg`, stock's
  is a plain hand-drawn wave (not a brand mark).
- **Model folder** (`models_dir`, "" = `config.MODELS_DIR`): `model_store.ROOT` replaces the
  `MODELS_DIR` constant in every path; the app calls `model_store.set_root(config.models_root(cfg))`
  at start, and `hebrish-model` does too. Changing it asks whether to move the downloaded
  models (`shutil.move` per model folder, off the GUI thread, engine unloaded meanwhile);
  "No" leaves them and the app looks only in the new folder. `state.json` keeps version folder
  names, not paths, so it stays valid after a move. The Parlance import and legacy migration
  still write to the default folder (they run on first start, before anyone could choose one).

### 0.5.0 additions (Daniel, 2026-10-21, same day)

- **Esc discards** a recording take (`escape_discards`, default on) and a **double tap of the
  toggle key is Retake** (`double_tap_retake`, `double_tap_ms` 300). Both in `HotkeyMachine.key`.
  Key sources never grab keys, so Esc also reaches the focused app (said in Settings). A tap that
  would stop a take now arms a `threading.Timer` for `double_tap_ms`; a second press of the toggle
  key before it fires cancels it and fires `action("retake")`, else the timer stops the take.
  Cost: stopping by tap is 0.3 s later (the mic keeps recording meanwhile, so nothing is lost).
  Hold-to-talk release and the PTT key are unchanged. The double tap needs the action callback,
  so a machine without one (the old tests' `Rig`) stops at once as before.
  Tests: `test_double_tap_while_recording_is_retake`, `test_single_tap_stops_after_the_double_tap_window`,
  `test_escape_discards_only_while_recording`.
- **Distinct sounds:** beeps mode plays a falling two-note "doo-doo" (660 then 440 Hz) for
  discard and a rising pair (523, 880) for retake; voice mode says "Discarded" and "Starting
  again" (`retake.wav`). `Controller.start(cue=)` lets retake replace the start cue.
- **Diagnostics tab** (`ui/diagnostics.py`): `Engine.stats` gets one record per decoded piece
  (`audio_s`, which includes the stretched inner pauses but not the tail pad; `decode_s` =
  `create_stream` + `accept_waveform` + `decode_stream`; `tokens` = `len(result.tokens)`);
  `Controller.latencies` has stop → final text. Averages over the last 10/20/50/all are totals over
  totals. Run benchmark decodes the voice prompts joined with 0.5 s gaps three times: the edge-tts set (10.6 s) up to 0.6.3, Herman's set from 0.7.0 (about 6.2 s of speech plus gaps), so timings from before and after 0.7.0 are not comparable.
  Copy as JSON gives summary, system and records. Nothing is saved to disk.

Measured 2026-10-21 (V), Run benchmark off-screen on daniellaptop (AMD Ryzen 7 5700U, 16
logical CPUs, auto = 8 threads), Jachnun v1.0 int8, sherpa-onnx 1.13.8 CPU: 0.74-0.95 s per
10.6 s piece, 12.9× real time, 61 tokens/s, model load 5.35 s, app memory 1361 MB.

**GPU (checked 2026-10-21):** the sherpa-onnx wheel the app uses ships a CPU-only
`libonnxruntime.so`; its binary names providers cpu, cuda, coreml, directml, openvino, tensorrt,
xnnpack, qnn and rknn, and prints "Please compile with -DSHERPA_ONNX_ENABLE_GPU=ON" for GPU
ones. There is no ROCm or MIGraphX provider in sherpa-onnx, so AMD GPUs on Linux are not a
`provider=` switch away: it would take a custom onnxruntime build plus a sherpa-onnx patch.
On Windows, DirectML (any DX12 GPU, AMD included) is a provider sherpa-onnx knows, but needs a
DirectML build of sherpa-onnx in the freeze. GPUs also want fp16/fp32 graphs, not these int8
ones (`Hebrish/Jachnun-ONNX` has fp32). (I) At 13× real time on a mid laptop CPU, a GPU would
save well under a second per take; it matters more on old 2-4 core laptops, which are not
measured yet (the Diagnostics tab is how to find out).

## One model version on disk (0.5.1, 2026-10-21)

Daniel: "I don't think we'll want to hold previous old versions of the model … when there's a
new version … we get that and we delete the older ones in the user storage." So:

- `model_store.download(keep_old=False)` is the default and the app always passes False: the
  previous versions of that model go once the new one's `manifest.json` is written (same
  `prune_except` as before, so other models are never touched).
- `model_store.prune_all()` runs once per start (`Controller.__init__`, after `load_model`) and
  keeps only each model's active version, clearing what 0.5.0 and earlier kept (daniellaptop had
  four Jachnun folders: v1.0, v5 and two v4 on 2026-10-21).
- `auto_update` is on by default. `config.upgrade()` treats a stored `keep_old_versions` as a
  pre-0.5.1 config: drops it and sets `auto_update` true once. The setting stays in Settings →
  Model updates; off means a notification and an Update button on the Models tab.
- Removed: the "Installed versions" card (Use / Delete per version) and the "Keep previous
  versions" checkbox. Rolling back to an older model version is no longer possible from the app;
  older versions stay on the CDN (`models/<model>/<version>/`) and on Hugging Face.
- Tests: `test_one_version_per_model_by_default`, `test_upgrade_drops_keep_old_versions_and_turns_on_auto_update`.


## Two-level model picker and Help me choose (0.6.0, 2026-10-21)

Daniel (2026-10-21): "you choose Sabich, and under Sabich we show the versions available …
with a short recommendation for each … apps show it as a speed–accuracy gradient … add some way
for users to make sense and use the right one."

- `model_store.lines()` / `variants()` give every line and variant; `models()` only the ones this
  build can run (`SUPPORTED_ENGINES = {"sherpa_offline_transducer"}`, `PLATFORM` linux or
  windows). Every download, select, update and folder path still goes through `models()` /
  `get_model()`, so a Qwen3-ASR or asr4all variant can never be selected or fetched (test
  `test_unsupported_engines_are_listed_but_not_models`).
- Models tab (`ui/window.py` `_line_header`, `_model_row`): per line a header (mark, name,
  summary, link, terms), then one row per variant: name and base model, Recommended / In use
  chips, the recommendation sentence, speed and accuracy as five-dot meters marked
  "(estimates)", size, hardware and card link, state, buttons. A variant the app can't run is
  greyed with "Not in this app yet. Runs on: …" and no buttons; a planned one says "Coming soon".
  Rows are rebuilt when the catalogue's (id, available, supported) list changes.
- `current_id()` without a pick: the first downloaded supported model, recommended first, else
  `recommended`. Before 0.6.0 it was schema 1's `default` (`stock`); a user who never picked keeps
  the stock download they have.
- **Help me choose** (`ui/choose.py`, logic in `model_store.recommend`, `vram_bucket`,
  `detect_gpu`): device (this computer, a phone, a wearable), GPU vendor and VRAM, priority, and
  "words while I'm talking". The answer is the catalogue's `chooser.rules`, the same list as
  hebrish.app/models/choose (`../shared/update-protocol.md`, "Catalogue v2"). 0.6.0 ranked by
  weighted tiers instead, which disagreed with the site (no GPU + speed gave the 110M, the site
  Sabich); 0.6.1 uses the rules. When the pick can't run here it is still named with its `how`
  ("Use via llama.cpp: see the model card." for `qwen3_asr`, else `runs_on`), then the best
  variant this app can run, with a Download / Switch button. Intel graphics count as `none`.
- `detect_gpu()`: `nvidia-smi --query-gpu=memory.total` (3 s timeout), else
  `/sys/class/drm/card*/device/{vendor,mem_info_vram_total}` (amdgpu; vendor ids 0x1002 AMD,
  0x10de NVIDIA, 0x8086 Intel). (V, 2026-10-21, daniellaptop) an AMD APU reports its 1 GB
  carve-out there, so it is shown as "AMD, 1 GB" and Qwen is not suggested; correct by hand.
  `rocm-smi` was not used: it is often not installed, and sysfs gives the same number. Windows:
  NVIDIA only (no sysfs); others are entered by hand.
- Rendered off-screen and checked (V, 2026-10-21): the Models tab and the dialog, including
  "AMD, 16 GB, accuracy" → Sabich-Qwen3-ASR-1.7B + "In this app, the best fit is Sabich".
  Not tried on Windows.
- `Engine.load(..., feature_dim)` takes the variant's `feature_dim` (0.6.1; 128 was hard-coded
  before). Sabich-Parakeet-110M (80 mels) checked end to end on 2026-10-21 (V): fetched from its
  CDN manifest, downloaded and verified, loaded, transcribed correctly. Its install folder name
  has spaces (`Sabich-Parakeet-110M v1.0-9bc182a9e1b3`, from the manifest's `version`); harmless.
