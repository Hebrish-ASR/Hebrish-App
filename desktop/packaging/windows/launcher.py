# PyInstaller entry point (a package's __main__ can't be frozen directly with relative imports).
from parlance.ui.app import main

main()
