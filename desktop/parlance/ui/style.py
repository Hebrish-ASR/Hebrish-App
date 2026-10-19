"""Look and feel. Accent colours are fixed (flag blue, record red); everything else uses
the system palette, so the window follows light and dark themes."""

BLUE = "#24527A"
BLUE_HOVER = "#1a4fd0"
RED = "#D62828"
RED_PULSE = "#ef4b4b"
AMBER = "#E8A317"

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
#transcript {{ font-size: 13px; }}

#record {{ border-radius: 66px; font-size: 15px; font-weight: 700; color: white;
          background: {BLUE}; border: 4px solid palette(base); }}
#record:hover {{ background: {BLUE_HOVER}; }}
#record[state="recording"] {{ background: {RED}; }}
#record[state="recording"][pulse="true"] {{ background: {RED_PULSE}; }}
#record[state="busy"] {{ background: {AMBER}; }}
#record:disabled {{ background: palette(mid); }}

#primary {{ background: {BLUE}; color: white; border: none; border-radius: 6px;
           padding: 6px 14px; font-weight: 600; }}
#primary:hover {{ background: {BLUE_HOVER}; }}
#banner {{ background: #fff3cd; color: #5c4400; border-radius: 8px; padding: 8px; }}
QProgressBar {{ border: 1px solid palette(mid); border-radius: 5px; text-align: center;
               height: 18px; }}
QProgressBar::chunk {{ background: {BLUE}; border-radius: 4px; }}
"""
