**1.032: The app and its models update themselves.**

- **App updates in the background** (F-Droid and APK installs): once Hebrish is allowed to install apps (a new optional Setup step), it checks for a new version every 12 hours on Wi-Fi, verifies the download's size and checksum, and installs it when no take is open. On Android 12 and later this is usually silent; Android 9 to 11 ask through a notification. "Update Hebrish in the background" on Install and updates turns it off; "Check for updates now" checks at once.
- **Models update in the background:** every 6 hours, on Wi-Fi by default, Hebrish downloads new versions of the models you have installed, the selected one first. A take in progress is never interrupted: the switch to the new model waits until it ends. "Update models automatically" and "Only on Wi-Fi" on the Models screen.
- Not yet tested on a device. arm64-v8a only. Android 9+. Downloads: [hebrish.app/download](https://hebrish.app/download).
