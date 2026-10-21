**0.6.1: choose a model by family and version, with Help me choose.** (0.6.1 makes Help me choose give the same answers as [hebrish.app/models/choose](https://hebrish.app/models/choose).)

- **Models tab, two levels.** Each family is listed by what it is trained for: **Sabich** (Hebrew words plus tech vocabulary, recommended), **Jachnun** (Hebrew words only), **Shakshuka** (live text while you talk) and stock Parakeet, with its versions on different base models under it.
- Every version shows **speed and accuracy dots** (1 to 5, estimates), its download size, the hardware it needs, and one line on who it is for.
- **Help me choose…** asks where you dictate, your graphics card and its memory (detected where possible), and whether speed or accuracy matters more, then names a version, using the same rules as the website. If the best fit runs outside the app (Sabich-Qwen3-ASR-1.7B on a GPU, via llama.cpp), it says so and names the best one the app can run, with a Download button.
- Versions the app can't run yet are listed greyed with where they run and a link to the model card. **Sabich-Parakeet-110M** is new: a small, fast version (137 MB) for older computers.
- Your model, downloads and updates are unchanged.
- Ubuntu 26.04 .deb and a portable Windows zip. Not yet tested on Windows hardware. Downloads: [hebrish.app/download](https://hebrish.app/download).
