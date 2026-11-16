**1.039: Change Hebrish's settings from a script or an AI agent through the local API.**

- **`GET /v1/app/settings`** lists the settings it can change, with their values and what each does. **`POST /v1/app/settings`** with `{"out_clipboard": false}` (any of them, several at once) changes them. Everything is checked before anything is saved, at least one output stays on, and changes apply from the next take.
- Covers outputs, the paste and send shortcuts, pane and window binding (1.038), Enter after silence, the Enter guard, insert-as-you-go pacing, capitals, sounds and voice detection. Needs *Settings → Local API* with control on.
- Windows and the AppImage stay on 1.026.
