# Codeswitch Dictation (Linux)

Desktop dictation for Linux that runs one model only: the English-Hebrew code-switching
fine-tune of Parakeet TDT 0.6B v2,
[`danielrosehill/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching`](https://huggingface.co/danielrosehill/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching).
It runs on the CPU and offline, using sherpa-onnx int8.

English dictation with Hebrew terms written in Latin letters: *"could you send me the latest
arnona bill"*, *"I need a rishayon iski"*.

It is the single-model sibling of
[Parakeet-Type-Ubuntu](https://github.com/danielrosehill/Parakeet-Type-Ubuntu), which offers several models
and needs KDE. The desktop counterpart of the Android
[Codeswitch Voice](https://github.com/danielrosehill/English-Hebrew-Codeswitching-Voice-Keyboard-Android) keyboard.

## What it does

- **Hotkey**: any key on any keyboard or foot pedal. There are three modes:
  - *hybrid* (the default): a tap starts and a second tap stops; holding the key is push-to-talk.
  - *toggle*: tap to start, tap to stop.
  - *hold*: push-to-talk.

  The key is read from `/dev/input`, so it works on any Wayland or X11 desktop.
- **Output**: pastes at the cursor (clipboard plus Ctrl+V sent through uinput, which works
  whatever keyboard layout is active), or clipboard only.
- **System tray**: closing the window leaves the app in the tray. Middle-click the tray icon to start or stop.
- **Model management**:
  - On first run it downloads the weights (~660 MB) and checks their SHA-256.
  - It checks Hugging Face for a newer fine-tune on a schedule (every 24 h by default) or when you click **Check for update**.
  - It installs a new version automatically or after you confirm.
  - Older versions are kept (you can switch back) or deleted once the new one verifies.
- `codeswitch-dictation --toggle` starts or stops the running instance, so a desktop
  shortcut can drive it if the `/dev/input` hotkey is unavailable.

## Install

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1 python3-evdev libportaudio2 wl-clipboard
sudo usermod -aG input $USER     # for the hotkey; log in again afterwards
./install.sh                     # needs uv; re-run to upgrade
```

Then launch **Codeswitch Dictation** from the menu. In the window you can turn on
*Start at login*.

## Files

| Path | What |
| --- | --- |
| `~/.config/codeswitch-dictation/config.json` | Settings (the window edits them too) |
| `~/.local/share/codeswitch-dictation/models/<version>-<sha12>/` | One folder per installed model version |
| `~/.local/share/codeswitch-dictation/state.json` | Active version, time of last update check |

`config.json` keys and their defaults: see `DEFAULTS` in
[`codeswitch_dictation/config.py`](codeswitch_dictation/config.py).

Model CLI: `codeswitch-dictation-model status|check|download [--replace]`.

## License

MIT. The model is CC-BY-4.0.
