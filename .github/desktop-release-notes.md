**0.7.3: History is text only, exports to CSV, and records the exact model.**

- **No audio is kept.** The "keep the audio of each take" setting is gone, and audio that earlier versions saved is deleted on the first start. Your transcripts stay.
- **Export to CSV** (History → Export…): timestamp, transcription and model version for every transcript, for a spreadsheet or your own analysis. JSON Lines is still there.
- Each transcript now records exactly which model weights produced it and how it was decoded, so mistakes can be traced to a model version.
- Also in this release (0.7.2): ALL CAPS (Settings → Dictation), and a polish pass: Settings fits the window, clearer model descriptions, smaller fixes.
- Ubuntu 26.04 .deb and a portable Windows zip. Not yet tested on Windows hardware. Downloads: [hebrish.app/download](https://hebrish.app/download).
