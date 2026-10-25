**1.003: the floating mic types instead of pasting, plain model descriptions, and a What's new list.**

- On Android 13+ the floating mic now types the transcript at the cursor through its own input connection, the way a keyboard does. The clipboard isn't used, so Android no longer says the app "pasted from your clipboard" after every sentence.
- If a field doesn't accept that, it falls back to pasting, then to rewriting the field, then to holding the text for **Insert**, so the text gets in wherever it can. Android 9-12 paste as before.
- If the notice still appears on Android 13+ after updating, turn the floating mic off and on once in Accessibility settings.
- **Models in plain words:** each model now says what it is built on ("Base model: Parakeet 0.6B v2 by NVIDIA"); the technical detail is under **Technical details**.
- **What's new:** a new screen (from the home screen's More menu, the side menu or About) lists the latest Hebrish updates. It's built into the app, so it works offline.
- **No more `<unk>` in your text:** Sabich v2.0 sometimes wrote `<unk>` at a clause break; the app now removes it. Sabich v2.1, out today, no longer learns it, and the app offers it as a model update.
- Not yet tested on a phone. arm64-v8a only. Android 9+. Downloads: [hebrish.app/download](https://hebrish.app/download).
