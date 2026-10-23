**0.8.2: fewer capitals and full stops in the middle of sentences.**

- Long takes are transcribed in pieces at your pauses. Each piece used to be treated as a sentence of its own, so a pause mid-sentence could leave "word. Capital" or "word Capital". Now each piece is transcribed together with the end of the one before it, so the model hears the sentence carry on, and a full stop at a pause is only kept if the sentence really ended there. Same fix as desktop 0.7.6. On desktop it cut mid-sentence capitals by more than half on the benchmark.
- Takes shorter than about 8 seconds were never affected and work as before. Long takes may take a moment longer after you tap stop.
- The history export has a new `context_s` column.
- Not yet tested on a device. arm64-v8a only. Android 9+. Downloads: [hebrish.app/download](https://hebrish.app/download).
