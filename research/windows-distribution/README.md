# Windows distribution: installer, self-update, Microsoft Store

## Question

The Windows build ships as a portable zip (`Hebrish-latest-windows-x64.zip`). `desktop/hebrish/app_update.py`
(method `windows`) only links to the download page when `files.windows` in `latest.json` is newer, so Windows users
update by hand and stay behind (Windows was on 1.026 while the .deb reached 1.040). Daniel, 2026-11-17: package it
the way a Windows app should be, update it with no user action, and ship both a direct installer and the Microsoft
Store. The Linux .deb waits and goes out with the first such Windows release.

## Status

Answered (2026-11-17): built. Daniel chose both channels, unsigned for now ("whatever is quickest and simplest"). Shipped behaviour and CI verification: `desktop/docs/maintaining.md`, "Windows: installer that updates itself, and the Microsoft Store". Findings read 2026-11-17 by an agent from vendor docs.
Tags: **(S)** confirmed from the source, **(I)** inferred or not found in a source.

## Findings

### Velopack (direct installer with self-update)

- MIT. PyPI `velopack` 1.2.161 (2026-09-29), with abi3 wheels. CLI `vpk` is a .NET tool, and its version must match the Python package's. (S)
  https://pypi.org/project/velopack/, https://github.com/velopack/velopack
- Python: `velopack.App().run()` first thing at start; `UpdateManager(url)` → `check_for_updates()` →
  `download_updates(info)` → `apply_updates_and_restart(info)`. PyInstaller must be `--onedir` (ours is). (S)
  https://docs.velopack.io/getting-started/python
- `vpk pack --packId --packVersion --packDir --mainExe`. Setup.exe is one-click and per-user. It installs to
  `%LocalAppData%\{packId}\current` with `Update.exe` beside it, and adds Desktop and Start menu shortcuts and an
  Apps & Features entry. `-s/--silent` is supported. (S) https://docs.velopack.io/packaging/installer
- **Trap:** our models and data already live in `%LOCALAPPDATA%\Hebrish` (`desktop/hebrish/config.py`
  `DATA_DIR`), so the packId must not be `Hebrish`. (I, from the two paths)
- Feed: static files in one folder: `releases.<channel>.json`, `*-full.nupkg`, `*-delta.nupkg`, `*-Setup.exe`.
  `UpdateManager` takes the base URL. Plain HTTP on R2 (`cdn.hebrish.app`) should work. (S/I)
  https://docs.velopack.io/distributing/overview
- Channels: `--channel`, each build reads only its own `releases.<channel>.json`. This maps onto our beta and stable. (S)
  https://docs.velopack.io/packaging/channels
- Deltas: on by default, if the previous release's package is in the output dir (`vpk download` fetches it). (S)
- Signing: `--signParams` (signtool), `--azureTrustedSignFile`, `--signTemplate` (jsign, AzureSignTool). Unsigned
  Setup.exe gets SmartScreen and AV warnings. (S) https://docs.velopack.io/packaging/signing

### Microsoft Store

- Registration is free for individuals since 2025-09-10 (ID and selfie check). (S)
  https://blogs.windows.com/windowsdeveloper/2025/09/10/free-developer-registration-for-individual-developers-on-microsoft-store/
- **MSIX route:** the Store signs the package, so no certificate is needed. (S)
  https://learn.microsoft.com/en-us/windows/msix/package/signing-package-overview
  - Full-trust Win32 (`runFullTrust`) packaged with makeappx and a hand-written manifest. (I for PyInstaller)
  - Writes under `%LocalAppData%` and `%AppData%` are redirected to a per-package folder and **deleted on uninstall**,
    which includes the ~600 MB models. The HKCU Run key is virtualised, so autostart must use `desktop:StartupTask`. (S)
    https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-behind-the-scenes
  - The Store updates the app itself; the in-app updater must be off in that build. (I: policy wording found only for games, 10.2.5)
  - Global hotkey, low-level keyboard hook, SendInput into other apps and the localhost API: Microsoft lists no
    restriction for full trust, but none of these is tested. (I) **Must be tested before committing.**
- **Unpackaged EXE route (policy 10.2.9):** the Store lists our own installer. It must be signed by a trusted CA,
  hosted at a versioned HTTPS URL, and install silently as a standard user. Each update is a new submission. (S)
  https://learn.microsoft.com/en-us/windows/apps/publish/store-policies

### Code signing

- Azure Artifact Signing (formerly Trusted Signing), about $10 a month: **individuals only in the US or Canada**.
  Organisations are accepted in more countries, Israel included, but an older page asks for 3+ years of verifiable
  history. (S) https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart
- Otherwise an OV certificate (e.g. Certum's open-source developer certificate, SSL.com), used through jsign or
  signtool. (I: vendors not yet priced)
- Even signed, a new app shows SmartScreen warnings until it has download history. (S, Microsoft)

### winget

- `InstallerType: exe` with `InstallerSwitches: Silent: --silent` for a Velopack Setup.exe. Each version needs a
  stable URL and a SHA-256. `wingetcreate` can open the PR from CI. Signing is in practice expected. (S/I)
  https://learn.microsoft.com/en-us/windows/package-manager/package/manifest

## Recommendation (adopted 2026-11-17, except signing and winget: later)

1. **Direct channel: Velopack**, packId `HebrishDictation`, channels `beta` and `stable`, with the feed on
   `cdn.hebrish.app/apps/windows/velopack/`. `app_update.py` gains a `velopack` method that checks, downloads in the
   background and applies on the next restart. The zip ships once more, with a notice pointing at the installer.
2. **Store: MSIX** (free, Store-signed), the same PyInstaller output with Velopack disabled and a StartupTask.
   Prototype first: hotkey, paste, mic and local API under MSIX, and where models land.
3. **Signing** decides how clean the direct installer is. It needs an OV certificate or an organisation account (a money decision).
4. **winget** after signing.
