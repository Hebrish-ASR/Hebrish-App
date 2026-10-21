#!/usr/bin/env python3
"""Render the desktop app's screenshots off-screen:   .venv/bin/python scripts/screenshots.py [out_dir]
(the venv: system python3 has no sherpa-onnx, and the model would not load)

Writes <out_dir>/desktop-{dictate,file,model,settings,about}.png (default: the repo's docs/screenshots/)
at 2x, 1200x1440.
Nothing appears on screen (QT_QPA_PLATFORM=offscreen) and real settings are untouched: config
and data live in a temp dir, with this machine's downloaded models symlinked in and its
state.json copied (which model version is active). Needs a downloaded model (Sabich).

The File tab shows Sabich's real output on a public sample clip from hebrish.app/archive
(cdn.hebrish.app/samples/clips/), never typed-in text. Re-run it for each release so the
version in the footer matches; the AppStream metainfo and hebrish.app use these files.
"""

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

DESKTOP = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DESKTOP.parent / "docs" / "screenshots"
CLIP = "https://cdn.hebrish.app/samples/clips/20261015T104852Z_zntv22.wav"
TABS = ("dictate", "file", "model", "settings", "about")

real = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "hebrish"
tmp = Path(tempfile.mkdtemp(prefix="hebrish-shots-"))
(tmp / "config/hebrish").mkdir(parents=True)
(tmp / "data/hebrish").mkdir(parents=True)
# Defaults (F14 hotkey, paste at the cursor) except: no app-update strip, no sounds.
(tmp / "config/hebrish/config.json").write_text(json.dumps(
    {"app_update_check": False, "feedback": "off"}))
os.symlink(real / "models", tmp / "data/hebrish/models")
if (real / "state.json").exists():
    state = json.loads((real / "state.json").read_text())
    state = {k: v for k, v in state.items() if k in ("active", "model")}
    (tmp / "data/hebrish/state.json").write_text(json.dumps(state))
# Before importing hebrish: config.py fixes its paths at import time.
os.environ.update(QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR="2",
                  XDG_CONFIG_HOME=str(tmp / "config"), XDG_DATA_HOME=str(tmp / "data"))
sys.path.insert(0, str(DESKTOP))

from PySide6.QtWidgets import QApplication  # noqa: E402

from hebrish import model_store  # noqa: E402
from hebrish.ui.app import Controller  # noqa: E402
from hebrish.ui.style import QSS  # noqa: E402


def pump(done, timeout=120.0):
    end = time.monotonic() + timeout
    while not done():
        if time.monotonic() > end:
            raise TimeoutError("gave up waiting")
        app.processEvents()
        time.sleep(0.05)
    app.processEvents()


app = QApplication([sys.argv[0]])
app.setApplicationName("Hebrish")
app.setStyleSheet(QSS)
ctl = Controller(hidden=True)
win = ctl.win
try:
    pump(lambda: not ctl.loading and ctl.engine.loaded_dir is not None)
except TimeoutError:
    sys.exit(f"model not loaded: active={model_store.active()} loading={ctl.loading} status={win.status_label.text()!r}")

wav = tmp / "sample.wav"
wav.write_bytes(model_store._get(CLIP, timeout=60))
win.tabs.setCurrentWidget(win.pages["file"])
win.transcribe.transcribe_file(str(wav))
pump(lambda: win.transcribe.cancel is None and win.transcribe.text.toPlainText().strip(), 300)

OUT.mkdir(parents=True, exist_ok=True)
file_status = win.status_label.text()       # "Transcribed 00:04 of audio in 0.4 s."
win.show()
for key in TABS:
    win.tabs.setCurrentWidget(win.pages[key])
    win.status(file_status if key == "file" else "")
    pump(lambda: True)
    path = OUT / f"desktop-{key}.png"
    win.grab().save(str(path))
    print(path)
win.hide()
shutil.rmtree(tmp, ignore_errors=True)
os._exit(0)     # the hotkey and decode threads are daemons; skip Qt teardown
