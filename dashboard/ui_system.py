"""
ui_system.py
EyeStrain AI — Centralised UI System

Theme, fonts, SVG icons, shared components.
Import this in main.py and login.py for consistent styling.
"""

from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt, QByteArray
from PyQt6.QtGui import (
    QFont, QFontDatabase, QColor, QPixmap, QPainter,
    QFontMetrics
)

# ── THEME ─────────────────────────────────────────────────────────────────────
# Dark, professional, minimal — two reference images show deep navy + accent
T = {
    # Backgrounds
    'bg':        '#0D1117',   # deepest — window background
    'surface':   '#161B22',   # card background
    'surface2':  '#1C2128',   # input, secondary surface
    'surface3':  '#21262D',   # hover states
    # Borders
    'border':    '#30363D',   # subtle border
    'border2':   '#3D444D',   # slightly more visible
    # Text
    'text':      '#E6EDF3',   # primary text
    'text2':     '#8B949E',   # secondary text
    'text3':     '#484F58',   # placeholder / disabled
    # Accent — single blue accent, minimal secondary colors
    'accent':    '#2F81F7',   # primary action
    'accent2':   '#1F6FEB',   # hover
    'accent_dim':'#1C2E45',   # accent background tint
    # Status — used sparingly
    'green':     '#3FB950',
    'yellow':    '#D29922',
    'orange':    '#DB6D28',
    'red':       '#F85149',
    'green_dim': '#12261E',
    'red_dim':   '#2D1317',
    # Flag
    'dark':      True,
}

# ── FONT ──────────────────────────────────────────────────────────────────────
# Font size scale — consistent hierarchy
FS = {
    'xs':    9,   # captions, timestamps
    'sm':   11,   # secondary labels
    'base': 13,   # body text, inputs
    'md':   15,   # card titles, nav items
    'lg':   18,   # section headers
    'xl':   24,   # page titles
    'xxl':  32,   # gauge numbers
    'hero': 48,   # large display numbers
}

_FONT_FAMILY = 'Segoe UI'   # Best Windows system font — clean, modern

def setup_font(app: QApplication) -> str:
    """
    Load Inter from system or fall back to Segoe UI.
    Returns the family name to use.
    """
    db = QFontDatabase()
    # Check if Inter is available (user may have it installed)
    families = db.families()
    for candidate in ['Inter', 'Inter Display', 'Segoe UI Variable',
                      'Segoe UI', 'SF Pro Display']:
        if candidate in families:
            global _FONT_FAMILY
            _FONT_FAMILY = candidate
            break

    base_font = QFont(_FONT_FAMILY, FS['base'])
    base_font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(base_font)
    return _FONT_FAMILY


def font(size: int = None, weight: QFont.Weight = QFont.Weight.Normal,
         italic: bool = False) -> QFont:
    """Create a font with the app family."""
    f = QFont(_FONT_FAMILY, size or FS['base'])
    f.setWeight(weight)
    f.setItalic(italic)
    f.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    return f


def bold(size: int = None) -> QFont:
    return font(size, QFont.Weight.Bold)


def semibold(size: int = None) -> QFont:
    return font(size, QFont.Weight.DemiBold)


# ── SVG ICONS ─────────────────────────────────────────────────────────────────
# Lucide icon paths (MIT license) — embedded as SVG strings
# All use viewBox="0 0 24 24", stroke-based, no fill
_ICONS = {
    'monitor': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/>
        <line x1="12" y1="17" x2="12" y2="21"/></svg>''',

    'bar-chart': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/>
        <line x1="6" y1="20" x2="6" y2="14"/><line x1="2" y1="20" x2="22" y2="20"/></svg>''',

    'file-text': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
        <line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
        <polyline points="10 9 9 9 8 9"/></svg>''',

    'settings': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="3"/>
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06
            a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09
            A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83
            l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09
            A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83
            l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09
            a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83
            l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09
            a1.65 1.65 0 0 0-1.51 1z"/></svg>''',

    'user': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
        <circle cx="12" cy="7" r="4"/></svg>''',

    'flask': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <path d="M9 3h6l1 9H8L9 3z"/><path d="M6.5 15L5 21h14l-1.5-6"/>
        <line x1="9" y1="3" x2="9" y2="12"/><line x1="15" y1="3" x2="15" y2="12"/></svg>''',

    'eye': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
        <circle cx="12" cy="12" r="3"/></svg>''',

    'activity': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>''',

    'clock': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <polyline points="12 6 12 12 16 14"/></svg>''',

    'award': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="8" r="6"/>
        <path d="M15.477 12.89L17 22l-5-3-5 3 1.523-9.11"/></svg>''',

    'shield': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>''',

    'bell-off': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
        <path d="M18.63 13A17.89 17.89 0 0 1 18 8"/>
        <path d="M6.26 6.26A5.86 5.86 0 0 0 6 8c0 7-3 9-3 9h14"/>
        <path d="M18 8a6 6 0 0 0-9.33-5"/>
        <line x1="1" y1="1" x2="23" y2="23"/></svg>''',

    'log-out': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
        <polyline points="16 17 21 12 16 7"/>
        <line x1="21" y1="12" x2="9" y2="12"/></svg>''',

    'check-circle': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
        <polyline points="22 4 12 14.01 9 11.01"/></svg>''',

    'alert-triangle': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3
            L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/>
        <line x1="12" y1="17" x2="12.01" y2="17"/></svg>''',

    'trending-up': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>
        <polyline points="17 6 23 6 23 12"/></svg>''',

    'trending-down': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/>
        <polyline points="17 18 23 18 23 12"/></svg>''',

    'minus': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <line x1="5" y1="12" x2="19" y2="12"/></svg>''',

    'droplets': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <path d="M7 16.3c2.2 0 4-1.83 4-4.05 0-1.16-.57-2.26-1.71-3.19S7.29 6.75 7
            5c-1.18 1.29-3 2.7-3 5.25.05 2.22 1.8 4.05 3 4.05z"/>
        <path d="M12.56 6.6A10.97 10.97 0 0 0 14 3.02c.5 2.5 2 4.9 3 6.88 2.29 4
            .73 5 1 7.5.3 1.18.07 2.87-.42 3.97"/></svg>''',

    'person-walking': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <circle cx="13" cy="4" r="1"/>
        <path d="M7 21l3-6 2 2 2-4"/>
        <path d="M17.5 15.5L12 14l2-5.5-2.5-1L9 12l-3 1.5"/>
        <path d="M10.5 8.5l2.5-1.5"/></svg>''',

    'x': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <line x1="18" y1="6" x2="6" y2="18"/>
        <line x1="6" y1="6" x2="18" y2="18"/></svg>''',

    'minus-square': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
        <line x1="8" y1="12" x2="16" y2="12"/></svg>''',

    'maximize-2': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/>
        <line x1="21" y1="3" x2="14" y2="10"/>
        <line x1="3" y1="21" x2="10" y2="14"/></svg>''',

    'minimize-2': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round">
        <polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/>
        <line x1="10" y1="14" x2="3" y2="21"/>
        <line x1="21" y1="3" x2="14" y2="10"/></svg>''',
}


def icon(name: str, size: int = 16, color: str = None) -> QPixmap:
    """Render a Lucide SVG icon. Falls back to colored dot if QtSvg unavailable."""
    col = color or T['text2']
    svg = _ICONS.get(name, _ICONS['eye']).replace(
        'stroke="currentColor"', f'stroke="{col}"')
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    try:
        from PyQt6.QtSvg import QSvgRenderer
        renderer = QSvgRenderer(QByteArray(svg.encode()))
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(p)
        p.end()
    except Exception:
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(col))
        p.setPen(Qt.PenStyle.NoPen)
        r = size // 2 - 2
        p.drawEllipse(size//2 - r, size//2 - r, r*2, r*2)
        p.end()
    return px


def icon_label(name: str, size: int = 16, color: str = None) -> QLabel:
    """Return a QLabel containing an SVG icon pixmap."""
    lbl = QLabel()
    lbl.setPixmap(icon(name, size, color))
    lbl.setFixedSize(size, size)
    lbl.setStyleSheet("background:transparent;border:none;")
    return lbl


# ── GLOBAL STYLESHEET ─────────────────────────────────────────────────────────
def global_stylesheet() -> str:
    """
    Returns a comprehensive QSS stylesheet for the entire application.
    Apply once via app.setStyleSheet(global_stylesheet()).
    """
    return f"""
/* ── Base ─────────────────────────────────────────────────────────────── */
* {{
    font-family: '{_FONT_FAMILY}';
    font-size: {FS['base']}px;
    color: {T['text']};
    outline: none;
}}

QWidget {{
    background: {T['bg']};
    color: {T['text']};
}}

QMainWindow, QDialog {{
    background: {T['bg']};
}}

/* ── Scrollbars ────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {T['border2']};
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {T['text3']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
}}
QScrollBar::handle:horizontal {{
    background: {T['border2']};
    border-radius: 3px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Input fields ──────────────────────────────────────────────────────── */
QLineEdit {{
    background: {T['surface2']};
    color: {T['text']};
    border: 1px solid {T['border']};
    border-radius: 8px;
    padding: 0 14px;
    font-size: {FS['base']}px;
    selection-background-color: {T['accent_dim']};
}}
QLineEdit:focus {{
    border-color: {T['accent']};
    background: {T['surface']};
}}
QLineEdit::placeholder {{
    color: {T['text3']};
}}
QLineEdit:disabled {{
    color: {T['text3']};
    border-color: {T['surface2']};
}}

/* ── Combo boxes ───────────────────────────────────────────────────────── */
QComboBox {{
    background: {T['surface2']};
    color: {T['text']};
    border: 1px solid {T['border']};
    border-radius: 8px;
    padding: 0 12px;
    font-size: {FS['base']}px;
}}
QComboBox:hover {{
    border-color: {T['border2']};
}}
QComboBox:focus {{
    border-color: {T['accent']};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {T['text3']};
    width: 0;
    height: 0;
}}
QComboBox QAbstractItemView {{
    background: {T['surface']};
    color: {T['text']};
    border: 1px solid {T['border2']};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {T['accent_dim']};
    selection-color: {T['accent']};
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 12px;
    border-radius: 4px;
    min-height: 28px;
}}

/* ── Buttons ───────────────────────────────────────────────────────────── */
QPushButton {{
    background: {T['surface2']};
    color: {T['text']};
    border: 1px solid {T['border']};
    border-radius: 8px;
    padding: 0 16px;
    font-size: {FS['base']}px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {T['surface3']};
    border-color: {T['border2']};
}}
QPushButton:pressed {{
    background: {T['surface']};
}}
QPushButton:disabled {{
    color: {T['text3']};
    border-color: {T['surface2']};
}}

/* ── Frames / Cards ────────────────────────────────────────────────────── */
QFrame {{
    background: transparent;
}}

/* ── Labels ────────────────────────────────────────────────────────────── */
QLabel {{
    background: transparent;
    color: {T['text']};
    font-size: {FS['base']}px;
}}

/* ── Tab widget ────────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {T['border']};
    border-radius: 8px;
    background: {T['surface']};
}}
QTabBar::tab {{
    background: transparent;
    color: {T['text2']};
    padding: 8px 16px;
    border-bottom: 2px solid transparent;
    font-size: {FS['sm']}px;
    font-weight: 500;
}}
QTabBar::tab:selected {{
    color: {T['accent']};
    border-bottom-color: {T['accent']};
}}
QTabBar::tab:hover {{
    color: {T['text']};
}}

/* ── Table ─────────────────────────────────────────────────────────────── */
QTableWidget {{
    background: {T['surface']};
    color: {T['text']};
    border: 1px solid {T['border']};
    border-radius: 8px;
    gridline-color: {T['border']};
    font-size: {FS['sm']}px;
}}
QTableWidget::item {{
    padding: 8px 12px;
    border: none;
}}
QTableWidget::item:selected {{
    background: {T['accent_dim']};
    color: {T['accent']};
}}
QHeaderView::section {{
    background: {T['surface2']};
    color: {T['text2']};
    padding: 8px 12px;
    border: none;
    border-bottom: 1px solid {T['border']};
    font-size: {FS['xs']}px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

/* ── Progress bar ──────────────────────────────────────────────────────── */
QProgressBar {{
    background: {T['surface2']};
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    font-size: 0px;
}}
QProgressBar::chunk {{
    background: {T['accent']};
    border-radius: 4px;
}}

/* ── Tooltip ───────────────────────────────────────────────────────────── */
QToolTip {{
    background: {T['surface']};
    color: {T['text']};
    border: 1px solid {T['border2']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: {FS['sm']}px;
}}

/* ── Scroll area ───────────────────────────────────────────────────────── */
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

/* ── Message box ───────────────────────────────────────────────────────── */
QMessageBox {{
    background: {T['surface']};
    color: {T['text']};
    font-size: {FS['base']}px;
}}
QMessageBox QLabel {{
    color: {T['text']};
    font-size: {FS['base']}px;
    min-width: 280px;
}}
QMessageBox QPushButton {{
    min-width: 80px;
    min-height: 32px;
}}
"""


# ── CARD HELPER ───────────────────────────────────────────────────────────────
def card_style(radius: int = 12, border: bool = True) -> str:
    b = f"border: 1px solid {T['border']};" if border else "border: none;"
    return (f"background: {T['surface']}; {b} "
            f"border-radius: {radius}px;")


# ── BUTTON STYLES ─────────────────────────────────────────────────────────────
def btn_primary() -> str:
    return f"""
        QPushButton {{
            background: {T['accent']}; color: white;
            border: none; border-radius: 8px;
            font-size: {FS['base']}px; font-weight: 600;
        }}
        QPushButton:hover {{ background: {T['accent2']}; }}
        QPushButton:pressed {{ background: {T['accent2']}; opacity: 0.8; }}
        QPushButton:disabled {{ background: {T['surface2']}; color: {T['text3']}; }}
    """

def btn_ghost() -> str:
    return f"""
        QPushButton {{
            background: transparent; color: {T['text2']};
            border: 1px solid {T['border']}; border-radius: 8px;
            font-size: {FS['base']}px; font-weight: 500;
        }}
        QPushButton:hover {{
            background: {T['surface2']}; color: {T['text']};
            border-color: {T['border2']};
        }}
    """

def btn_danger() -> str:
    return f"""
        QPushButton {{
            background: {T['red']}; color: white;
            border: none; border-radius: 8px;
            font-size: {FS['base']}px; font-weight: 600;
        }}
        QPushButton:hover {{ background: #DA3633; }}
    """