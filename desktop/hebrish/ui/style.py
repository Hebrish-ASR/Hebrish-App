"""Look and feel: the hebrish.app brand (Hebrish-Mgmt/brand/tokens.json; 1.007 moved the app from
flag blue to the brand's green and paper). Accents are fixed (brand green, record red, busy amber);
surfaces use the system palette, so the window follows light and dark themes. `QSS` is built when
first imported, after the QApplication exists, from that palette: the dark-theme accent is the
brand's dark token."""

# The Hebrish brand (Hebrish-Mgmt/brand/tokens.json, light)
BRAND_GREEN = "#0f6b5c"
BRAND_GREEN_HOVER = "#0c5a4d"   # a darker BRAND_GREEN, not a different green
PAPER = "#fbf8f2"
INK = "#1d2422"
MUTED = "#5b6662"
LINE = "#e2dccf"
GOLD = "#c8901c"
# tokens.json, dark
DARK = {"bg": "#111615", "surface": "#18201e", "ink": "#e8ece9", "muted": "#9aa7a2",
        "line": "#2a3532", "accent": "#3fbf9f", "accent_ink": "#0c1412", "gold": "#e0b14a"}

# The accent everywhere a control is "on" (record button, primary buttons, selected tab). BLUE is
# the pre-1.007 name, kept because the overlay and older code import it.
ACCENT = BLUE = BRAND_GREEN
ACCENT_HOVER = BLUE_HOVER = BRAND_GREEN_HOVER
RED = "#D62828"
RED_PULSE = "#ef4b4b"
AMBER = "#E8A317"
# Transcription recorder's round buttons (1.012): one colour per action, white icon on each.
TAPE_COLOURS = {"record": RED, "pause": AMBER, "stop": "#3f4b57", "retake": "#2f6fb5",
                "discard": "#7b8794", "transcribe": BRAND_GREEN}
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


def is_dark() -> bool:
    """The system theme is dark (window colour), once a QApplication exists."""
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance()
    return bool(app) and app.palette().window().color().lightness() < 128


def colours() -> dict:
    """The theme's brand colours: header surface, ink, muted, line, accent, text on the accent."""
    if is_dark():
        return {"head": DARK["surface"], "ink": DARK["ink"], "muted": DARK["muted"], "line": DARK["line"],
                "accent": DARK["accent"], "accent_hover": "#5fd0b3", "on_accent": DARK["accent_ink"],
                "gold": DARK["gold"]}
    return {"head": PAPER, "ink": INK, "muted": MUTED, "line": LINE, "accent": BRAND_GREEN,
            "accent_hover": BRAND_GREEN_HOVER, "on_accent": "white", "gold": GOLD}


def qss() -> str:
    from PySide6.QtGui import QColor
    c = colours()
    tape = "\n".join(f'#tapeButton[kind="{k}"] {{ background: {v}; }}\n'
                     f'#tapeButton[kind="{k}"]:hover {{ background: {QColor(v).darker(115).name()}; }}\n'
                     f'#tapeButton[kind="{k}"]:disabled {{ background: rgba({QColor(v).red()}, '
                     f'{QColor(v).green()}, {QColor(v).blue()}, 0.3); }}'
                     for k, v in TAPE_COLOURS.items())
    return f"""
#header {{ background: {c['head']}; border-bottom: 1px solid {c['line']}; }}
#header QLabel {{ color: {c['ink']}; }}
#header #tagline {{ color: {c['muted']}; font-size: 12px; }}
#headerButton {{ border: none; border-radius: 6px; padding: 4px 8px; color: {c['muted']}; }}
#headerButton:hover {{ background: {c['line']}; color: {c['ink']}; }}
#headerButton:checked {{ color: {c['accent']}; font-weight: 600; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ padding: 8px 12px; margin: 0 1px; border: none;
               border-bottom: 3px solid transparent; }}
QTabBar::tab:selected {{ border-bottom: 3px solid {c['accent']}; color: {c['accent']}; font-weight: 600; }}
QTabBar::tab:hover:!selected {{ border-bottom: 3px solid {c['line']}; }}

#card {{ background: palette(base); border: 1px solid palette(mid); border-radius: 10px; }}
#cardTitle {{ font-weight: 700; font-size: 13px; }}
#muted {{ color: palette(placeholder-text); }}
#footer {{ border-top: 1px solid palette(mid); }}
#version {{ font-size: 12px; font-weight: 600; }}
#transcript {{ font-size: 13px; }}
#statBig {{ font-size: 18px; font-weight: 700; }}

#record {{ border-radius: 52px; font-size: 15px; font-weight: 700; color: {c['on_accent']};
          background: {c['accent']}; border: 4px solid palette(base); }}
#record:hover {{ background: {c['accent_hover']}; }}
#record[state="recording"] {{ background: {RED}; color: white; }}
#record[state="recording"][pulse="true"] {{ background: {RED_PULSE}; }}
#record[state="busy"] {{ background: {AMBER}; color: {INK}; }}
#record:disabled {{ background: palette(mid); }}

#tapeButton {{ border: none; border-radius: 20px; }}
{tape}

#primary {{ background: {c['accent']}; color: {c['on_accent']}; border: none; border-radius: 6px;
           padding: 6px 14px; font-weight: 600; }}
#primary:hover {{ background: {c['accent_hover']}; }}
#outputToggle:checked {{ background: {c['accent']}; color: {c['on_accent']}; border-color: {c['accent']}; }}
#dropZone {{ border: 2px dashed palette(mid); border-radius: 12px; background: palette(base);
             font-size: 15px; color: palette(placeholder-text); padding: 18px; }}
#dropZone:hover {{ border-color: {c['accent']}; color: {c['accent']}; }}
#toast {{ background: {BRAND_GREEN}; color: white; border-radius: 14px; font-weight: 600; }}
#updateBar {{ background: #e3f1ec; border-bottom: 1px solid #b9dccf; }}
#updateBar QLabel {{ color: {INK}; }}
#banner {{ background: #fff3cd; color: #5c4400; border-radius: 8px; padding: 8px; }}
QProgressBar {{ border: 1px solid palette(mid); border-radius: 5px; text-align: center;
               height: 18px; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}
"""


def __getattr__(name):
    # `from .style import QSS` (app.main, scripts/screenshots.py) runs after the QApplication is
    # made, so the theme is known by then.
    if name == "QSS":
        return qss()
    raise AttributeError(name)
