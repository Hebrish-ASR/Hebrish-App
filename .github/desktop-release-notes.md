**0.2.0: Voice To Hebrish, now on Windows too.** *Codeswitch Dictation* is now **Voice To Hebrish** (a working title, and a gag).

- **Windows** (new, untested on real hardware): `VoiceToHebrish-v0.2.0-windows-x64.zip`. Unzip it and run `VoiceToHebrish.exe`. It is unsigned, so SmartScreen may warn you.
- **Ubuntu 26.04**: `sudo apt install ./voice-to-hebrish_0.2.0-1_amd64.deb`. It replaces Codeswitch Dictation 0.1.0 and keeps your downloaded model and settings.
- **New Transcribe tab** for long-form work: pick a microphone, then record with a level meter, a timer and pause. Or open or drop an audio file. The transcript fills an editable text box, and you can save it as .txt or .md, or save the recording as WAV.
- **Dictate tab:** a redesigned UI, recent transcripts kept between sessions, and Copy all / Clear history.
- **About tab:** what the model is, how it was trained, and its benchmark numbers.
- The UI moved from GTK to Qt, so the same app runs on Linux and Windows.
