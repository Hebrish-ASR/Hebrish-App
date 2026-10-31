**1.014: Press Enter after silence, a local transcription API, and no more lost pieces.**

- **Press Enter after silence (optional, off by default):** Settings → Action keys. While Voice Typing with Insert as you go, once text has been typed and you have been quiet for 8 s (2–60 s), Hebrish presses your Send key once, so a message to Claude goes without reaching for Enter.
- **Local API (optional, off by default):** Settings → Local API. Other programs on this computer can send audio files to Hebrish and get the transcript back, from an OpenAI-compatible endpoint on 127.0.0.1:8723. No key, and nothing leaves the computer. For coding agents: the `transcribe-with-hebrish` skill in the Hebrish Claude Code marketplace.
- **Transcription no longer loses pieces:** the model sometimes returned nothing for a whole stretch of a recording or file (about 20 s on one voice note). Such a stretch is now transcribed again in two halves.
- **Clean-up model choice:** S1-mini by Superwhisper (the default) or S1-ASR-Cleanup (experimental), under Models → Utilities → Post-processing.
- **Updates:** What's new has its own page, from a button in the header, with every entry newest first.
- Ubuntu 26.04 .deb. Downloads: [hebrish.app/download](https://hebrish.app/download).
