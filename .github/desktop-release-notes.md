**1.041: Windows gets an installer that keeps Hebrish up to date.**

- **Windows installer** (`HebrishDictation-stable-Setup.exe`, Velopack): per-user, no admin rights, Start menu and desktop shortcuts, an uninstaller. Installed this way Hebrish updates itself: new versions download in the background and install at the next start, or at once from *Restart Hebrish to finish updating*. Unsigned, so SmartScreen may warn on first install.
- Model downloads survive a dropped connection (1.040): retry with backoff and resume from the partial file.
- Stable on every desktop platform: Windows and the AppImage move up from 1.026. The portable zip is still attached for those who want it.
