# PyInstaller entry point (a package's __main__ can't be frozen directly with relative imports).
import sys

# Velopack's startup hook (1.041) must run first: on install, update and uninstall Velopack starts
# the exe with its own arguments, and run() handles them and exits. In a normal start it applies an
# update downloaded earlier (auto-apply) and returns. Not in the zip or the MSIX build, where there
# is no Update.exe; a failure here must never stop the app starting.
if "\\windowsapps\\" not in sys.executable.lower():
    try:
        import velopack
        velopack.App().run()
    except Exception:
        pass

# MSIX (V, CI run 44105576595, 2026-11-17): every SVG icon failed to render, because Qt's svg image
# plugin (imageformats\qsvg.dll) couldn't load its dependency Qt6Svg.dll. A packaged app's DLL search
# doesn't use PATH, which is how PyInstaller's PySide6 hook makes _internal\PySide6 findable for
# plugins Qt loads itself. Importing the QtSvg module loads Qt6Svg.dll through Python's own search
# (os.add_dll_directory), so the plugin finds it already in memory. Harmless elsewhere.
try:
    import PySide6.QtSvg  # noqa: F401
except ImportError:
    pass

from hebrish.ui.app import main

main()
