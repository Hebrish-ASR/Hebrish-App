**1.037: Dictation goes where you started it, even if you move to another terminal pane or window while it transcribes.**

- **Konsole panes:** a take remembers the Konsole pane it started in, and its text and Enter go there, even after you click into another pane. With Konsole's *Settings → Configure Konsole → General → "Enable the security sensitive parts of the DBus API"* on, the text goes straight into that pane without the clipboard or a paste shortcut. Without it, Hebrish switches back to that pane and pastes, and says once how to turn the setting on.
- **Other windows (KDE Plasma):** if you move to another window while a take is transcribing, Hebrish brings the window it started in back to the front before it pastes.
- On by default; `bind_pane` and `bind_window` in the config turn each off.
- Windows and the AppImage stay on 1.026.
