**1.034: Dictate in Hebrew with a Hebrew-only model, used when your keyboard is in Hebrew.**

- **Hebrew model:** a new download on the Models screen (about 72 MB) that writes in Hebrew letters. It is [Zipformer2 66M by Yakov Kolani](https://huggingface.co/ivrit-ai/zipformer2-66m-streaming-he), trained on [ivrit.ai](https://www.ivrit.ai) data, CC BY 4.0, unchanged (Hebrish fork: [Hebrish/Zipformer2-66M-Streaming-He](https://huggingface.co/Hebrish/Zipformer2-66M-Streaming-He)). Credited on its card and on About.
- **Automatic switching:** with the Hebrew model downloaded, the voice keyboard uses it when the keyboard you came from is set to Hebrew (or the field asks for Hebrew); English stays on your main model.
- **EN / עב button** in the voice keyboard: Auto, English or Hebrew. A "Hebrew (voice)" keyboard option is also listed. The floating mic follows the button. Transcription Mode stays on the main model.
- Not yet tested on a device. arm64-v8a only. Android 9+. Downloads: [hebrish.app/download](https://hebrish.app/download).
