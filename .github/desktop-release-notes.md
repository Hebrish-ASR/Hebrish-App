**1.048: fewer invented phrases from silence and breaths (first Windows and AppImage release since 1.041).**

- A take with no speech in it (left recording, or only a breath), or the very first moment of a take, could come back as a phrase nobody said. Hebrish now remembers how loud you usually speak into each microphone, and skips a piece that is far quieter than that and holds almost no speech. It learns the level from your first few dictations on a new mic, so nothing changes until then.
- 1.048 is 1.047 with a test fixed so the Windows build could run. Also since 1.045: a breath or murmur before you speak, between sentences or after your last word is no longer transcribed by itself (1.046); model downloads are written safely to disk, and a damaged model is downloaded again instead of failing to load; on Linux, Hebrish recovers display settings missing after autostart.
- Windows: Hebrish is in the [Microsoft Store](https://apps.microsoft.com/detail/9n2tv8hpq6lh).
