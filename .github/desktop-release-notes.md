**1.040: Model downloads survive a dropped connection.**

- A download that loses its connection, times out or hits a server error (408, 429, 5xx) no longer fails: it backs off (2 to 30 s) and resumes the same file from where it stopped. It gives up only after 10 minutes without a new byte. The model card shows "connection lost, retrying" meanwhile.
- Covers the speech models, the paragraph model and the clean-up add-on. The desktop port of Android 1.036's fix.
- Promoted to stable: Windows and the AppImage move up from 1.026 and get everything since.
