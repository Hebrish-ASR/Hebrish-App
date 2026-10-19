**0.1.0: first release of Parlance for Android.**

- A voice keyboard (IME) running NVIDIA Parakeet TDT 0.6B v2 on the phone, through sherpa-onnx (int8).
- **Choose the model**: stock Parakeet, or the English-Hebrew code-switching fine-tune. A technical-vocabulary model and a personal general-English model are listed as coming soon; they appear in the app when they are published, without an app update.
- Each model is a separate ~660 MB download from Hugging Face, kept until you delete it. Updates to a model are offered only when its weights change.
- **Try it**: a notepad with a mic button, so you can test a model before setting up the keyboard.
- New app ID (`com.danielrosehill.parlance`), so it installs alongside Voice To Hebrish, which it replaces. Uninstall that one once this works.
- arm64-v8a only. Android 9+. Recommended with HeliBoard.
