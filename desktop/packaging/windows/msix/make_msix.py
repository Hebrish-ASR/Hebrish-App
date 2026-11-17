"""Lay out the MSIX folder for makeappx (run in CI after PyInstaller; needs PySide6).

    python packaging/windows/msix/make_msix.py dist/Hebrish msix-layout

Copies the PyInstaller folder to <layout>/Hebrish, renders the logos from the app SVG into
<layout>/Assets and writes <layout>/AppxManifest.xml from the template. Identity from the environment
(Partner Center values for a Store build): MSIX_NAME, MSIX_PUBLISHER, MSIX_PUBLISHER_DISPLAY; the
defaults are dev placeholders. Version: hebrish.__version__ as the Store's four-part form, 1.041 ->
1.41.0.0 (the last part must be 0 for the Store)."""
import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon, QImage, QPainter

HERE = Path(__file__).resolve().parent
DESKTOP = HERE.parents[2]
sys.path.insert(0, str(DESKTOP))
from hebrish import __version__  # noqa: E402
from hebrish.app_update import velopack_version  # noqa: E402

SVG = DESKTOP / "hebrish" / "data" / "icons" / "hebrish.svg"
# name: (width, height); the icon is centred at the height's 80 %.
ASSETS = {"StoreLogo.png": (50, 50), "Square44x44Logo.png": (44, 44), "Square150x150Logo.png": (150, 150),
          "Wide310x150Logo.png": (310, 150), "Square44x44Logo.targetsize-256_altform-unplated.png": (256, 256)}


def main(src: str, layout: str):
    app = QGuiApplication(sys.argv[:1])  # noqa: F841 (QIcon needs it)
    out = Path(layout)
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(src, out / "Hebrish")
    (out / "Assets").mkdir(parents=True)
    icon = QIcon(str(SVG))
    for name, (w, h) in ASSETS.items():
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        side = int(min(w, h) * (1.0 if w == h and w <= 50 else 0.8))
        p = QPainter(img)
        p.drawPixmap((w - side) // 2, (h - side) // 2, icon.pixmap(side, side))
        p.end()
        img.save(str(out / "Assets" / name))
    text = (HERE / "AppxManifest.xml").read_text(encoding="utf-8")
    values = {"NAME": os.environ.get("MSIX_NAME") or "Hebrish.Dictation.Dev",
              "PUBLISHER": os.environ.get("MSIX_PUBLISHER") or "CN=Hebrish Dev",
              "PUBLISHER_DISPLAY": os.environ.get("MSIX_PUBLISHER_DISPLAY") or "Hebrish",
              "VERSION": velopack_version(__version__) + ".0"}
    for k, v in values.items():
        text = text.replace("{" + k + "}", v)
    (out / "AppxManifest.xml").write_text(text, encoding="utf-8")
    print("MSIX layout in", out, values)


if __name__ == "__main__":
    main(*sys.argv[1:3])
