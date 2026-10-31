**1.015: Saved transcripts get a folder, a title and a proper header; transcripts arrive in one go; Backup.**

- **Transcripts folder:** Save writes straight to a Hebrish folder (default Documents/Hebrish/transcripts), one folder per year, month and day, as Markdown. Never overwrites. The folder is shown under the Transcription tab's text box with Open and Change….
- **Titles (optional):** download the title model (292 MB) in Models → Utilities → Post-processing and each saved transcript gets a short title in its file name and heading. Set the longest title there (60 characters by default).
- **A proper header:** each saved file starts with YAML front matter (title, date, model, audio length), the title as a heading, the date and time under it, and which model transcribed it.
- **Versions, never overwritten:** if you edited the transcript or clean-up changed it, the raw transcription is saved beside it. *Save cleaned copy* runs a clean-up model you choose (S1-mini by Superwhisper or S1-ASR-Cleanup) and saves the result as its own file; the original stays as it was. A small JSON file links the versions.
- **Transcripts arrive in one go:** the Transcription tab shows the finished transcript at once instead of filling it in piece by piece. A "Transcribing…" timer appears only if it takes more than 5 seconds.
- **Next recording:** choose whether a new recording or file adds to the transcript in the box or starts a new one.
- **Your data and Backup:** Settings → Your data shows where your history, transcripts, dictionary and settings are kept. Back up… saves them as one tar.gz or zip file.
- Ubuntu 26.04 .deb. Downloads: [hebrish.app/download](https://hebrish.app/download).
