**0.2.2: the model downloads from Hebrish's own CDN.**

- The code-switching model (v1.0) now downloads from `cdn.hebrish.app` instead of Hugging Face, so it keeps working while the model repositories on Hugging Face need an access request. An existing v1.0 install is recognised and not downloaded again; the offline fallback points at the CDN too.
- Terms of use on the setup screen: free for personal and non-commercial use; commercial use, including telephony, needs a licence. [hebrish.app/terms](https://hebrish.app/terms).
- arm64-v8a only. Android 9+. Downloads: [hebrish.app/download](https://hebrish.app/download).
