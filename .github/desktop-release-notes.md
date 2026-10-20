**0.3.0: two hotkeys, a floating overlay, and a more finished look.**

- **Two hotkeys.** A toggle key (tap to start, tap to stop; holding it is push-to-talk too, unless you turn that off) and a separate push-to-talk key. Either can be any key or a foot pedal, and either can be left unset. Your 0.2.x hotkey and mode carry over.
- **Floating overlay** (optional, like the Android floating mic): a small bar over every app with the timer, a level meter, Pause/Resume, Retake and Discard, then "Transcribing…" and "Inserted". Show it while dictating or always; drag it anywhere. It never takes the keyboard focus, so the text still goes where your cursor is. Turn it on in Settings or from the tray.
- **Start-up screen** while the model loads, and a redesigned **About** tab.
- **Wayland:** the .deb now pulls in the Qt Wayland plugin, so the window is native on GNOME and KDE. On GNOME the clipboard is set through XWayland (xclip), because GNOME doesn't let a background app set the Wayland clipboard. Raising the window from a second launch works on Wayland.
- Ubuntu 26.04 .deb and a portable Windows zip. Downloads: [hebrish.app/download](https://hebrish.app/download).
