**0.5.0: new name, same app.** *Codeswitch Voice* is now **Voice To Hebrish** (a working title, and a gag).

- The keyboard's name in Android's keyboard list changes to "Voice To Hebrish". The app ID is unchanged, so this installs over 0.4.0 and keeps your downloaded model.
- The code now lives in the [Voice-To-Hebrish](https://github.com/danielrosehill/Voice-To-Hebrish) repo, next to the desktop app.
- arm64-v8a only. Android 9+. Recommended with HeliBoard.
- **Fix:** 1 s of silence is added after each take before decoding. Without it the model could drop the last words, or the whole last sentence, if you stopped right after speaking.
