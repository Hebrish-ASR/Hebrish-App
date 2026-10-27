"""Line icons (1.007): data/icons/line-<name>.svg, 24 px, stroke 2, drawn in black and tinted
here to the theme's text colour (or a given colour), so they read on light and dark and look the
same on Linux and Windows. QIcon.fromTheme gave Breeze/Adwaita icons on Linux and none on Windows."""

from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize
from PySide6.QtGui import QGuiApplication, QIcon, QImageReader, QPixmap

ICONS = Path(__file__).resolve().parent.parent / "data" / "icons"
_cache: dict[tuple[str, str, int], QIcon] = {}


def line_icon(name: str, colour: str = "", px: int = 48) -> QIcon:
    if not colour:
        app = QGuiApplication.instance()
        colour = app.palette().buttonText().color().name() if app else "#1d2422"
    key = (name, colour, px)
    if key not in _cache:
        svg = (ICONS / f"line-{name}.svg").read_text().replace('stroke="#000"', f'stroke="{colour}"')
        # through Qt's SVG image plugin (qt6-svg-plugins on Debian/Ubuntu): QtSvg isn't a dependency
        buf = QBuffer()
        buf.setData(QByteArray(svg.encode()))
        buf.open(QIODevice.ReadOnly)
        reader = QImageReader(buf, b"svg")
        reader.setScaledSize(QSize(px, px))           # rendered at size, not scaled up from 24 px
        _cache[key] = QIcon(QPixmap.fromImage(reader.read()))
    return _cache[key]
