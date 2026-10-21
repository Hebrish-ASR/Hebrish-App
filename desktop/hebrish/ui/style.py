"""Look and feel. Accent colours are fixed (flag blue, record red); everything else uses
the system palette, so the window follows light and dark themes."""

BLUE = "#24527A"
BLUE_HOVER = "#1a4fd0"
RED = "#D62828"
RED_PULSE = "#ef4b4b"
AMBER = "#E8A317"
# The Hebrish brand (Hebrish-Mgmt/brand/tokens.json, light): used by the splash and the About
# hero, where the green mark has to sit on paper rather than on the blue.
BRAND_GREEN = "#0f6b5c"
PAPER = "#fbf8f2"
INK = "#1d2422"
MUTED = "#5b6662"
GOLD = "#c8901c"
_display_family = None


def display_font(px: int, bold: bool = True):
    """Fraunces (brand display face, bundled from Hebrish-Mgmt/brand/fonts), else a serif."""
    global _display_family
    from pathlib import Path
    from PySide6.QtGui import QFont, QFontDatabase
    if _display_family is None:
        fid = QFontDatabase.addApplicationFont(
            str(Path(__file__).resolve().parent.parent / "data" / "fonts" / "Fraunces.ttf"))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        _display_family = fams[0] if fams else "serif"
    f = QFont(_display_family)
    f.setStyleHint(QFont.Serif)
    f.setPixelSize(px)
    f.setWeight(QFont.Bold if bold else QFont.DemiBold)
    return f

QSS = f"""
#header {{ background: {BLUE}; }}
#header QLabel {{ color: white; }}
#title {{ font-size: 20px; font-weight: 700; }}
#tagline {{ font-size: 12px; opacity: 0.85; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ padding: 8px 18px; margin: 0 2px; border: none;
               border-bottom: 3px solid transparent; }}
QTabBar::tab:selected {{ border-bottom: 3px solid {BLUE}; font-weight: 600; }}

#card {{ background: palette(base); border: 1px solid palette(mid); border-radius: 10px; }}
#cardTitle {{ font-weight: 700; font-size: 13px; }}
#muted {{ color: palette(placeholder-text); }}
#footer {{ border-top: 1px solid palette(mid); }}
#version {{ font-size: 12px; font-weight: 600; }}
#transcript {{ font-size: 13px; }}

#record {{ border-radius: 52px; font-size: 15px; font-weight: 700; color: white;
          background: {BLUE}; border: 4px solid palette(base); }}
#record:hover {{ background: {BLUE_HOVER}; }}
#record[state="recording"] {{ background: {RED}; }}
#record[state="recording"][pulse="true"] {{ background: {RED_PULSE}; }}
#record[state="busy"] {{ background: {AMBER}; }}
#record:disabled {{ background: palette(mid); }}

#primary {{ background: {BLUE}; color: white; border: none; border-radius: 6px;
           padding: 6px 14px; font-weight: 600; }}
#primary:hover {{ background: {BLUE_HOVER}; }}
#dropZone {{ border: 2px dashed palette(mid); border-radius: 12px; background: palette(base);
             font-size: 15px; color: palette(placeholder-text); padding: 18px; }}
#dropZone:hover {{ border-color: {BLUE}; color: {BLUE}; }}
#toast {{ background: {BRAND_GREEN}; color: white; border-radius: 14px; font-weight: 600; }}
#updateBar {{ background: #e3f1ec; border-bottom: 1px solid #b9dccf; }}
#updateBar QLabel {{ color: {INK}; }}
#banner {{ background: #fff3cd; color: #5c4400; border-radius: 8px; padding: 8px; }}
QProgressBar {{ border: 1px solid palette(mid); border-radius: 5px; text-align: center;
               height: 18px; }}
QProgressBar::chunk {{ background: {BLUE}; border-radius: 4px; }}
"""
