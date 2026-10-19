# Parlance: desktop (Linux and Windows)

The desktop app of [Parlance](../README.md): on-device dictation with NVIDIA Parakeet,
stock or one of the fine-tunes, running on your CPU with sherpa-onnx.

**Website for the English-Hebrew code-switching model: [hebrish.app](https://hebrish.app)**: get the Hebrish keyboard for Android and the desktop apps, see the results, and find every model, dataset and demo in one place.

![The Dictate tab on KDE Plasma](../docs/screenshots/linux-dictate.png)

## Two ways to work

**Dictate** (hotkey, anywhere):
- The hotkey can be any key on any keyboard, or a foot pedal. There are three modes:
  - *hybrid* (the default): a tap starts and a second tap stops; holding the key is push-to-talk.
  - *toggle*: tap to start, tap to stop.
  - *hold*: push-to-talk.
- The text is pasted at the cursor: the app puts it on the clipboard and sends Ctrl+V, so
  it works whatever keyboard layout is active, Hebrew included. Clipboard-only is an option.
- Recent transcripts are listed with Copy buttons, plus **Copy all** and **Clear history**.
- `parlance --toggle` starts or stops the running app, for a desktop shortcut.

**Transcribe** (long form):
- Pick the microphone, then record with a level meter, a timer and Pause/Resume. Recordings can run up to 3 hours.
- Or open an audio file, or drop one on the tab. With ffmpeg installed it reads any format; without it, WAV, FLAC, OGG and MP3.
- The transcript fills an editable text box piece by piece, about one paragraph per 30 s, split at a pause.
- New transcripts are added at the end of the text.
- Copy the text, save it as .txt or .md, or save the recording as WAV.

**Also included:**
- **Tray icon:** closing the window leaves the app in the tray. Middle-click the tray icon to start or stop dictation.
- **Model choice** (Model tab): stock Parakeet, or the English-Hebrew code-switching
  fine-tune. The technical and personal-voice fine-tunes are listed as *coming soon* and
  appear by themselves once published (the app re-reads the catalogue from this repo).
  - Each model (~630 MB) downloads once, on request, with its SHA-256 checked.
  - Models you've downloaded stay on disk, so switching back is instant; *Delete the other
    models* frees the space.
  - It checks the selected model for new versions on a schedule, and installs them
    automatically or after you confirm. It can keep previous versions so you can switch back.
- **About tab:** the models, and the code-switching model's training data and benchmarks.
- **Hebrish links:** [hebrish.app](https://hebrish.app), the code-switching model's website,
  email to feedback@hebrish.app (report a bug, request a feature, send feedback; your mail
  client opens with the app and OS version filled in), and the site's contact form (suggest a
  word, send voice samples, get involved). In
  the tray's **Hebrish** submenu, on the About tab, and under the code-switching model on the
  Model tab.

## Install

**Ubuntu 26.04** (amd64): download the .deb from the
[releases](https://github.com/Hebrish-ASR/Hebrish-Dictation/releases), then:

```bash
sudo apt install ./parlance_*_amd64.deb
sudo usermod -aG input $USER     # for the hotkey; log in again afterwards
```

The .deb bundles sherpa-onnx (Ubuntu doesn't ship it) and is pinned to Ubuntu 26.04's
python3 (3.14). It replaces the predecessor apps `voice-to-hebrish`, `codeswitch-dictation`
and `parakeet-dictation` (Parakeet-Type-Ubuntu), so only one dictation app is installed, and
on first start it adopts Voice To Hebrish's settings and downloaded model. On
other Ubuntu releases, run `./install.sh` (a per-user venv; needs uv) or rebuild with
`./build-deb.sh`.

**Windows 10/11** (x64): download the `-windows-x64.zip` from the releases, unzip it, and
run `Parlance.exe`. There is no installer and no admin rights are needed. Turn on
*Start at login* under Settings if you want it in the tray at every login. Windows
SmartScreen may warn you because the build is unsigned.

## Files

| | Linux | Windows |
| --- | --- | --- |
| Settings | `~/.config/parlance/config.json` | `%APPDATA%\Parlance\config.json` |
| Models, history, state | `~/.local/share/parlance/` | `%LOCALAPPDATA%\Parlance\` |
| Log | stderr | `%LOCALAPPDATA%\Parlance\parlance.log` |

`config.json` keys and defaults: `DEFAULTS` in [`parlance/config.py`](parlance/config.py).
Model CLI: `parlance-model list`, `parlance-model use <model>`,
`parlance-model status|check|download [<model>] [--replace]`.

## Development

```bash
# Linux: the distro python, for apt's PySide6 and evdev
uv venv --python /usr/bin/python3 --system-site-packages .venv && uv pip install -e . pytest
.venv/bin/python -m pytest tests
.venv/bin/parlance
```

Windows: `pip install -e ".[windows]"`. The CI build is `.github/workflows/desktop.yml`.
Internals and measured findings: [`docs/maintaining.md`](docs/maintaining.md).
