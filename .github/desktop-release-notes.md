**1.042: Web pages you choose can start and stop dictation, and the local API covers the rest of the app.**

- **Web pages allowed** (Settings → Local API, empty by default): list a web page's origin, e.g. `https://label.example.com`, and that page may check `GET /health` (now with `state`: idle, recording or busy) and start or stop dictation with `POST /v1/app/dictation` (with the control switch on), so it can have its own mic button. It gets nothing else: history, the dictionary and settings still refuse web pages, as does every unlisted site. Config key `local_api_web_origins`.
- **Local API control**: every dictation action key (pause, resume, retake, discard, send, paste last), correcting and deleting transcripts, choosing the dictation and Transcription Mode microphones, model download progress and removal, Transcription Mode on a file, and a live stream of changes (`GET /v1/app/events`). `GET /v1` lists every route.
- **Gefilte PoC** as a second Hebrew model, with *Use for Hebrew* to pick which downloaded Hebrew model Hebrew takes use.
- New installs dictate English by default (was Follow keyboard); saved settings keep their value. Sabich stays the recommended model.
- Ubuntu beta (the .deb and the APT repository); Windows and the AppImage stay on 1.041 until a stable promotion. Downloads: [hebrish.app/download](https://hebrish.app/download).
