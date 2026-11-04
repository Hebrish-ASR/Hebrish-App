**1.018: Let your coding agent read your history, fix recurring errors and update the app.**

- **Agent control (opt-in):** a new switch in Settings → Local API lets coding agents on this computer read and search transcript history, add find-and-replace rules to the personal dictionary, update the app and its models, switch model and start or stop dictation. Off by default; `GET /v1` lists every route.
- **Agent skills:** `update-hebrish`, `read-hebrish-history` and `fix-hebrish-mistranscriptions` ship with the app. Install them for Claude Code, Codex and Gemini CLI from Settings → Local API, or with `hebrish --install-agent-skills`.
- **Try a sample:** test recordings on the Transcribe tab.
- **The send key can stop recording** (opt-in), and question marks, exclamation marks and spaces join better between live pieces.
- **Better audio import:** files opened without ffmpeg are resampled to 16 kHz properly.
- **Fixed:** the Dictionary tab could overwrite words written to the dictionary file while the app was open.
- Beta: Ubuntu 26.04 .deb. Downloads: [hebrish.app/download](https://hebrish.app/download).
