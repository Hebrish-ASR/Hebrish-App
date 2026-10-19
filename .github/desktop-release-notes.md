**0.2.0: Hebrish everywhere, and it installs alongside Parlance.**

- The command, package, folders and files are now `hebrish` (up to 0.1.2 they were `parlance`): run `hebrish` / `hebrish-model`, install `hebrish_0.2.0-1_amd64.deb`, or unzip and run `Hebrish.exe`.
- Hebrish and [Parlance](https://github.com/danielrosehill/Parlance-Dictation) are now separate apps and can be installed at the same time. An existing 0.1.x `parlance` install stays Parlance and is upgraded by Parlance 0.2.0.
- On first start Hebrish copies Parlance's settings (except the hotkey) and history, and hardlinks its downloaded models, so nothing is downloaded again and Parlance keeps working.
- The default hotkey is now **F14**, because Parlance keeps F13 and a shared key would start both apps. Each app ignores the other's paste device.
- Ubuntu 26.04 .deb and a portable Windows zip (Windows still untested on real hardware).
