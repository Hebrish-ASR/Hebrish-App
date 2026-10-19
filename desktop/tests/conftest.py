"""Loaded by pytest before any test module is imported: point every per-user dir at a temp
dir, so hebrish.config's CONFIG_DIR / DATA_DIR (computed at import) can never be the real
~/.config or ~/.local/share. Without this, whichever test module imported config first decided
the paths, and on 2026-10-19 a run wrote into the real ~/.config/hebrish and deleted the real
~/.config/voice-to-hebrish and ~/.local/share/voice-to-hebrish (the legacy-adoption test
removes its "old" dirs at the end)."""

import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="hebrish-tests-"))
for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "APPDATA", "LOCALAPPDATA"):
    os.environ[var] = str(_TMP / var)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hebrish import autostart, config  # noqa: E402

for p in (config.CONFIG_DIR, config.DATA_DIR, autostart._DESKTOP):
    assert _TMP in p.parents, f"test paths escaped the temp dir: {p}"
