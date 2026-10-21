# Hebrish: desktop (Linux + Windows)

Read `docs/maintaining.md` before changing the update protocol, the engine padding and
pause handling, or the hotkey and paste path. Each has a measured reason recorded there.
The model source and update rules are shared with Android: `../shared/catalogue.json` (the model catalogue, schema 2 since 0.6.0;
`hebrish/data/catalogue.json` is a byte-identical copy, re-copy after editing; `../shared/models.json` is schema 1 for older builds) and
`../shared/update-protocol.md` (`tests/test_shared.py` enforces them).

- Dev venv (Linux): `uv venv --python /usr/bin/python3 --system-site-packages .venv && uv pip install -e . pytest`.
  The distro python is required, for apt's PySide6 and evdev.
- Tests: `.venv/bin/python -m pytest tests`.
- Per-OS code lives only in `hotkey_evdev.py` / `hotkey_win.py`,
  `inserter_linux.py` / `inserter_win.py` and `autostart.py`. Everything else is shared.
  `ui/overlay.py` picks in-process or an XWayland child by Qt platform, not by OS: keep the
  overlay unable to take focus on every route (`docs/maintaining.md`, "Floating overlay").
- Don't run live record-and-paste tests on Daniel's desktop. Render the UI off-screen
  (`QT_QPA_PLATFORM=offscreen`) and drive the controller from a script.
- Hebrish runs alongside the separate Parlance app (`../../Parlance-Dictation`, same code
  lineage, every identifier `parlance`). Keep every installed path, dir, socket, uinput device
  and autostart entry named `hebrish`, and never write to Parlance's dirs: see
  `docs/maintaining.md`, "Hebrish and Parlance".
