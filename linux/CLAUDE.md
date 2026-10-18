# Codeswitch Dictation (Linux)

Single-model desktop dictation for the English-Hebrew Parakeet fine-tune. Read
`docs/maintaining.md` before changing the update protocol, the engine padding, or the
hotkey/paste path: each has a measured reason recorded there.

- Dev venv: `uv venv --python /usr/bin/python3 --system-site-packages .venv && uv pip install -e . pytest`
  (the distro python is required, for gi and evdev).
- Tests: `.venv/bin/python -m pytest tests`.
- The update protocol must stay in step with the Android app
  (`../English-Hebrew-Codeswitching-Voice-Keyboard-Android/docs/maintaining.md`).
