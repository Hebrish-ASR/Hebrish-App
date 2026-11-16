**1.036: Dictate in Hebrew with a Hebrew-only model, used when your keyboard layout is Hebrew.**

- **Hebrew model:** a new download on the Models tab (about 72 MB) that writes in Hebrew letters. It is [Zipformer2 66M by Yakov Kolani](https://huggingface.co/ivrit-ai/zipformer2-66m-streaming-he), trained on [ivrit.ai](https://www.ivrit.ai) data, CC BY 4.0, unchanged (Hebrish fork: [Hebrish/Zipformer2-66M-Streaming-He](https://huggingface.co/Hebrish/Zipformer2-66M-Streaming-He)). Credited on its card and on About.
- **Automatic switching:** with the Hebrew model downloaded, Voice Typing uses it when your keyboard layout is Hebrew (KDE, GNOME, X11 and Windows); English stays on your main model. Auto / EN / עב buttons under the record button and in Settings choose by hand. Transcription mode stays on the main model.
- **Local API:** `language: "he"` on transcription requests, and `GET`/`POST /v1/app/language`.
- Windows and the AppImage stay on 1.026.
