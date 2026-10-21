**0.5.0: dictate into the window, spoken prompts, a level meter, model cards, and text as you talk.**

This release also carries 0.4.0, which was never published on its own.

- **Text appears as you talk.** Insert as you go is on by default: long takes are decoded at pauses while you speak, every ~10 seconds, so only the last few seconds are left when you stop. Long takes are split at real pauses, which cut the word error rate on ~50-second test takes from 16.0% to 1.0%.
- **The Dictate tab records into a text box.** Press Talk (or your hotkey) and the text lands in an editable box, as well as at your cursor. Output can be the cursor, the clipboard, or the text box only.
- **Microphone pane:** the mic in use (including which device "System default" is), a switcher, a level meter showing too quiet, good and loud zones and a clip lamp, and Test mic.
- **Voice detection** (on by default): a take with no speech isn't transcribed, so no stray "Yeah.", and long silences are shortened.
- **Sounds:** softer beeps, or short spoken prompts ("Recording", "Paused", "Transcribing", "Discarded", "Starting again"), or off. A volume setting and quiet hours.
- **Keys:** Esc discards a take; double-tap the toggle key to start again. One key per action for a macropad or pedals (Start, Stop, Pause, Retake, Discard).
- **Models tab:** a card per model with its own Download, Use and Delete, so you can download Jachnun, Sabich or stock Parakeet without switching. Choose the folder the models are stored in.
- **File tab:** drop an audio file to transcribe it.
- **Diagnostics tab:** inference speed on your computer (tokens per second, × real time, wait after you stop), with a benchmark button.
- History is now optional and off by default. Your existing settings get the new defaults once.
- Ubuntu 26.04 .deb and a portable Windows zip. Not yet tested on Windows hardware. Downloads: [hebrish.app/download](https://hebrish.app/download).
