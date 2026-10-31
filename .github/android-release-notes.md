**1.011: Stability release: the speech model is now freed while the phone sleeps.**

- **Less memory while the phone sleeps:** 1.010 freed the speech model (about 700 MB) after 5 minutes without use, but that timer stalls while the phone is asleep, so the model could stay in memory for hours. Now it is also freed as soon as the screen turns off (unless you are recording), and the 5 minutes are measured on a clock that keeps counting during sleep.
- Model loads and frees are logged under the tag `HebrishModel`, for anyone checking memory with adb.
- Only these changes on top of 1.010. Not yet tested on a phone. arm64-v8a only. Android 9+. Downloads: [hebrish.app/download](https://hebrish.app/download).
