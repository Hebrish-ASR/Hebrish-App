**0.2.1: model download fixed, terms of use, v1.0 results.**

- **Fixes the code-switching model download.** The model's main repository on Hugging Face now needs an access request, so downloads and update checks failed. The app now downloads v1.0 from the open app build ([`Hebrish/…-sherpa-onnx-int8`](https://huggingface.co/Hebrish/Parakeet-TDT-0.6B-v2-English-Hebrew-Codeswitching-sherpa-onnx-int8)). Installed 0.2.0 apps also pick this up on their next update check.
- **Terms of use** in the About tab, and a note before the model download: the Hebrish models are free for personal and non-commercial use; commercial use, including telephony, needs a licence. Full terms: [hebrish.app/terms](https://hebrish.app/terms).
- The About tab shows v1.0's benchmark: 5.1% word error rate on English with Hebrew words (stock Parakeet 11.3%), 73.3% Hebrew-term recall on the public benchmark.
- Ubuntu 26.04 .deb and a portable Windows zip (Windows still untested on real hardware).
