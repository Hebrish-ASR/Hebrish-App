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

from hebrish.ui.app import main

main()
