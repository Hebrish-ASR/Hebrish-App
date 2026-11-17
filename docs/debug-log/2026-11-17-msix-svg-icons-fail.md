---
date: 2026-11-17
platform: desktop-windows
environment: GitHub Actions windows-latest (Windows Server, SDK 10.0.26100), MSIX installed with Add-AppxPackage
component: desktop/packaging/windows/launcher.py (MSIX build, unreleased)
affected: "MSIX dev builds before commit 'preload Qt6Svg.dll'"
fixed_in: "unreleased (first MSIX release)"
status: fixed
---

# In the MSIX package every SVG icon fails to render

## Symptom

CI's MSIX install test (`.github/workflows/desktop.yml`, step "Install the MSIX (self-signed copy)
and self-test it", run 44104121375) failed `--selftest` with "an icon failed to load (missing Qt SVG plugin?)":
every `hebrish/data/icons/*.svg` rendered null. The same PyInstaller folder passed as the zip and as the
Velopack install in the same run.

## How it was found

The selftest was made to print, on failure, `sys.executable`, `sys._MEIPASS`,
`QT_PLUGIN_PATH`, `QCoreApplication.libraryPaths()` and `QImageReader.supportedImageFormats()` (run
44105576595). All paths pointed correctly into `C:\Program Files\WindowsApps\…\Hebrish\_internal`, and the
plugin folder was on the library path, but the format list had every imageformats plugin except `svg`.

## Cause

`imageformats\qsvg.dll` depends on `Qt6Svg.dll` (in `_internal\PySide6`). Outside a package that is
found through `PATH`, which PyInstaller's PySide6 runtime hook extends. A packaged (MSIX) app's DLL search order
does not include `PATH` (Microsoft, "Dynamic-link library search order", packaged apps), so Qt's own
`LoadLibrary` of the plugin failed silently. The other image plugins only need Qt6Gui/Qt6Core, which were
already loaded. (Cause inferred from the format list and the documented search order; the fix confirms it.)

## Fix

`desktop/packaging/windows/launcher.py` imports `PySide6.QtSvg` before the app starts (PyInstaller:
`--hidden-import PySide6.QtSvg`). Python loads `Qt6Svg.dll` through its own search (`os.add_dll_directory`), and
the plugin then finds it in memory. Run 44106984180: MSIX selftest OK, zip and Velopack unchanged.

## Ruled out

The `hebrish.exe` app-execution alias as `argv[0]` (the alias path) was suspected of
breaking `_MEIPASS`/plugin paths: the diagnostics showed `sys.executable` and `_MEIPASS` resolve to the real
package folder.

## Watch for

Any other Qt plugin with its own Qt dependency (e.g. multimedia, TLS backends) would fail the same
way under MSIX: preload its module in `launcher.py`.
