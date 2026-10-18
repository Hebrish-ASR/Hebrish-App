"""Render the app SVG to a multi-size .ico for the exe (run in CI; needs PySide6 + Pillow)."""
import io
import sys

from PIL import Image
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QGuiApplication, QIcon

app = QGuiApplication(sys.argv[:1])
svg, out = sys.argv[1], sys.argv[2]
icon = QIcon(svg)
data = QByteArray()
buf = QBuffer(data)
buf.open(QIODevice.WriteOnly)
icon.pixmap(256, 256).save(buf, "PNG")
img = Image.open(io.BytesIO(bytes(data)))
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", out)
