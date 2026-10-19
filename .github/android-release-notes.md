**0.2.1: model download fixed, terms of use.**

- **Fixes the code-switching model download.** The model's main repository on Hugging Face now needs an access request, so downloads and update checks failed. The app now downloads v1.0 from the open app build ([`Hebrish/…-sherpa-onnx-int8`](https://huggingface.co/Hebrish/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching-sherpa-onnx-int8)); the offline fallback is v1.0 too. Installed 0.2.0 apps also pick up the new location on their next update check.
- **Terms of use** on the setup screen, and a note under the download button: the Hebrish models are free for personal and non-commercial use; commercial use, including telephony, needs a licence. Full terms: [hebrish.app/terms](https://hebrish.app/terms).
- arm64-v8a only. Android 9+.
