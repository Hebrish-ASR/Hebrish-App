**0.4.0: action keys, insert as you go, quieter beeps, and more accurate long takes.**

- **Action keys** for a macropad or foot pedals: one key each for Start, Stop, Pause/Resume, Retake and Discard (Settings → Action keys), alongside the toggle and push-to-talk keys.
- **Insert as you go** (Settings → Speed, off by default): long takes are decoded while you talk and the text is inserted every ~10–30 seconds, at a pause, so on a computer without a GPU only the last few seconds are left when you stop. *CPU threads* now defaults to Auto.
- **More accurate long takes.** Takes over ~25 seconds are now split at real pauses. On a test set of six ~50-second takes, the word error rate fell from 16.0% to 1.0%: the old split sometimes cut a sentence in half and lost it.
- **Beeps:** a volume setting, and quiet hours during which they stay silent.
- Settings show a short "Settings saved" toast when a change is applied.
- Ubuntu 26.04 .deb and a portable Windows zip. Downloads: [hebrish.app/download](https://hebrish.app/download).
