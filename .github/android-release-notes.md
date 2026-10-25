**1.003 (draft, not released): the floating mic types instead of pasting, so no more "pasted from your clipboard".**

- On Android 13+ the floating mic now types the transcript at the cursor through its own input connection, the way a keyboard does. The clipboard isn't used, so Android no longer says the app "pasted from your clipboard" after every sentence.
- If a field doesn't accept that, it falls back to pasting, then to rewriting the field, then to holding the text for **Insert**, so the text gets in wherever it can. Android 9-12 paste as before.
- If the notice still appears on Android 13+ after updating, turn the floating mic off and on once in Accessibility settings.
- Not yet tested on a phone. arm64-v8a only. Android 9+. Downloads: [hebrish.app/download](https://hebrish.app/download).
