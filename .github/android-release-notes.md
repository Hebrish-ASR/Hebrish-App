**1.010: Stability release: less memory, and a floating mic crash guarded.**

- **Less memory:** the speech model (about 700 MB) is no longer loaded when the phone starts. It loads when you focus a text field or start a take, is freed after 5 minutes without use, and is freed straight away when the phone runs short of memory. Up to 1.009 it stayed in memory all the time, which could make the phone close other apps in the background. The first take after a pause can take a few seconds longer to start transcribing.
- **Floating mic:** dragging the floating mic is guarded against a crash ("The specified child already has a parent") reported on 0.6.0.
- Only these changes on top of 1.009. Not yet tested on a phone. arm64-v8a only. Android 9+. Downloads: [hebrish.app/download](https://hebrish.app/download).
