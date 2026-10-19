**Parlance 0.1.0 for desktop: the first release.** Parlance succeeds Voice To Hebrish and Parakeet-Type-Ubuntu.

- **Choice of model:** stock NVIDIA Parakeet TDT 0.6B v2, or the English-Hebrew code-switching fine-tune. Technical-vocabulary and personal-voice fine-tunes are listed as coming soon and will appear without an app update once published.
- **Ubuntu 26.04**: `sudo apt install ./parlance_0.1.0-1_amd64.deb`. It replaces Voice To Hebrish and Parakeet-Type-Ubuntu, and keeps Voice To Hebrish's settings and downloaded model.
- **Windows** (untested on real hardware): `Parlance-v0.1.0-windows-x64.zip`. Unzip it and run `Parlance.exe`. It is unsigned, so SmartScreen may warn you.
- Everything else carries over: hotkey dictation (hybrid, toggle or hold), the Transcribe tab for recordings and files, the tray icon, and model updates with SHA-256 checks.
