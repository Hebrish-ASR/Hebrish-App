# Parlance: desktop (Linux + Windows)

Read `docs/maintaining.md` before changing the update protocol, the engine padding and
pause handling, or the hotkey and paste path. Each has a measured reason recorded there.
The model source and update rules are shared with Android: `../shared/models.json` (the model catalogue; `parlance/data/models.json` is a
byte-identical copy, re-copy after editing) and
`../shared/update-protocol.md` (`tests/test_shared.py` enforces them).

- Dev venv (Linux): `uv venv --python /usr/bin/python3 --system-site-packages .venv && uv pip install -e . pytest`.
  The distro python is required, for apt's PySide6 and evdev.
- Tests: `.venv/bin/python -m pytest tests`.
- Per-OS code lives only in `hotkey_evdev.py` / `hotkey_win.py`,
  `inserter_linux.py` / `inserter_win.py` and `autostart.py`. Everything else is shared.
- Don't run live record-and-paste tests on Daniel's desktop. Render the UI off-screen
  (`QT_QPA_PLATFORM=offscreen`) and drive the controller from a script.
