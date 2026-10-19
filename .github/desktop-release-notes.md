**0.2.2: the model downloads from Hebrish's own CDN.**

- The code-switching model (v1.0) now downloads from `cdn.hebrish.app` instead of Hugging Face, so it keeps working while the model repositories on Hugging Face need an access request. An existing v1.0 install is recognised and not downloaded again.
- Downloads resume and every file is checked against its SHA-256, as before.
- Terms of use: free for personal and non-commercial use; commercial use, including telephony, needs a licence. [hebrish.app/terms](https://hebrish.app/terms).
- Ubuntu 26.04 .deb and a portable Windows zip (Windows still untested on real hardware). Downloads: [hebrish.app/download](https://hebrish.app/download).
