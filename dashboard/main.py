"""
dashboard/main.py
EyeStrain AI — Dashboard
"""

import sys
import os
import json
import random
import threading
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QFrame, QStackedWidget,
    QDialog, QGridLayout, QSizePolicy, QScrollArea,
    QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QTabWidget, QComboBox, QLineEdit,
    QGraphicsDropShadowEffect
)
from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, QPropertyAnimation,
    QEasingCurve, QPoint, QRect, pyqtProperty
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QPainterPath, QPalette, QPixmap, QFontDatabase,
    QMouseEvent, QCursor
)

# ── UI SYSTEM — theme, fonts, icons ──────────────────────────────────────────
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
_sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
try:
    from ui_system import T, FS, font, bold, semibold, icon, icon_label
    from ui_system import global_stylesheet, card_style, btn_primary, btn_ghost, btn_danger
    from ui_system import setup_font
except ImportError:
    # Fallback theme if ui_system not found
    T = {
        'bg': '#0D1117', 'surface': '#161B22', 'surface2': '#1C2128',
        'surface3': '#21262D', 'border': '#30363D', 'border2': '#3D444D',
        'text': '#E6EDF3', 'text2': '#8B949E', 'text3': '#484F58',
        'accent': '#2F81F7', 'accent2': '#1F6FEB', 'accent_dim': '#1C2E45',
        'green': '#3FB950', 'yellow': '#D29922', 'orange': '#DB6D28',
        'red': '#F85149', 'green_dim': '#12261E', 'red_dim': '#2D1317',
        'dark': True,
    }
    FS = {'xs':9,'sm':11,'base':13,'md':15,'lg':18,'xl':24,'xxl':32,'hero':48}
    def font(s=13, w=QFont.Weight.Normal, i=False):
        f = QFont('Segoe UI', s); f.setWeight(w); return f
    def bold(s=13): return font(s, QFont.Weight.Bold)
    def semibold(s=13): return font(s, QFont.Weight.DemiBold)
    def icon(name, size=16, color=None):
        px = QPixmap(size, size); px.fill(Qt.GlobalColor.transparent); return px
    def icon_label(name, size=16, color=None):
        l = QLabel(); l.setPixmap(icon(name,size,color))
        l.setFixedSize(size,size); l.setStyleSheet("background:transparent;"); return l
    def global_stylesheet(): return ""
    def card_style(r=12, b=True): return f"background:{T['surface']};"
    def btn_primary(): return f"QPushButton{{background:{T['accent']};color:white;border:none;border-radius:8px;}}"
    def btn_ghost(): return f"QPushButton{{background:transparent;color:{T['text2']};border:1px solid {T['border']};border-radius:8px;}}"
    def btn_danger(): return f"QPushButton{{background:{T['red']};color:white;border:none;border-radius:8px;}}"
    def setup_font(app): return 'Segoe UI' 

# ── PATHS ─────────────────────────────────────────────────────────────────────
ROOT_DIR    = Path(__file__).parent.parent
DATA_DIR    = ROOT_DIR / 'data'
REPORTS_DIR = ROOT_DIR / 'reports'
PING_PATH   = DATA_DIR / 'profiles' / 'weekly_report_ping.json'
REPORTS_DIR.mkdir(exist_ok=True)

# ── THEME & HELPERS ───────────────────────────────────────────────────────────
# T, FS, font helpers imported from ui_system above
# If ui_system import failed, T and FS are already defined as fallbacks

def make_msgbox(parent, title: str, text: str,
                icon_type=QMessageBox.Icon.Information) -> QMessageBox:
    """Readable QMessageBox using the dark theme."""
    msg = QMessageBox(parent)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setIcon(icon_type)
    msg.setStyleSheet(f"""
        QMessageBox {{
            background: {T['surface']};
        }}
        QMessageBox QLabel {{
            color: {T['text']};
            font-size: {FS['base']}px;
            min-width: 320px;
            padding: 8px 0;
        }}
        QPushButton {{
            background: {T['accent']}; color: white;
            border: none; border-radius: 8px;
            padding: 8px 24px; font-size: {FS['base']}px;
            font-weight: 600; min-width: 80px;
        }}
        QPushButton:hover {{ background: {T['accent2']}; }}
    """)
    return msg

# ── DOWNLOAD PATH HELPER ──────────────────────────────────────────────────────
def get_save_path(parent, title: str, default_name: str,
                  filter_str: str) -> str:
    """
    Open a Save File dialog starting at Desktop (fallback: Downloads, home).
    Returns the chosen path as string, or '' if cancelled.
    """
    desktop   = Path.home() / 'Desktop'
    downloads = Path.home() / 'Downloads'
    start_dir = str(desktop if desktop.exists() else
                    downloads if downloads.exists() else
                    Path.home())
    path, _ = QFileDialog.getSaveFileName(
        parent, title,
        str(Path(start_dir) / default_name),
        filter_str
    )
    return path

# ── VERIFY WINDOWS ────────────────────────────────────────────────────────────
VERIFY_WINDOWS = {
    '20-20-20 Rule': 40,
    'Eye Drops':     60,
    'Neck Stretch':  45,
    'Stand & Walk':  120,
}

ACTION_ICONS = {
    '20-20-20 Rule': 'eye',
    'Eye Drops':     'droplets',
    'Neck Stretch':  'activity',
    'Stand & Walk':  'person-walking',
}

ACTION_INSTRUCTIONS = {
    '20-20-20 Rule': 'Look at something 20 feet away and let your eyes relax',
    'Eye Drops':     'Blink rapidly 20 times — camera will count each blink',
    'Neck Stretch':  'Tilt your head right, then left — camera checks both',
    'Stand & Walk':  'Step away from your screen — camera detects you leaving',
}

ACTION_NUDGES = {
    '20-20-20 Rule': 'Hold your gaze away for longer — need 20 continuous seconds',
    'Eye Drops':     'Blink more rapidly — need 20 blinks total',
    'Neck Stretch':  'Turn your head further to each side (need 15+ degrees)',
    'Stand & Walk':  'Move completely out of camera view for 20 seconds',
}

TIER_CONFIG = {
    'Gold':   {'icon': 'G',  'color': '#D29922', 'border': '#D29922', 'points': 50},
    'Silver': {'icon': 'S',  'color': '#8B949E', 'border': '#8B949E', 'points': 25},
    'Bronze': {'icon': 'B',  'color': '#DB6D28', 'border': '#DB6D28', 'points': 10},
}

# ── STRAIN HELPERS ────────────────────────────────────────────────────────────
def strain_color(vfq):
    if vfq < 20: return T['green']
    if vfq < 40: return '#84CC16'
    if vfq < 60: return T['yellow']
    if vfq < 80: return T['orange']
    return T['red']

def strain_label_from_vfq(vfq):
    if vfq < 20: return 'NORMAL'
    if vfq < 40: return 'LOW'
    if vfq < 60: return 'MODERATE'
    if vfq < 80: return 'HIGH'
    return 'SEVERE'

STRAIN_LEVELS = ['NORMAL', 'LOW', 'MODERATE', 'HIGH', 'SEVERE']
STRAIN_COLORS = ['#10B981', '#84CC16', '#F59E0B', '#F97316', '#EF4444']

# ── MOCK PIPELINE ─────────────────────────────────────────────────────────────
class MockPipeline:
    def __init__(self):
        self.vfq        = 25.0
        self.blink_rate = 9.5
        self.trend      = 'STABLE'

    def update(self):
        self.vfq        = max(0, min(100, self.vfq + random.gauss(0, 2)))
        self.blink_rate = max(2, min(20, self.blink_rate + random.gauss(0, 0.3)))
        self.trend      = ('WORSENING' if self.vfq > 50
                           else 'IMPROVING' if self.vfq < 25 else 'STABLE')
        return {
            'vfq_score':    self.vfq,
            'blink_rate':   self.blink_rate,
            'strain_trend': self.trend,
            'strain_label': strain_label_from_vfq(self.vfq),
        }

# ── CUSTOM WIDGETS ────────────────────────────────────────────────────────────

class VFQGauge(QWidget):
    """
    VFQ arc gauge with QPropertyAnimation for fluid value transitions.
    EasingCurve.OutCubic gives a natural deceleration feel.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value  = 0.0
        self.setMinimumSize(200, 200)
        self.setMaximumSize(200, 200)
        # QPropertyAnimation on the custom 'value' property
        self._anim = QPropertyAnimation(self, b"value")
        self._anim.setDuration(600)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def get_value(self): return self._value
    def set_value_prop(self, v):
        self._value = float(v)
        self.update()
    value = pyqtProperty(float, get_value, set_value_prop)

    def set_value(self, v):
        """Animate to new value."""
        target = max(0.0, min(100.0, float(v)))
        if self._anim.state() == QPropertyAnimation.State.Running:
            self._anim.stop()
        self._anim.setStartValue(self._value)
        self._anim.setEndValue(target)
        self._anim.start()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h   = self.width(), self.height()
        cx, cy = w // 2, h // 2
        r      = min(w, h) // 2 - 16
        pen_w  = 12
        # Background arc
        p.setPen(QPen(QColor(T['surface2']), pen_w,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(cx-r, cy-r, r*2, r*2, 225*16, -270*16)
        # Value arc
        color = QColor(strain_color(self._value))
        angle = int((self._value / 100.0) * 270 * 16)
        if angle > 0:
            p.setPen(QPen(color, pen_w,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(cx-r, cy-r, r*2, r*2, 225*16, -angle)
        # Value number
        p.setPen(QColor(T['text']))
        f = QFont('Segoe UI', 28, QFont.Weight.Bold)
        f.setStyleHint(QFont.StyleHint.SansSerif)
        p.setFont(f)
        p.drawText(0, cy-24, w, 36, Qt.AlignmentFlag.AlignCenter,
                   f"{int(self._value)}")
        # VFQ Score label
        p.setPen(QColor(T['text3']))
        f2 = QFont('Segoe UI', 9)
        f2.setStyleHint(QFont.StyleHint.SansSerif)
        p.setFont(f2)
        p.drawText(0, cy+12, w, 20, Qt.AlignmentFlag.AlignCenter, 'VFQ Score')
        # Strain label
        p.setPen(QColor(strain_color(self._value)))
        f3 = QFont('Segoe UI', 10, QFont.Weight.Bold)
        f3.setStyleHint(QFont.StyleHint.SansSerif)
        p.setFont(f3)
        p.drawText(0, cy+28, w, 20, Qt.AlignmentFlag.AlignCenter,
                   strain_label_from_vfq(self._value))
        p.end()


class MiniChart(QWidget):
    def __init__(self, max_points=120, parent=None):
        super().__init__(parent)
        self.max_points = max_points
        self.data       = []
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def add_point(self, v):
        self.data.append(max(0.0, min(100.0, v)))
        if len(self.data) > self.max_points:
            self.data.pop(0)
        self.update()

    def clear(self):
        self.data = []
        self.update()

    def paintEvent(self, event):
        if len(self.data) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pad  = 12
        ch   = h - pad * 2
        cw   = w - pad * 2
        n    = len(self.data)
        for lo, hi, col in [
            (0, 20, '#10B98115'), (20, 40, '#84CC1615'),
            (40, 60, '#F59E0B15'), (60, 80, '#F9731615'), (80, 100, '#EF444415')
        ]:
            y1 = pad + ch * (1 - hi/100)
            y2 = pad + ch * (1 - lo/100)
            p.fillRect(int(pad), int(y1), int(cw), int(y2-y1), QColor(col))
        path = QPainterPath()
        for i, v in enumerate(self.data):
            x = pad + (i / (n-1)) * cw
            y = pad + ch * (1 - v/100)
            if i == 0: path.moveTo(x, y)
            else:      path.lineTo(x, y)
        last_v = self.data[-1]
        color  = QColor(strain_color(last_v))
        p.setPen(QPen(color, 2, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
        lx = pad + cw
        ly = pad + ch * (1 - last_v/100)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(color))
        p.drawEllipse(int(lx-4), int(ly-4), 8, 8)
        p.end()


class PieChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = []
        self.setMinimumSize(160, 160)
        self.setMaximumSize(180, 180)

    def set_data(self, values, colors):
        self.data = list(zip(values, colors))
        self.update()

    def paintEvent(self, event):
        if not self.data:
            return
        p      = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h   = self.width(), self.height()
        r      = min(w, h) // 2 - 8
        cx, cy = w // 2, h // 2
        total  = sum(v for v, _ in self.data) or 1
        angle  = 90 * 16
        for val, color in self.data:
            span = int((val / total) * 360 * 16)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(color)))
            p.drawPie(cx-r, cy-r, r*2, r*2, angle, -span)
            angle -= span
        p.setBrush(QBrush(QColor(T['surface'])))
        p.setPen(Qt.PenStyle.NoPen)
        inner = int(r * 0.55)
        p.drawEllipse(cx-inner, cy-inner, inner*2, inner*2)
        p.end()


class StatCard(QFrame):
    def __init__(self, label, value='--', unit='', color=None, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(f"""
            QFrame {{
                background: {T['surface']};
                border: 1px solid {T['border']};
                border-radius: 12px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        self._label_w = QLabel(label)
        self._label_w.setStyleSheet(f"color:{T['text2']}; font-size:11px; border:none;")
        self._value_w = QLabel(value)
        self._value_w.setStyleSheet(
            f"color:{color or T['text']}; font-size:22px; font-weight:700; border:none;")
        self._unit_w = QLabel(unit)
        self._unit_w.setStyleSheet(f"color:{T['text3']}; font-size:10px; border:none;")
        layout.addWidget(self._label_w)
        layout.addWidget(self._value_w)
        layout.addWidget(self._unit_w)

    def set_value(self, v, color=None):
        self._value_w.setText(str(v))
        if color:
            self._value_w.setStyleSheet(
                f"color:{color}; font-size:22px; font-weight:700; border:none;")


class NavButton(QPushButton):
    """Sidebar navigation button. Minimal, no emojis — just label."""
    def __init__(self, icon_name, label, parent=None):
        super().__init__(parent)
        self._label    = label
        self._icon_name = icon_name
        self.setText(label)
        self.setCheckable(True)
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style(False)

    def _update_style(self, active):
        if active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {T['accent_dim']}; color: {T['accent']};
                    border: none; border-left: 2px solid {T['accent']};
                    border-radius: 0px;
                    font-size: 13px; font-weight: 600;
                    text-align: left; padding-left: 16px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {T['text2']};
                    border: none; border-left: 2px solid transparent;
                    border-radius: 0px;
                    font-size: 13px; font-weight: 400;
                    text-align: left; padding-left: 16px;
                }}
                QPushButton:hover {{
                    background: {T['surface2']}; color: {T['text']};
                }}
            """)

    def setChecked(self, v):
        super().setChecked(v)
        self._update_style(v)


def make_progress_bar(color, height=8):
    bar = QProgressBar()
    bar.setMinimum(0); bar.setMaximum(100); bar.setValue(0)
    bar.setTextVisible(False); bar.setFixedHeight(height)
    bar.setStyleSheet(f"""
        QProgressBar {{ background:{T['surface2']}; border-radius:{height//2}px; border:none; }}
        QProgressBar::chunk {{ background:{color}; border-radius:{height//2}px; }}
    """)
    return bar

def update_bar_color(bar, color):
    bar.setStyleSheet(f"""
        QProgressBar {{ background:{T['surface2']}; border-radius:4px; border:none; }}
        QProgressBar::chunk {{ background:{color}; border-radius:4px; }}
    """)


# ── RECOVERY POPUP ────────────────────────────────────────────────────────────
class RecoveryPopup(QDialog):
    ACTIONS = [
        ("",   "20-20-20 Rule",  "Look 20ft away for 20 seconds"),
        ("",   "Eye Drops",       "Blink rapidly 20 times"),
        ("",   "Neck Stretch",    "Tilt head right and left"),
        ("",   "Stand & Walk",    "Step away from screen"),
    ]

    def __init__(self, vfq_at_trigger, parent=None):
        super().__init__(parent)
        self.vfq_at_trigger   = vfq_at_trigger
        self._selected_action = None
        self.setWindowTitle("Break Time")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setModal(True)
        self.setFixedWidth(400)
        self.setStyleSheet(f"""
            QDialog {{ background:{T['surface']}; border:1px solid {T['border']}; border-radius:16px; }}
        """)
        self.setWindowOpacity(0.0)
        self._build_ui()
        self._fade_op = 0.0
        self._fade_t  = QTimer(self)
        self._fade_t.timeout.connect(self._fade_step)
        self._fade_t.start(16)

    def _fade_step(self):
        self._fade_op = min(1.0, self._fade_op + 0.07)
        self.setWindowOpacity(self._fade_op)
        if self._fade_op >= 1.0:
            self._fade_t.stop()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        header = QLabel("Break Reminder")
        header.setStyleSheet(f"color:{T['text']}; font-size:15px; font-weight:700;")
        layout.addWidget(header)

        sub = QLabel(
            f"VFQ {int(self.vfq_at_trigger)} — {strain_label_from_vfq(self.vfq_at_trigger)} strain detected.")
        sub.setStyleSheet(f"color:{T['text2']}; font-size:12px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        div = QFrame(); div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"color:{T['border']};")
        layout.addWidget(div)

        action_lbl = QLabel("Select a recovery action")
        action_lbl.setStyleSheet(f"color:{T['text']}; font-size:13px; font-weight:600;")
        layout.addWidget(action_lbl)

        for icon, name, desc in self.ACTIONS:
            btn = QPushButton(f"{name}  —  {desc}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background:{T['surface2']}; color:{T['text']};
                    border:1px solid {T['border']}; border-radius:10px;
                    padding:10px 14px; font-size:12px; text-align:left;
                }}
                QPushButton:hover {{
                    background:{T['accent_dim']}; border-color:{T['accent']}; color:{T['accent']};
                }}
            """)
            btn.clicked.connect(lambda _, n=name: self._on_action(n))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            layout.addWidget(btn)

    def _on_action(self, action_name):
        self._selected_action = action_name
        self.accept()

    def get_selected_action(self):
        return self._selected_action


# ── INTERVENTION SCREEN ───────────────────────────────────────────────────────
class InterventionScreen(QDialog):
    closed_signal = pyqtSignal(str)

    def __init__(self, action, vfq_at_trigger, parent=None):
        super().__init__(parent)
        self.action          = action
        self.vfq_at_trigger  = vfq_at_trigger
        self._current_vfq    = vfq_at_trigger
        self._best_drop      = 0.0
        self._verify_elapsed = 0
        self._verify_window  = VERIFY_WINDOWS.get(action, 60)
        self._recovered      = False
        self._tier           = None
        self._flash_done     = False

        self.setWindowTitle("Recovery in Progress")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setModal(True)
        self.setFixedWidth(440)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowOpacity(0.0)
        self.setStyleSheet(f"""
            QDialog {{ background:{T['surface']}; border:2px solid {T['accent']}; border-radius:16px; }}
        """)
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(28, 24, 28, 24)
        self._main_layout.setSpacing(14)
        self._build_normal_view()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

        self._fade_opacity = 0.0
        self._fade_timer   = QTimer(self)
        self._fade_timer.timeout.connect(self._fade_in_step)
        self._fade_timer.start(16)

    def _build_normal_view(self):
        L = self._main_layout

        icon_lbl = icon_label(ACTION_ICONS.get(self.action, 'eye'), 40, T['accent'])
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        L.addWidget(icon_lbl)

        action_lbl = QLabel(self.action)
        action_lbl.setStyleSheet(f"color:{T['text']}; font-size:18px; font-weight:700;")
        action_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        L.addWidget(action_lbl)

        instr = QLabel(ACTION_INSTRUCTIONS.get(self.action, ''))
        instr.setStyleSheet(f"color:{T['text2']}; font-size:12px;")
        instr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instr.setWordWrap(True)
        L.addWidget(instr)

        L.addWidget(self._divider())

        cam_header = QHBoxLayout()
        cam_lbl = QLabel("Camera Verification")
        cam_lbl.setStyleSheet(f"color:{T['text']}; font-size:12px; font-weight:600;")
        self._conf_pct_lbl = QLabel("0%")
        self._conf_pct_lbl.setStyleSheet(f"color:{T['text3']}; font-size:12px; font-weight:700;")
        cam_header.addWidget(cam_lbl); cam_header.addStretch(); cam_header.addWidget(self._conf_pct_lbl)
        L.addLayout(cam_header)

        self._conf_bar = make_progress_bar(T['text3'], height=10)
        L.addWidget(self._conf_bar)

        self._status_lbl = QLabel("Waiting — perform the action")
        self._status_lbl.setStyleSheet(f"color:{T['text3']}; font-size:12px; font-weight:500;")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setWordWrap(True)
        L.addWidget(self._status_lbl)

        L.addWidget(self._divider())

        vfq_row = QHBoxLayout()
        vfq_lbl = QLabel("Live Eye Strain")
        vfq_lbl.setStyleSheet(f"color:{T['text']}; font-size:12px; font-weight:600;")
        self._vfq_val_lbl = QLabel(f"{int(self.vfq_at_trigger)}")
        self._vfq_val_lbl.setStyleSheet(
            f"color:{strain_color(self.vfq_at_trigger)}; font-size:12px; font-weight:700;")
        vfq_row.addWidget(vfq_lbl); vfq_row.addStretch(); vfq_row.addWidget(self._vfq_val_lbl)
        L.addLayout(vfq_row)

        self._vfq_bar = make_progress_bar(strain_color(self.vfq_at_trigger))
        self._vfq_bar.setValue(int(min(100, self.vfq_at_trigger)))
        L.addWidget(self._vfq_bar)

        self._drop_lbl = QLabel("VFQ drop: 0 pts")
        self._drop_lbl.setStyleSheet(f"color:{T['text3']}; font-size:11px;")
        self._drop_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        L.addWidget(self._drop_lbl)

    def _divider(self):
        d = QFrame(); d.setFrameShape(QFrame.Shape.HLine)
        d.setStyleSheet(f"background:{T['border']}; max-height:1px;")
        return d

    def _fade_in_step(self):
        self._fade_opacity = min(1.0, self._fade_opacity + 0.06)
        self.setWindowOpacity(self._fade_opacity)
        if self._fade_opacity >= 1.0:
            self._fade_timer.stop()

    def _fade_out_then_close(self, reason: str):
        if hasattr(self, '_fading_out'):
            return
        self._fading_out = True

        def step():
            op = self.windowOpacity() - 0.08
            if op <= 0:
                self._fade_out_timer.stop()
                self.closed_signal.emit(reason)
                self.close()
            else:
                self.setWindowOpacity(op)

        self._fade_out_timer = QTimer(self)
        self._fade_out_timer.timeout.connect(step)
        self._fade_out_timer.start(16)

    def update_vfq(self, vfq: float):
        if self._recovered:
            return
        self._current_vfq = vfq
        drop = self.vfq_at_trigger - vfq
        if drop > self._best_drop:
            self._best_drop = drop
        color = strain_color(vfq)
        self._vfq_val_lbl.setText(f"{int(vfq)}")
        self._vfq_val_lbl.setStyleSheet(f"color:{color}; font-size:12px; font-weight:700;")
        self._vfq_bar.setValue(max(0, min(100, int(vfq))))
        update_bar_color(self._vfq_bar, color)
        if drop > 0:
            self._drop_lbl.setText(f"VFQ drop: {drop:.0f} pts")
            self._drop_lbl.setStyleSheet(f"color:{T['green']}; font-size:11px; font-weight:600;")
        else:
            self._drop_lbl.setText("VFQ drop: 0 pts")
            self._drop_lbl.setStyleSheet(f"color:{T['text3']}; font-size:11px;")

    def update_action_confidence(self, confidence: float,
                                  action_verified: bool,
                                  status_text: str = ""):
        if self._recovered:
            return
        pct = int(confidence * 100)
        self._conf_pct_lbl.setText(f"{pct}%")
        self._conf_bar.setValue(pct)

        if action_verified:
            self._conf_pct_lbl.setStyleSheet(f"color:{T['green']}; font-size:12px; font-weight:700;")
            update_bar_color(self._conf_bar, T['green'])
            self._status_lbl.setStyleSheet(f"color:{T['green']}; font-size:12px; font-weight:700;")
            if not self._flash_done:
                self._flash_done = True
                self._timer.stop()
                self._status_lbl.setText("Verified — closing...")
                drop = self.vfq_at_trigger - self._current_vfq
                QTimer.singleShot(1000, lambda: self._show_verified_flash(drop))
        elif confidence >= 0.5:
            self._conf_pct_lbl.setStyleSheet(f"color:{T['yellow']}; font-size:12px; font-weight:700;")
            update_bar_color(self._conf_bar, T['yellow'])
            self._status_lbl.setStyleSheet(f"color:{T['yellow']}; font-size:12px;")
        elif confidence > 0:
            self._conf_pct_lbl.setStyleSheet(f"color:{T['orange']}; font-size:12px; font-weight:700;")
            update_bar_color(self._conf_bar, T['orange'])
            self._status_lbl.setStyleSheet(f"color:{T['orange']}; font-size:12px;")
        else:
            self._conf_pct_lbl.setStyleSheet(f"color:{T['text3']}; font-size:12px; font-weight:700;")
            update_bar_color(self._conf_bar, T['text3'])
            self._status_lbl.setStyleSheet(f"color:{T['text3']}; font-size:12px;")

        if status_text and not self._flash_done:
            self._status_lbl.setText(status_text)

    def _show_verified_flash(self, drop: float):
        if self._recovered:
            return
        tier = self._tier or {
            'name': 'Bronze', 'icon': '',
            'color': '#B45309', 'border': '#D97706', 'points': 10,
        }
        self.on_recovery_confirmed(tier, drop)

    def _tick(self):
        if self._recovered:
            return
        self._verify_elapsed += 1
        if self._verify_elapsed >= self._verify_window:
            self._on_verify_expired()

    def on_recovery_confirmed(self, tier: dict, drop: float):
        if self._recovered:
            return
        self._recovered = True
        self._tier      = tier
        self._timer.stop()
        self._show_reward_view(tier, drop)

    def _show_reward_view(self, tier: dict, drop: float):
        while self._main_layout.count():
            item = self._main_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        tier_lbl = QLabel(tier['name'] + " Recovery")
        tier_lbl.setStyleSheet(f"color:{tier['color']}; font-size:20px; font-weight:700;")
        tier_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._main_layout.addWidget(tier_lbl)
        action_r = QLabel(self.action)
        action_r.setStyleSheet(f"color:{T['text2']}; font-size:12px;")
        action_r.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._main_layout.addWidget(action_r)

        if drop > 0:
            dl = QLabel(f"VFQ dropped {drop:.0f} points")
            dl.setStyleSheet(f"color:{T['text2']}; font-size:13px;")
            dl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._main_layout.addWidget(dl)

        pl = QLabel(f"+{tier['points']} points earned")
        pl.setStyleSheet(f"color:{tier['color']}; font-size:15px; font-weight:700;")
        pl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._main_layout.addWidget(pl)

        cl = QLabel("Closing automatically...")
        cl.setStyleSheet(f"color:{T['text3']}; font-size:11px;")
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._main_layout.addWidget(cl)

        self.setStyleSheet(f"""
            QDialog {{ background:{T['surface']}; border:2px solid {tier['border']}; border-radius:16px; }}
        """)
        self.adjustSize()
        QTimer.singleShot(3000, lambda: self._fade_out_then_close('completed'))

    def _on_verify_expired(self):
        self._timer.stop()
        if self._recovered:
            return
        nudge = ACTION_NUDGES.get(self.action, 'Try again next time')
        self._status_lbl.setText(nudge)
        self._status_lbl.setStyleSheet(f"color:{T['yellow']}; font-size:11px;")
        QTimer.singleShot(3000, lambda: self._fade_out_then_close('expired'))


# ── LIVE SCREEN ───────────────────────────────────────────────────────────────
class LiveScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(16)

        title = QLabel("Live Monitor")
        title.setStyleSheet(f"color:{T['text']}; font-size:20px; font-weight:700;")
        layout.addWidget(title)

        top_row = QHBoxLayout(); top_row.setSpacing(16)

        # ── Two gauges side by side ───────────────────────────────────────────
        gauges_row = QHBoxLayout(); gauges_row.setSpacing(12)

        # Clinical gauge (absolute VFQ 0-100)
        clinical_card = QFrame()
        clinical_card.setStyleSheet(
            f"QFrame{{background:{T['surface']};border:1px solid {T['border']};border-radius:14px;}}")
        cl_lay = QVBoxLayout(clinical_card)
        cl_lay.setContentsMargins(12, 12, 12, 12)
        cl_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl_hdr = QLabel("Clinical VFQ")
        cl_hdr.setStyleSheet(f"color:{T['text3']}; font-size:10px; font-weight:600; letter-spacing:1px;")
        cl_hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl_lay.addWidget(cl_hdr)
        self.gauge = VFQGauge()
        cl_lay.addWidget(self.gauge, alignment=Qt.AlignmentFlag.AlignCenter)
        self._clinical_note = QLabel("NORMAL")
        self._clinical_note.setStyleSheet(
            f"color:{T['green']}; font-size:11px; font-weight:700;")
        self._clinical_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl_lay.addWidget(self._clinical_note)
        gauges_row.addWidget(clinical_card)

        # Personal gauge (relative to user's baseline threshold)
        personal_card = QFrame()
        personal_card.setStyleSheet(
            f"QFrame{{background:{T['surface']};border:1px solid {T['border']};border-radius:14px;}}")
        pr_lay = QVBoxLayout(personal_card)
        pr_lay.setContentsMargins(12, 12, 12, 12)
        pr_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pr_hdr = QLabel("Personal VFQ")
        pr_hdr.setStyleSheet(f"color:{T['text3']}; font-size:10px; font-weight:600; letter-spacing:1px;")
        pr_hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pr_lay.addWidget(pr_hdr)
        self.personal_gauge = VFQGauge()
        pr_lay.addWidget(self.personal_gauge, alignment=Qt.AlignmentFlag.AlignCenter)
        self._personal_note = QLabel("—")
        self._personal_note.setStyleSheet(
            f"color:{T['text3']}; font-size:11px; font-weight:700;")
        self._personal_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pr_lay.addWidget(self._personal_note)
        gauges_row.addWidget(personal_card)

        gauge_wrap = QFrame()
        gauge_wrap.setStyleSheet(
            f"QFrame{{background:{T['surface']};border:1px solid {T['border']};border-radius:16px;}}")
        gwl = QVBoxLayout(gauge_wrap); gwl.setContentsMargins(8,8,8,8); gwl.setSpacing(8)
        gwl.addLayout(gauges_row)

        trend_row = QHBoxLayout()
        self.trend_label = QLabel("STABLE")
        self.trend_label.setStyleSheet(f"color:{T['text2']}; font-size:12px; font-weight:600;")
        trend_row.addStretch(); trend_row.addWidget(self.trend_label); trend_row.addStretch()
        gwl.addLayout(trend_row)

        self.tcn_label_w = QLabel("Model: --")
        self.tcn_label_w.setStyleSheet(f"color:{T['text3']}; font-size:11px;")
        tr2 = QHBoxLayout()
        tr2.addStretch(); tr2.addWidget(self.tcn_label_w); tr2.addStretch()
        gwl.addLayout(tr2)
        top_row.addWidget(gauge_wrap)

        stats_widget = QWidget()
        stats_grid   = QGridLayout(stats_widget); stats_grid.setSpacing(10)
        self.blink_card   = StatCard("Blink Rate",    "--",  "/min", T['accent'])
        self.timer_card   = StatCard("Session Time",  "0:00","",     T['text'])
        self.reward_card  = StatCard("Reward Points", "0",   "pts",  T['green'])
        self.prevent_card = StatCard("Strain Saved",  "--",  "min",  T['yellow'])
        stats_grid.addWidget(self.blink_card,   0, 0)
        stats_grid.addWidget(self.timer_card,   0, 1)
        stats_grid.addWidget(self.reward_card,  1, 0)
        stats_grid.addWidget(self.prevent_card, 1, 1)
        top_row.addWidget(stats_widget)
        layout.addLayout(top_row)

        chart_card = QFrame()
        chart_card.setStyleSheet(f"""
            QFrame {{ background:{T['surface']}; border:1px solid {T['border']}; border-radius:16px; }}
        """)
        cl = QVBoxLayout(chart_card); cl.setContentsMargins(16, 12, 16, 12)
        ch_header = QHBoxLayout()
        chart_lbl = QLabel("VFQ — Current Session")
        chart_lbl.setStyleSheet(f"color:{T['text']}; font-size:13px; font-weight:600;")
        self.live_lbl = QLabel("LIVE")
        self.live_lbl.setStyleSheet(f"color:{T['red']}; font-size:11px;")
        ch_header.addWidget(chart_lbl); ch_header.addStretch(); ch_header.addWidget(self.live_lbl)
        cl.addLayout(ch_header)
        self.chart = MiniChart(max_points=180)
        cl.addWidget(self.chart)
        layout.addWidget(chart_card)

    def set_personal_threshold(self, threshold):
        """Called by Dashboard after login to set user's personal VFQ threshold."""
        self._personal_threshold = threshold

    def update_data(self, data):
        vfq   = float(data.get('vfq_score', 0) or 0)
        blink = float(data.get('blink_rate', 0) or 0)
        trend = data.get('strain_trend', 'STABLE') or 'STABLE'
        label = data.get('strain_label', 'NORMAL') or 'NORMAL'

        # Clinical gauge — absolute scale 0-100
        self.gauge.set_value(vfq)
        color = strain_color(vfq)
        self._clinical_note.setText(label)
        self._clinical_note.setStyleSheet(
            f"color:{color}; font-size:11px; font-weight:700;")

        # Personal gauge — shows how close user is to THEIR personal threshold
        # Scale: 0 = no strain, 100 = at personal threshold (break fires here)
        # So gauge at 100 = break reminder fires. Past 100 = overdue for break.
        pt = getattr(self, '_personal_threshold', None)
        if pt and pt > 0:
            # Scale: 0-100 where 50 = at personal threshold, 100 = 2x threshold
            # This way the gauge visually shows "halfway" when break is due
            # VFQ=37, threshold=33.5 → ratio=1.1 → pct=55 → Near threshold ✓
            # VFQ=20, threshold=33.5 → ratio=0.6 → pct=30 → Within normal range ✓
            ratio        = vfq / pt          # 0.0 = no strain, 1.0 = at threshold
            personal_pct = min(100, ratio * 50)  # 50% gauge = at threshold
            self.personal_gauge.set_value(personal_pct)
            if ratio < 0.6:
                pnote, pcol = "Within normal range", T['green']
            elif ratio < 0.85:
                pnote, pcol = "Approaching threshold", T['yellow']
            elif ratio < 1.0:
                pnote, pcol = "Near your threshold", '#F97316'
            else:
                pnote, pcol = "Above your threshold", T['red']
            self._personal_note.setText(pnote)
            self._personal_note.setStyleSheet(
                f"color:{pcol}; font-size:11px; font-weight:700;")
        else:
            self.personal_gauge.set_value(0)
            self._personal_note.setText("No baseline yet")
            self._personal_note.setStyleSheet(
                f"color:{T['text3']}; font-size:11px;")

        self.blink_card.set_value(f"{blink:.1f}", T['accent'])
        colors = {'IMPROVING': T['green'], 'STABLE': T['text2'], 'WORSENING': T['red']}
        self.trend_label.setText(trend)
        self.trend_label.setStyleSheet(
            f"color:{colors.get(trend, T['text2'])}; font-size:12px; font-weight:600;")

    def update_timer(self, seconds):
        m, s = divmod(seconds, 60)
        self.timer_card.set_value(f"{m}:{s:02d}")

    def update_rewards(self, points):
        self.reward_card.set_value(str(points), T['green'])

    def update_prevented(self, minutes):
        self.prevent_card.set_value(f"{minutes:.0f}", T['yellow'])

    def update_tcn_prediction(self, label, probs):
        if not hasattr(self, 'tcn_label_w'):
            return
        self.tcn_label_w.setText(f"Model: {label}")
        color = strain_color(
            [0, 20, 40, 60, 80][
                ['NORMAL', 'LOW', 'MODERATE', 'HIGH', 'SEVERE'].index(label)
                if label in ['NORMAL', 'LOW', 'MODERATE', 'HIGH', 'SEVERE'] else 0
            ]
        )
        self.tcn_label_w.setStyleSheet(f"color:{color}; font-size:12px; font-weight:600;")


# ── ANALYTICS SCREEN ──────────────────────────────────────────────────────────
class AnalyticsScreen(QWidget):
    def __init__(self, user_id='user_001', parent=None):
        super().__init__(parent)
        self._user_id            = user_id
        self._session_recoveries = 0
        self._build_ui()

    def set_user(self, user_id: str):
        self._user_id = user_id

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 20, 28, 20)
        outer.setSpacing(12)

        title = QLabel("Analytics")
        title.setStyleSheet(f"color:{T['text']}; font-size:20px; font-weight:700;")
        outer.addWidget(title)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ background:transparent; border:none; }}
            QTabBar::tab {{
                background:{T['surface2']}; color:{T['text2']};
                border:1px solid {T['border']}; border-radius:8px;
                padding:8px 24px; margin-right:6px;
                font-size:13px; font-weight:600;
            }}
            QTabBar::tab:selected {{ background:{T['accent']}; color:white; border-color:{T['accent']}; }}
            QTabBar::tab:hover:!selected {{ background:{T['surface']}; color:{T['text']}; }}
        """)

        self._tabs.addTab(self._build_live_tab(),    "Live Session")
        self._tabs.addTab(self._build_history_tab(), "History")
        outer.addWidget(self._tabs)

    def _build_live_tab(self):
        widget = QWidget()
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        content = QWidget()
        layout  = QVBoxLayout(content)
        layout.setContentsMargins(0, 16, 0, 16); layout.setSpacing(14)

        self._live_no_session = QLabel("No active session.\nStart a session to see live analytics.")
        self._live_no_session.setStyleSheet(f"color:{T['text3']}; font-size:13px;")
        self._live_no_session.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._live_no_session)

        live_card_row = QHBoxLayout(); live_card_row.setSpacing(10)
        self._live_duration_card   = StatCard("Session Duration",   "--",  "",     T['text'])
        self._live_strain_card     = StatCard("Current Strain",     "--",  "",     T['accent'])
        self._live_blink_card      = StatCard("Blink Rate",         "--",  "/min", T['green'])
        self._live_rewards_card    = StatCard("Points This Session","0",   "pts",  T['yellow'])
        self._live_recoveries_card = StatCard("Recoveries",         "0",   "",     T['orange'])
        for c in [self._live_duration_card, self._live_strain_card,
                  self._live_blink_card, self._live_rewards_card,
                  self._live_recoveries_card]:
            c.hide(); live_card_row.addWidget(c)
        layout.addLayout(live_card_row)

        self._live_chart_card = self._make_card(); self._live_chart_card.hide()
        lc = QVBoxLayout(self._live_chart_card); lc.setContentsMargins(16, 14, 16, 14)
        ch = QHBoxLayout()
        ct = QLabel("VFQ — Current Session")
        ct.setStyleSheet(f"color:{T['text']}; font-size:13px; font-weight:600;")
        self._live_dot = QLabel("LIVE")
        self._live_dot.setStyleSheet(f"color:{T['red']}; font-size:11px;")
        ch.addWidget(ct); ch.addStretch(); ch.addWidget(self._live_dot)
        lc.addLayout(ch)
        self._live_vfq_chart = MiniChart(max_points=180)
        self._live_vfq_chart.setMinimumHeight(130)
        lc.addWidget(self._live_vfq_chart)
        layout.addWidget(self._live_chart_card)

        self._live_trend_card = self._make_card(); self._live_trend_card.hide()
        lt = QHBoxLayout(self._live_trend_card); lt.setContentsMargins(20,16,20,16); lt.setSpacing(30)
        tc = QVBoxLayout()
        tl = QLabel("Strain Trend"); tl.setStyleSheet(f"color:{T['text2']}; font-size:11px; font-weight:600;")
        self._live_trend_lbl = QLabel("→  STABLE")
        self._live_trend_lbl.setStyleSheet(f"color:{T['text2']}; font-size:16px; font-weight:700;")
        tc.addWidget(tl); tc.addWidget(self._live_trend_lbl)
        sc = QVBoxLayout()
        sl = QLabel("Strain Level"); sl.setStyleSheet(f"color:{T['text2']}; font-size:11px; font-weight:600;")
        self._live_strain_lbl = QLabel("NORMAL")
        self._live_strain_lbl.setStyleSheet(f"color:{T['green']}; font-size:16px; font-weight:700;")
        sc.addWidget(sl); sc.addWidget(self._live_strain_lbl)
        lt.addLayout(tc); lt.addLayout(sc); lt.addStretch()
        layout.addWidget(self._live_trend_card)

        layout.addStretch()
        scroll.setWidget(content)
        outer = QVBoxLayout(widget); outer.setContentsMargins(0,0,0,0); outer.addWidget(scroll)
        return widget

    def _build_history_tab(self):
        widget = QWidget()
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        content = QWidget()
        layout  = QVBoxLayout(content)
        layout.setContentsMargins(0, 16, 0, 16); layout.setSpacing(16)

        rr = QHBoxLayout()
        rb = QPushButton("Refresh"); rb.setFixedHeight(32)
        rb.setCursor(Qt.CursorShape.PointingHandCursor)
        rb.setStyleSheet(f"""
            QPushButton {{ background:{T['surface2']}; color:{T['text2']};
                border:1px solid {T['border']}; border-radius:8px; font-size:12px; padding:0 14px; }}
            QPushButton:hover {{ background:{T['accent']}; color:white; }}
        """)
        rb.clicked.connect(self.load_history)
        rr.addStretch(); rr.addWidget(rb)
        layout.addLayout(rr)

        sr = QHBoxLayout(); sr.setSpacing(10)
        self.avg_card       = StatCard("Avg VFQ",       "--", "",     T['accent'])
        self.high_card      = StatCard("High Strain",   "--", "min",  T['orange'])
        self.sessions_card  = StatCard("Sessions",      "--", "",     T['text'])
        self.blink_avg_card = StatCard("Avg Blink Rate","--", "/min", T['green'])
        for c in [self.avg_card, self.high_card, self.sessions_card, self.blink_avg_card]:
            sr.addWidget(c)
        layout.addLayout(sr)

        for attr, lbl, h in [('week_chart','VFQ — Last 7 Days',130),('blink_chart','Blink Rate — Last 7 Days',100)]:
            card = self._make_card(); cl = QVBoxLayout(card); cl.setContentsMargins(16,14,16,14)
            l = QLabel(lbl); l.setStyleSheet(f"color:{T['text']}; font-size:13px; font-weight:600;")
            cl.addWidget(l)
            chart = MiniChart(max_points=300); chart.setMinimumHeight(h)
            setattr(self, attr, chart); cl.addWidget(chart); layout.addWidget(card)

        bottom_row = QHBoxLayout(); bottom_row.setSpacing(12)
        strain_card = self._make_card(); strain_card.setMinimumWidth(260)
        sl2 = QVBoxLayout(strain_card); sl2.setContentsMargins(16,14,16,14); sl2.setSpacing(10)
        sl2.addWidget(QLabel("Strain Breakdown"))
        pie_row = QHBoxLayout()
        self.pie_chart = PieChart()
        pie_row.addWidget(self.pie_chart, alignment=Qt.AlignmentFlag.AlignVCenter)
        ll = QVBoxLayout(); ll.setSpacing(5)
        self.legend_labels = []
        for level, color in zip(STRAIN_LEVELS, STRAIN_COLORS):
            r = QHBoxLayout()
            dot = QLabel("●"); dot.setStyleSheet(f"color:{color}; font-size:12px;")
            lv  = QLabel(f"{level}  0%"); lv.setStyleSheet(f"color:{T['text2']}; font-size:11px;")
            r.addWidget(dot); r.addWidget(lv); r.addStretch()
            self.legend_labels.append(lv); ll.addLayout(r)
        pie_row.addLayout(ll); sl2.addLayout(pie_row)
        bottom_row.addWidget(strain_card)

        focus_card = self._make_card()
        fl = QVBoxLayout(focus_card); fl.setContentsMargins(16,14,16,14); fl.setSpacing(10)
        fl.addWidget(QLabel("Focus Points"))
        self.focus_layout = QVBoxLayout(); self.focus_layout.setSpacing(8)
        fl.addLayout(self.focus_layout); fl.addStretch()
        bottom_row.addWidget(focus_card)
        layout.addLayout(bottom_row)

        tc = self._make_card()
        tl2 = QVBoxLayout(tc); tl2.setContentsMargins(16,14,16,14)
        tl2.addWidget(QLabel("Session History"))
        self.table = QTableWidget(); self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Date","Duration","Avg VFQ","Max VFQ","High Strain %","Blink Rate"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(f"""
            QTableWidget {{ background:{T['surface']}; border:none; gridline-color:{T['border']}; font-size:12px; color:{T['text']}; }}
            QTableWidget::item {{ padding:8px; }}
            QHeaderView::section {{ background:{T['surface2']}; color:{T['text2']}; border:none; border-bottom:1px solid {T['border']}; padding:8px; font-size:11px; font-weight:600; }}
            QTableWidget::item:alternate {{ background:{T['surface2']}; }}
        """)
        self.table.setMinimumHeight(200); tl2.addWidget(self.table); layout.addWidget(tc)

        scroll.setWidget(content)
        outer = QVBoxLayout(widget); outer.setContentsMargins(0,0,0,0); outer.addWidget(scroll)
        return widget

    def update_live(self, data, session_active, session_seconds, reward_points, session_recoveries):
        if not session_active:
            self._live_no_session.show()
            for c in [self._live_duration_card, self._live_strain_card,
                      self._live_blink_card, self._live_rewards_card,
                      self._live_recoveries_card]:
                c.hide()
            self._live_chart_card.hide(); self._live_trend_card.hide()
            return

        self._live_no_session.hide()
        for c in [self._live_duration_card, self._live_strain_card,
                  self._live_blink_card, self._live_rewards_card,
                  self._live_recoveries_card]:
            c.show()
        self._live_chart_card.show(); self._live_trend_card.show()

        m, s = divmod(session_seconds, 60)
        self._live_duration_card.set_value(f"{m}:{s:02d}")

        vfq   = data.get('vfq_score', 0)
        label = data.get('strain_label', 'NORMAL')
        color = strain_color(vfq)
        self._live_strain_card.set_value(f"{int(vfq)}", color)
        self._live_blink_card.set_value(f"{data.get('blink_rate',0):.1f}", T['green'])
        self._live_rewards_card.set_value(str(reward_points), T['yellow'])
        self._live_recoveries_card.set_value(str(session_recoveries), T['orange'])
        self._live_vfq_chart.add_point(vfq)

        trend   = data.get('strain_trend', 'STABLE')
        arrows  = {'IMPROVING':'Improving','STABLE':'Stable','WORSENING':'Worsening'}
        tcolors = {'IMPROVING':T['green'],'STABLE':T['text2'],'WORSENING':T['red']}
        self._live_trend_lbl.setText(arrows.get(trend,'→  STABLE'))
        self._live_trend_lbl.setStyleSheet(f"color:{tcolors.get(trend,T['text2'])}; font-size:16px; font-weight:700;")
        # Show clinical label + personal context indicator
        personal_threshold = getattr(self, '_personal_threshold', None)
        if personal_threshold is not None and vfq <= personal_threshold * 0.75:
            personal_note = "Within your normal range"
            note_color    = T['green']
        elif personal_threshold is not None and vfq <= personal_threshold:
            personal_note = "Approaching your threshold"
            note_color    = T['yellow']
        else:
            personal_note = ""
            note_color    = color

        self._live_strain_lbl.setText(label)
        self._live_strain_lbl.setStyleSheet(
            f"color:{color}; font-size:16px; font-weight:700;")
        if hasattr(self, '_live_personal_note'):
            if personal_note:
                self._live_personal_note.setText(personal_note)
                self._live_personal_note.setStyleSheet(
                    f"color:{note_color}; font-size:10px;")
                self._live_personal_note.show()
            else:
                self._live_personal_note.hide()

    def clear_live_session(self):
        self._live_vfq_chart.clear()
        self._session_recoveries = 0

    def _make_card(self):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{ background:{T['surface']}; border:1px solid {T['border']}; border-radius:16px; }}
        """)
        return card

    def _add_focus_point(self, icon, text, color):
        r = QHBoxLayout()
        il = QLabel(icon); il.setStyleSheet(f"color:{T['text3']};font-size:10px;"); il.setFixedWidth(16)
        tl = QLabel(text); tl.setStyleSheet(f"color:{color}; font-size:12px; font-weight:500;"); tl.setWordWrap(True)
        r.addWidget(il); r.addWidget(tl); r.addStretch()
        w = QWidget(); w.setLayout(r); self.focus_layout.addWidget(w)

    def _clear_focus_points(self):
        for i in reversed(range(self.focus_layout.count())):
            item = self.focus_layout.itemAt(i)
            if item and item.widget(): item.widget().deleteLater()

    def load_history(self):
        import glob as g, pandas as pd
        # Prefer user-scoped sessions dir; fall back to data root for legacy
        _sess = DATA_DIR / 'users' / getattr(self, '_user_id', 'user_001') / 'sessions'
        if _sess.exists():
            _pattern = str(_sess / f"{getattr(self,'_user_id','user_001')}_session_*.csv")
        else:
            _pattern = str(DATA_DIR / 'user_001_session_*.csv')
        files = sorted(g.glob(_pattern))
        if not files:
            self._add_focus_point("—","No session files found.",T['text3']); return
        all_vfq=[]; all_blink=[]; all_high_secs=0; n_sessions=0
        strain_counts={lv:0 for lv in STRAIN_LEVELS}; session_rows=[]
        for f in files:
            try:
                df = pd.read_csv(f)
                if df is None or len(df)==0: continue
                n_sessions += 1
                if 'vfq_score' in df.columns:
                    vfqs = pd.to_numeric(df['vfq_score'],errors='coerce').dropna().tolist()
                    all_vfq.extend(vfqs); all_high_secs+=sum(1 for v in vfqs if v>=60)
                    avg_vfq=round(sum(vfqs)/len(vfqs),1) if vfqs else 0
                    max_vfq=round(max(vfqs),1) if vfqs else 0
                    high_pct=round(sum(1 for v in vfqs if v>=60)/len(vfqs)*100,1) if vfqs else 0
                else: avg_vfq=max_vfq=high_pct=0
                if 'blink_rate' in df.columns:
                    blinks=pd.to_numeric(df['blink_rate'],errors='coerce').dropna().tolist()
                    all_blink.extend(blinks); avg_blink=round(sum(blinks)/len(blinks),1) if blinks else 0
                else: avg_blink=0
                if 'strain_label' in df.columns:
                    for lv in STRAIN_LEVELS: strain_counts[lv]+=int((df['strain_label']==lv).sum())
                try: date_str=str(df['timestamp'].iloc[0])[:16]
                except Exception: date_str=os.path.basename(f)[-19:-4]
                session_rows.append({'date':date_str,'duration':f"{len(df)//60}m {len(df)%60}s",
                    'avg_vfq':avg_vfq,'max_vfq':max_vfq,'high_pct':f"{high_pct}%",'blink':avg_blink})
            except Exception as e: print(f"  [Analytics] Skipped {f}: {e}"); continue

        if all_vfq:
            self.avg_card.set_value(f"{sum(all_vfq)/len(all_vfq):.1f}",T['accent'])
            self.high_card.set_value(f"{all_high_secs//60}",T['orange'])
        self.sessions_card.set_value(str(n_sessions))
        if all_blink: self.blink_avg_card.set_value(f"{sum(all_blink)/len(all_blink):.1f}",T['green'])

        self.week_chart.clear()
        for v in all_vfq[-300:]: self.week_chart.add_point(v)
        self.blink_chart.clear()
        for v in all_blink[-300:]: self.blink_chart.add_point(min(100,(v/20)*100))

        total_labels=sum(strain_counts.values()) or 1
        self.pie_chart.set_data([strain_counts[lv] for lv in STRAIN_LEVELS],STRAIN_COLORS)
        for lv,lbl_w in zip(STRAIN_LEVELS,self.legend_labels):
            lbl_w.setText(f"{lv}  {round(strain_counts[lv]/total_labels*100,1)}%")

        self._clear_focus_points()
        if not all_vfq: self._add_focus_point("—","No VFQ data found.",T['text3'])
        else:
            avg=sum(all_vfq)/len(all_vfq); b_avg=sum(all_blink)/len(all_blink) if all_blink else 0
            hi_pct=(strain_counts['HIGH']+strain_counts['SEVERE'])/total_labels*100
            if avg>=50: self._add_focus_point("High",f"Avg VFQ {avg:.1f}",T['red'])
            elif avg>=30: self._add_focus_point("Moderate",f"Avg VFQ {avg:.1f}",T['yellow'])
            else: self._add_focus_point("Good",f"Avg VFQ {avg:.1f}",T['green'])
            if b_avg<5: self._add_focus_point("Low",f"Blink rate {b_avg:.1f}/min — below clinical minimum",T['red'])
            elif b_avg<8: self._add_focus_point("Low",f"Blink rate {b_avg:.1f}/min",T['yellow'])
            else: self._add_focus_point("Good",f"Blink rate {b_avg:.1f}/min",T['green'])
            if hi_pct>15: self._add_focus_point("Alert",f"{hi_pct:.1f}% of time at HIGH/SEVERE strain",T['red'])
            if n_sessions>=3: self._add_focus_point("Info",f"{n_sessions} sessions logged",T['text2'])

        self.table.setRowCount(len(session_rows))
        for ri,row in enumerate(reversed(session_rows)):
            vals=[row['date'],row['duration'],str(row['avg_vfq']),str(row['max_vfq']),row['high_pct'],str(row['blink'])]
            for ci,val in enumerate(vals):
                item=QTableWidgetItem(val); item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if ci==2:
                    try: item.setForeground(QColor(strain_color(float(val))))
                    except Exception: pass
                self.table.setItem(ri,ci,item)


# ── REPORTS SCREEN ────────────────────────────────────────────────────────────

class ReportsScreen(QWidget):
    """
    Reports page — shows full report preview before download.
    Two dropdowns at bottom-left: scope and format.
    Charts: VFQ trend line, blink rate bar, strain distribution pie (drawn with QPainter).
    AI report with diet/suggestions section.
    """
    def __init__(self, user_id='user_001', parent=None):
        super().__init__(parent)
        self._user_id           = user_id
        self._report_text_cache = ""
        self._report_mode_cache = 'session'
        self._df_cache          = None
        self._build_ui()

    def set_user(self, user_id: str):
        self._user_id = user_id
        self._df_cache = None

    def _user_dir(self):
        return DATA_DIR / 'users' / self._user_id

    def _sessions_dir(self):
        return self._user_dir() / 'sessions'

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Scrollable main area ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        content = QWidget()
        layout  = QVBoxLayout(content)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(16)

        title = QLabel("Reports")
        title.setStyleSheet(
            f"color:{T['text']}; font-size:20px; font-weight:700;")
        layout.addWidget(title)

        # ── Charts row ──────────────────────────────────────────────────────
        charts_row = QHBoxLayout(); charts_row.setSpacing(12)

        self._vfq_chart_card  = self._chart_card("VFQ Over Time")
        self._blink_chart_card = self._chart_card("Blink Rate")
        self._pie_card        = self._chart_card("Strain Distribution")
        for c in [self._vfq_chart_card, self._blink_chart_card, self._pie_card]:
            charts_row.addWidget(c)
        layout.addLayout(charts_row)

        # ── Report preview ───────────────────────────────────────────────────
        preview_card = QFrame()
        preview_card.setStyleSheet(
            f"QFrame{{background:{T['surface']};border:1px solid {T['border']};"
            f"border-radius:14px;}}")
        pl = QVBoxLayout(preview_card)
        pl.setContentsMargins(24, 20, 24, 20)
        pl.setSpacing(12)

        ph = QHBoxLayout()
        preview_lbl = QLabel("Report Preview")
        preview_lbl.setStyleSheet(
            f"color:{T['text']}; font-size:14px; font-weight:700;")
        ph.addWidget(preview_lbl); ph.addStretch()

        self._generate_btn = QPushButton("Generate Report")
        self._generate_btn.setFixedHeight(32)
        self._generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._generate_btn.setStyleSheet(
            f"QPushButton{{background:{T['accent']};color:white;border:none;"
            f"border-radius:8px;font-size:12px;font-weight:600;padding:0 14px;}}"
            f"QPushButton:hover{{background:#1D4ED8;}}")
        self._generate_btn.clicked.connect(self._on_generate)
        ph.addWidget(self._generate_btn)
        pl.addLayout(ph)

        self._ai_status_lbl = QLabel("Select a scope and click Generate Report.")
        self._ai_status_lbl.setStyleSheet(
            f"color:{T['text3']}; font-size:12px;")
        pl.addWidget(self._ai_status_lbl)

        self._preview_area = QScrollArea()
        self._preview_area.setWidgetResizable(True)
        self._preview_area.setFixedHeight(380)
        self._preview_area.setFrameShape(QFrame.Shape.NoFrame)
        self._preview_area.setStyleSheet(
            f"QScrollArea{{background:{T['surface2']};border-radius:10px;border:none;}}")

        self._preview_text = QLabel("")
        self._preview_text.setWordWrap(True)
        self._preview_text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._preview_text.setStyleSheet(
            f"color:{T['text']}; font-size:12px; padding:16px; "
            f"background:{T['surface2']}; border-radius:10px; line-height:1.6;")
        self._preview_text.setTextFormat(Qt.TextFormat.PlainText)
        self._preview_area.setWidget(self._preview_text)
        pl.addWidget(self._preview_area)

        layout.addWidget(preview_card)
        layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

        # ── Bottom bar: scope + format dropdowns + download ──────────────────
        bottom_bar = QWidget()
        bottom_bar.setFixedHeight(60)
        bottom_bar.setStyleSheet(
            f"background:{T['surface']}; border-top:1px solid {T['border']};")
        bl = QHBoxLayout(bottom_bar)
        bl.setContentsMargins(24, 0, 24, 0)
        bl.setSpacing(12)

        scope_lbl = QLabel("Scope:")
        scope_lbl.setStyleSheet(f"color:{T['text2']}; font-size:12px;")
        self._scope_cb = QComboBox()
        self._scope_cb.addItems([
            "Last Session", "Last 7 Days", "Last Month", "All Sessions"])
        self._scope_cb.setFixedHeight(34)
        self._scope_cb.setFixedWidth(140)
        self._scope_cb.setStyleSheet(self._cb_style())

        fmt_lbl = QLabel("Format:")
        fmt_lbl.setStyleSheet(f"color:{T['text2']}; font-size:12px;")
        self._fmt_cb = QComboBox()
        self._fmt_cb.addItems(["PDF", "CSV"])
        self._fmt_cb.setFixedHeight(34)
        self._fmt_cb.setFixedWidth(90)
        self._fmt_cb.setStyleSheet(self._cb_style())

        self._download_btn = QPushButton("Download")
        self._download_btn.setFixedHeight(34)
        self._download_btn.setFixedWidth(100)
        self._download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._download_btn.setStyleSheet(
            f"QPushButton{{background:{T['accent']};color:white;border:none;"
            f"border-radius:8px;font-size:12px;font-weight:600;}}"
            f"QPushButton:hover{{background:#1D4ED8;}}")
        self._download_btn.clicked.connect(self._on_download)

        bl.addWidget(scope_lbl)
        bl.addWidget(self._scope_cb)
        bl.addWidget(fmt_lbl)
        bl.addWidget(self._fmt_cb)
        bl.addStretch()
        bl.addWidget(self._download_btn)
        root.addWidget(bottom_bar)

    def _cb_style(self):
        return (f"QComboBox{{background:{T['surface2']};color:{T['text']};"
                f"border:1px solid {T['border']};border-radius:8px;"
                f"padding:0 10px;font-size:12px;}}"
                f"QComboBox::drop-down{{border:none;width:18px;}}"
                f"QComboBox QAbstractItemView{{background:{T['surface2']};"
                f"color:{T['text']};border:1px solid {T['border']};"
                f"selection-background-color:{T['accent']};}}")

    def _chart_card(self, title):
        f = QFrame()
        f.setStyleSheet(
            f"QFrame{{background:{T['surface']};border:1px solid {T['border']};"
            f"border-radius:14px;}}")
        l = QVBoxLayout(f); l.setContentsMargins(16, 12, 16, 12); l.setSpacing(8)
        t = QLabel(title)
        t.setStyleSheet(f"color:{T['text2']}; font-size:11px; font-weight:600;")
        ph = QLabel("")
        ph.setFixedHeight(100)
        ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph.setStyleSheet(f"color:{T['text3']}; font-size:11px;")
        ph.setText("No data")
        l.addWidget(t); l.addWidget(ph)
        f._placeholder = ph
        return f

    # ── Data loading ──────────────────────────────────────────────────────────
    def _scope_to_mode(self):
        txt = self._scope_cb.currentText()
        return {
            "Last Session":  "session",
            "Last 7 Days":   "7days",
            "Last Month":    "month",
            "All Sessions":  "all",
        }.get(txt, "session")

    def _load_data(self, mode):
        import glob as g, pandas as pd
        from datetime import timedelta
        pattern = str(self._sessions_dir() /
                      f'{self._user_id}_session_*.csv')
        files = sorted(g.glob(pattern))
        if not files:
            return None, "No session data found.", ""

        if mode == "session":
            files = [files[-1]]
            label = "Last Session"
        elif mode == "7days":
            cutoff = datetime.now() - timedelta(days=7)
            sel = []
            for f in files:
                try:
                    row = pd.read_csv(f, nrows=1)
                    if 'timestamp' in row.columns:
                        ts = pd.to_datetime(row['timestamp'].iloc[0], errors='coerce')
                        if ts is not pd.NaT and ts >= cutoff:
                            sel.append(f)
                except Exception:
                    pass
            files = sel or files[-7:]
            label = "Last 7 Days"
        elif mode == "month":
            cutoff = datetime.now() - timedelta(days=30)
            sel = []
            for f in files:
                try:
                    row = pd.read_csv(f, nrows=1)
                    if 'timestamp' in row.columns:
                        ts = pd.to_datetime(row['timestamp'].iloc[0], errors='coerce')
                        if ts is not pd.NaT and ts >= cutoff:
                            sel.append(f)
                except Exception:
                    pass
            files = sel or files[-30:]
            label = "Last Month"
        else:
            label = "All Sessions"

        dfs = []
        for f in files:
            try: dfs.append(pd.read_csv(f))
            except Exception: pass
        if not dfs:
            return None, "Could not load data.", ""

        df = pd.concat(dfs, ignore_index=True)
        date_range = (f"{files[0].split('_')[-2]} to "
                      f"{files[-1].split('_')[-2]}" if len(files) > 1
                      else files[0].split('_')[-2])
        return df, label, date_range

    # ── Chart drawing ─────────────────────────────────────────────────────────
    def _draw_charts(self, df):
        import pandas as pd
        try:
            vfq = pd.to_numeric(df['vfq_score'], errors='coerce').dropna()
            self._draw_line(self._vfq_chart_card, vfq.tolist(), "#3B82F6", "VFQ")
        except Exception:
            self._vfq_chart_card._placeholder.setText("No VFQ data")

        try:
            blink = pd.to_numeric(df['blink_rate'], errors='coerce').dropna()
            blink = blink[blink > 0]
            # Bar chart — show per-decile averages
            self._draw_bars(self._blink_chart_card, blink.tolist(), "#10B981")
        except Exception:
            self._blink_chart_card._placeholder.setText("No blink data")

        try:
            vfq = pd.to_numeric(df['vfq_score'], errors='coerce').dropna()
            normal   = int((vfq < 20).sum())
            low      = int(((vfq >= 20) & (vfq < 40)).sum())
            moderate = int(((vfq >= 40) & (vfq < 60)).sum())
            high     = int(((vfq >= 60) & (vfq < 80)).sum())
            severe   = int((vfq >= 80).sum())
            self._draw_pie(self._pie_card,
                [normal, low, moderate, high, severe],
                ["Normal", "Low", "Moderate", "High", "Severe"],
                ["#10B981", "#84CC16", "#F59E0B", "#F97316", "#EF4444"])
        except Exception:
            self._pie_card._placeholder.setText("No strain data")

    def _draw_line(self, card, values, color, label):
        if not values: return
        import math
        ph = card._placeholder
        ph.setText("")

        class LineChart(QWidget):
            def __init__(self, vals, col):
                super().__init__()
                self.vals = vals
                self.col  = col
                self.setFixedHeight(100)

            def paintEvent(self, e):
                if not self.vals: return
                p = QPainter(self)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                w, h  = self.width(), self.height()
                pad   = 8
                mn    = min(self.vals); mx = max(self.vals)
                rng   = mx - mn or 1
                pts   = []
                for i, v in enumerate(self.vals):
                    x = pad + (w - 2*pad) * i / max(len(self.vals)-1, 1)
                    y = h - pad - (h - 2*pad) * (v - mn) / rng
                    pts.append((x, y))
                pen = QPen(QColor(self.col)); pen.setWidth(2)
                p.setPen(pen)
                for i in range(1, len(pts)):
                    p.drawLine(int(pts[i-1][0]), int(pts[i-1][1]),
                               int(pts[i][0]),   int(pts[i][1]))
                # Axis labels
                p.setPen(QColor("#666666"))
                p.setFont(QFont("Arial", 8))
                p.drawText(0, h-2, f"{mn:.0f}")
                p.drawText(0, 12, f"{mx:.0f}")

        # Remove old chart widget if any
        lo = card.layout()
        for i in reversed(range(lo.count())):
            w = lo.itemAt(i).widget()
            if isinstance(w, QWidget) and not isinstance(w, QLabel):
                lo.removeWidget(w); w.deleteLater()

        # Downsample if needed
        vals = values
        if len(vals) > 200:
            step = len(vals) // 200
            vals = vals[::step]

        chart = LineChart(vals, color)
        lo.addWidget(chart)

    def _draw_bars(self, card, values, color):
        if not values: return
        ph = card._placeholder; ph.setText("")

        class BarChart(QWidget):
            def __init__(self, vals, col):
                super().__init__()
                self.vals = vals
                self.col  = col
                self.setFixedHeight(100)

            def paintEvent(self, e):
                if not self.vals: return
                p = QPainter(self)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                w, h  = self.width(), self.height()
                pad   = 8
                n     = min(20, len(self.vals))
                step  = max(1, len(self.vals) // n)
                bars  = [sum(self.vals[i:i+step])/len(self.vals[i:i+step])
                         for i in range(0, len(self.vals), step)][:n]
                mx    = max(bars) or 1
                bw    = (w - 2*pad) / len(bars)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(self.col))
                for i, v in enumerate(bars):
                    bh = (h - 2*pad) * v / mx
                    p.drawRoundedRect(
                        int(pad + i*bw + 1), int(h - pad - bh),
                        int(bw - 2), int(bh), 3, 3)

        lo = card.layout()
        for i in reversed(range(lo.count())):
            wi = lo.itemAt(i).widget()
            if isinstance(wi, QWidget) and not isinstance(wi, QLabel):
                lo.removeWidget(wi); wi.deleteLater()
        lo.addWidget(BarChart(values, color))

    def _draw_pie(self, card, values, labels, colors):
        total = sum(values) or 1
        ph = card._placeholder; ph.setText("")

        class PieChart(QWidget):
            def __init__(self, vals, lbls, cols):
                super().__init__()
                self.vals = vals; self.lbls = lbls; self.cols = cols
                self.setFixedHeight(100)

            def paintEvent(self, e):
                p = QPainter(self)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                w, h = self.width(), self.height()
                r    = min(w, h) // 2 - 8
                cx, cy = w // 4, h // 2
                total = sum(self.vals) or 1
                angle = 0
                for v, col in zip(self.vals, self.cols):
                    span = int(360 * 16 * v / total)
                    p.setBrush(QColor(col)); p.setPen(Qt.PenStyle.NoPen)
                    p.drawPie(cx-r, cy-r, r*2, r*2, angle, span)
                    angle += span
                # Legend
                p.setFont(QFont("Arial", 8))
                ly = 12
                for lbl, col, val in zip(self.lbls, self.cols, self.vals):
                    if val == 0: continue
                    p.setBrush(QColor(col)); p.setPen(Qt.PenStyle.NoPen)
                    p.drawRect(cx*2+4, ly-8, 8, 8)
                    p.setPen(QColor("#888888"))
                    pct = val/total*100
                    p.drawText(cx*2+16, ly, f"{lbl} {pct:.0f}%")
                    ly += 14

        lo = card.layout()
        for i in reversed(range(lo.count())):
            wi = lo.itemAt(i).widget()
            if isinstance(wi, QWidget) and not isinstance(wi, QLabel):
                lo.removeWidget(wi); wi.deleteLater()
        lo.addWidget(PieChart(values, labels, colors))

    # ── Report generation ─────────────────────────────────────────────────────
    def _on_generate(self):
        mode = self._scope_to_mode()
        self._ai_status_lbl.setText("Loading data...")
        self._generate_btn.setEnabled(False)
        QApplication.processEvents()

        df, label, date_range = self._load_data(mode)
        if df is None:
            self._ai_status_lbl.setText(label)
            self._generate_btn.setEnabled(True)
            return

        self._df_cache = df
        self._draw_charts(df)

        # Generate stats-based report + AI enhancement
        stats = self._compute_stats(df)
        report = self._build_report_text(stats, label, date_range)
        self._report_text_cache = report
        self._preview_text.setText(report)
        self._ai_status_lbl.setText(f"Report ready — {label}")
        self._generate_btn.setEnabled(True)

        # Try to enhance with AI in background
        import threading
        threading.Thread(
            target=self._ai_enhance,
            args=(stats, label, date_range),
            daemon=True).start()

    def _compute_stats(self, df):
        import pandas as pd, numpy as np
        stats = {}
        try:
            vfq = pd.to_numeric(df['vfq_score'], errors='coerce').dropna()
            stats['vfq_mean']    = round(float(vfq.mean()), 1)
            stats['vfq_max']     = round(float(vfq.max()), 1)
            stats['vfq_min']     = round(float(vfq.min()), 1)
            stats['high_pct']    = round(float((vfq >= 60).mean() * 100), 1)
            stats['moderate_pct']= round(float(((vfq >= 40) & (vfq < 60)).mean() * 100), 1)
            stats['normal_pct']  = round(float((vfq < 40).mean() * 100), 1)
        except Exception: pass
        try:
            blink = pd.to_numeric(df['blink_rate'], errors='coerce').dropna()
            blink = blink[blink > 0]
            stats['blink_mean']  = round(float(blink.mean()), 1)
            stats['blink_min']   = round(float(blink.min()),  1)
        except Exception: pass
        try:
            ear = pd.to_numeric(df['ear'], errors='coerce').dropna()
            ear = ear[ear > 0.15]
            stats['ear_mean']    = round(float(ear.mean()), 3)
        except Exception: pass
        try:
            keys = pd.to_numeric(df['keystrokes_per_min'], errors='coerce').dropna()
            keys = keys[keys > 0]
            stats['keys_mean']   = round(float(keys.mean()), 1)
        except Exception: pass
        try:
            stats['total_rows']  = len(df)
            stats['duration_min']= round(len(df) / 60, 1)
        except Exception: pass
        return stats

    def _build_report_text(self, stats, label, date_range):
        lines = []
        lines.append(f"EYE HEALTH REPORT — {label.upper()}")
        lines.append(f"Period: {date_range}")
        lines.append(f"Generated: {datetime.now().strftime('%d %B %Y, %H:%M')}")
        lines.append("=" * 60)
        lines.append("")

        lines.append("SUMMARY")
        lines.append("-" * 40)
        vfq_m = stats.get('vfq_mean', 'N/A')
        vfq_x = stats.get('vfq_max', 'N/A')
        dur   = stats.get('duration_min', 'N/A')
        lines.append(f"Average VFQ Score:    {vfq_m} / 100")
        lines.append(f"Peak VFQ Score:       {vfq_x} / 100")
        lines.append(f"Session Duration:     {dur} minutes")
        lines.append(f"Time at Normal VFQ:   {stats.get('normal_pct','N/A')}%")
        lines.append(f"Time at Moderate VFQ: {stats.get('moderate_pct','N/A')}%")
        lines.append(f"Time at High VFQ:     {stats.get('high_pct','N/A')}%")
        lines.append("")

        lines.append("BLINK HEALTH")
        lines.append("-" * 40)
        bm = stats.get('blink_mean', 'N/A')
        bx = stats.get('blink_min', 'N/A')
        lines.append(f"Average Blink Rate:   {bm} blinks/min")
        lines.append(f"Minimum Blink Rate:   {bx} blinks/min")
        lines.append(f"Clinical minimum:     7.0 blinks/min (Tsubota & Nakamori 1993)")
        if isinstance(bm, (int, float)) and bm < 7:
            lines.append("  Status: BELOW clinical minimum — dry eye risk elevated")
        elif isinstance(bm, (int, float)):
            lines.append("  Status: Within normal range")
        lines.append("")

        lines.append("EYE ASPECT RATIO (EAR)")
        lines.append("-" * 40)
        ear = stats.get('ear_mean', 'N/A')
        lines.append(f"Average EAR:          {ear}")
        lines.append(f"Clinical minimum:     0.200 (Soukupova & Cech 2016)")
        if isinstance(ear, (int, float)) and ear < 0.20:
            lines.append("  Status: LOW — sustained squinting or fatigue detected")
        elif isinstance(ear, (int, float)):
            lines.append("  Status: Normal")
        lines.append("")

        lines.append("RECOMMENDATIONS")
        lines.append("-" * 40)
        vfq_n = stats.get('vfq_mean', 0) if isinstance(stats.get('vfq_mean'), (int,float)) else 0
        blink_n = stats.get('blink_mean', 15) if isinstance(stats.get('blink_mean'), (int,float)) else 15

        if vfq_n >= 60:
            lines.append("- Reduce continuous screen time — take a 10-min break every hour")
            lines.append("- Use the 20-20-20 rule consistently (every 20 min, look 20 ft away for 20 sec)")
            lines.append("- Consider reducing screen brightness by 30%")
        elif vfq_n >= 40:
            lines.append("- Follow the 20-20-20 rule — your strain levels are moderate")
            lines.append("- Ensure screen is at arm's length and at or below eye level")
        else:
            lines.append("- Good eye health maintained — continue current habits")
            lines.append("- Keep using break reminders to prevent strain accumulation")

        if blink_n < 7:
            lines.append("- Use lubricating eye drops to address dry eye symptoms")
            lines.append("- Set a conscious reminder to blink fully every few minutes")
        lines.append("")

        lines.append("DIET FOR EYE HEALTH")
        lines.append("-" * 40)
        lines.append("The following nutrients support long-term eye health:")
        lines.append("- Lutein & Zeaxanthin: leafy greens (spinach, kale), eggs")
        lines.append("  Reduces risk of macular degeneration and cataracts")
        lines.append("- Omega-3 Fatty Acids: fatty fish (salmon, sardines), walnuts, flaxseed")
        lines.append("  Reduces dry eye symptoms and inflammation")
        lines.append("- Vitamin A: carrots, sweet potatoes, bell peppers")
        lines.append("  Essential for night vision and corneal health")
        lines.append("- Vitamin C: citrus fruits, berries, broccoli")
        lines.append("  Antioxidant that protects against UV damage")
        lines.append("- Vitamin E: almonds, sunflower seeds, avocado")
        lines.append("  Protects eye cells from oxidative stress")
        lines.append("- Zinc: oysters, beef, pumpkin seeds")
        lines.append("  Supports retinal health and vitamin A absorption")
        lines.append("")
        lines.append("Hydration: drink at least 2L water daily — dehydration worsens dry eye.")
        lines.append("")

        lines.append("CLINICAL REFERENCES")
        lines.append("-" * 40)
        lines.append("- Tsubota & Nakamori (1993): Blink rate 7/min clinical minimum")
        lines.append("- Soukupova & Cech (2016): EAR fatigue detection threshold 0.20")
        lines.append("- Sheppard & Wolffsohn (2018): Digital eye strain prevalence and care")
        lines.append("- American Optometric Association: CVS guidelines and 20-20-20 rule")

        return "\n".join(lines)

    def _ai_enhance(self, stats, label, date_range):
        """Try to call Claude API for enhanced recommendations. Falls back gracefully."""
        try:
            import urllib.request, json
            payload = {
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 600,
                "messages": [{
                    "role": "user",
                    "content": (
                        f"You are an eye health assistant. Given these session stats for '{label}', "
                        f"write a single paragraph (4-6 sentences) of personalised recommendations. "
                        f"Be specific, clinical, and avoid generic advice. No headers, no bullet points.\n\n"
                        f"Stats: {json.dumps(stats)}"
                    )
                }]
            }
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                ai_text = data['content'][0]['text']

            # Append AI paragraph to report
            full = (self._report_text_cache +
                    "\n\nAI PERSONALISED ANALYSIS\n" + "-"*40 + "\n" + ai_text)
            self._report_text_cache = full
            # Update UI on main thread
            QTimer.singleShot(0, lambda: self._preview_text.setText(full))
            QTimer.singleShot(0, lambda: self._ai_status_lbl.setText(
                f"Report ready with AI analysis — {label}"))
        except Exception:
            pass  # AI enhancement is optional — base report always shows

    # ── Download ───────────────────────────────────────────────────────────────
    def _on_download(self):
        fmt = self._fmt_cb.currentText()
        if fmt == "PDF":
            self._export_pdf()
        else:
            self._export_csv()

    def _export_csv(self):
        if self._df_cache is None:
            make_msgbox(self, "No Data",
                        "Generate a report first.").exec()
            return
        import os
        for folder in [os.path.expanduser("~/Desktop"),
                       os.path.expanduser("~/Downloads"),
                       os.path.expanduser("~")]:
            if os.path.exists(folder):
                default_path = os.path.join(
                    folder,
                    f"eyestrain_{self._user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
                break
        path, _ = QFileDialog.getSaveFileName(
            self, "Save CSV", default_path, "CSV Files (*.csv)")
        if not path: return
        try:
            self._df_cache.to_csv(path, index=False)
            make_msgbox(self, "Saved", f"CSV saved to:\n{path}").exec()
        except Exception as e:
            make_msgbox(self, "Error", str(e)).exec()

    def _export_pdf(self):
        if not self._report_text_cache:
            make_msgbox(self, "No Report",
                        "Generate a report first.").exec()
            return
        import os
        for folder in [os.path.expanduser("~/Desktop"),
                       os.path.expanduser("~/Downloads"),
                       os.path.expanduser("~")]:
            if os.path.exists(folder):
                default_path = os.path.join(
                    folder,
                    f"eyestrain_{self._user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
                break
        path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF", default_path, "PDF Files (*.pdf)")
        if not path: return
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.units import mm

            doc    = SimpleDocTemplate(path, pagesize=A4,
                         topMargin=20*mm, bottomMargin=20*mm,
                         leftMargin=20*mm, rightMargin=20*mm)
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle('Title2',
                parent=styles['Heading1'],
                fontSize=16, textColor=colors.HexColor('#1E3A5F'),
                spaceAfter=12)
            body_style = ParagraphStyle('Body2',
                parent=styles['Normal'],
                fontSize=9, leading=14, spaceAfter=4)
            section_style = ParagraphStyle('Section',
                parent=styles['Normal'],
                fontSize=11, fontName='Helvetica-Bold',
                textColor=colors.HexColor('#3B82F6'),
                spaceBefore=12, spaceAfter=6)

            story = []
            for line in self._report_text_cache.split('\n'):
                if not line.strip():
                    story.append(Spacer(1, 4))
                elif line.startswith('===') or line.startswith('---'):
                    continue
                elif line.isupper() and len(line) < 50:
                    story.append(Paragraph(line, section_style))
                else:
                    safe = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    story.append(Paragraph(safe, body_style))

            doc.build(story)
            make_msgbox(self, "Saved", f"PDF saved to:\n{path}").exec()
        except ImportError:
            # Fallback to plain text file
            txt_path = path.replace('.pdf', '.txt')
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(self._report_text_cache)
            make_msgbox(self, "Saved (Text)",
                f"reportlab not installed — saved as text:\n{txt_path}").exec()
        except Exception as e:
            make_msgbox(self, "Error", str(e)).exec()

    def _gather_data_for_mode(self, mode='all'):
        df, label, date_range = self._load_data(mode)
        return df, label, date_range

    def _generate_ai_report(self, mode='session'):
        self._scope_cb.setCurrentText({
            'session': 'Last Session',
            '7days':   'Last 7 Days',
            'all':     'All Sessions',
        }.get(mode, 'Last Session'))
        self._on_generate()



class SettingsScreen(QWidget):
    """Functional settings — dropdowns write directly to live system."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 24, 32, 24)
        outer.setSpacing(20)

        title = QLabel("Settings")
        title.setStyleSheet(f"color:{T['text']}; font-size:20px; font-weight:700;")
        outer.addWidget(title)

        card = QFrame()
        card.setStyleSheet(
            f"QFrame{{background:{T['surface']}; border:1px solid {T['border']}; border-radius:14px;}}")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 8, 24, 8)
        cl.setSpacing(0)

        def _div():
            d = QFrame(); d.setFrameShape(QFrame.Shape.HLine)
            d.setStyleSheet(
                f"QFrame{{background:{T['border']}; border:none; max-height:1px;}}")
            return d

        def _row(label, desc, widget):
            rw = QWidget(); rw.setStyleSheet("QWidget{background:transparent;}")
            rl = QHBoxLayout(rw); rl.setContentsMargins(0, 16, 0, 16); rl.setSpacing(16)
            tb = QVBoxLayout(); tb.setSpacing(2)
            lw = QLabel(label)
            lw.setStyleSheet(f"color:{T['text']}; font-size:13px; font-weight:600;")
            dw = QLabel(desc)
            dw.setStyleSheet(f"color:{T['text3']}; font-size:11px;")
            tb.addWidget(lw); tb.addWidget(dw)
            rl.addLayout(tb); rl.addStretch(); rl.addWidget(widget)
            return rw

        def _dd(options, default=None):
            cb = QComboBox(); cb.addItems(options)
            if default: cb.setCurrentText(default)
            cb.setFixedWidth(140); cb.setFixedHeight(36)
            cb.setStyleSheet(f"""
                QComboBox{{background:{T['surface2']};color:{T['text']};
                    border:1px solid {T['border']};border-radius:8px;
                    padding:0 10px;font-size:12px;}}
                QComboBox::drop-down{{border:none;width:20px;}}
                QComboBox QAbstractItemView{{background:{T['surface2']};color:{T['text']};
                    border:1px solid {T['border']};
                    selection-background-color:{T['accent']};}}""")
            return cb

        # DND
        self._dnd_btn = QPushButton("Enable")
        self._dnd_btn.setFixedWidth(90); self._dnd_btn.setFixedHeight(36)
        self._dnd_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dnd_btn.setStyleSheet(
            f"QPushButton{{background:{T['surface2']};color:{T['text2']};"
            f"border:1px solid {T['border']};border-radius:8px;"
            f"font-size:12px;font-weight:600;}}"
            f"QPushButton:hover{{background:{T['accent']};color:white;"
            f"border-color:{T['accent']};}}")
        self._dnd_btn.clicked.connect(self._toggle_dnd)
        cl.addWidget(_row("Do Not Disturb",
            "Suppress break reminders — monitoring continues silently",
            self._dnd_btn))
        cl.addWidget(_div())

        # Break duration
        self._dur_cb = _dd(["2 minutes", "5 minutes", "10 minutes"], "5 minutes")
        self._dur_cb.currentTextChanged.connect(self._apply_duration)
        cl.addWidget(_row("Break Trigger Duration",
            "How long VFQ must stay elevated before a reminder fires",
            self._dur_cb))
        cl.addWidget(_div())

        # Cooldown
        self._cool_cb = _dd(
            ["5 minutes", "10 minutes", "15 minutes", "30 minutes"], "10 minutes")
        self._cool_cb.currentTextChanged.connect(self._apply_cooldown)
        cl.addWidget(_row("Reminder Cooldown",
            "Minimum time between consecutive break reminders",
            self._cool_cb))
        cl.addWidget(_div())

        # Verification window
        self._ver_cb = _dd(["30 seconds", "45 seconds", "60 seconds"], "45 seconds")
        self._ver_cb.currentTextChanged.connect(self._apply_verify)
        cl.addWidget(_row("Verification Window",
            "Maximum time camera watches to confirm each recovery action",
            self._ver_cb))
        outer.addWidget(card)

        # Sign out
        logout_btn = QPushButton("Sign Out")
        logout_btn.setFixedHeight(38); logout_btn.setFixedWidth(110)
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{T['text3']};"
            f"border:1px solid {T['border']};border-radius:8px;"
            f"font-size:12px;font-weight:600;}}"
            f"QPushButton:hover{{background:{T['surface2']};color:{T['text']};}}")
        logout_btn.clicked.connect(self._do_logout)
        lo = QHBoxLayout(); lo.addStretch(); lo.addWidget(logout_btn)
        outer.addLayout(lo)
        outer.addStretch()

    def _get_sm(self):
        w = self.parent()
        while w:
            if isinstance(w, Dashboard): return w.session_manager
            w = w.parent() if hasattr(w, 'parent') else None
        return None

    def _get_dashboard(self):
        w = self.parent()
        while w:
            if isinstance(w, Dashboard): return w
            w = w.parent() if hasattr(w, 'parent') else None
        return None

    def _toggle_dnd(self):
        sm = self._get_sm()
        if sm is None: return
        if sm.break_reminder.dnd_active:
            suppressed = sm.break_reminder.disable_dnd()
            self._dnd_btn.setText("Enable")
            self._dnd_btn.setStyleSheet(
                f"QPushButton{{background:{T['surface2']};color:{T['text2']};"
                f"border:1px solid {T['border']};border-radius:8px;"
                f"font-size:12px;font-weight:600;}}"
                f"QPushButton:hover{{background:{T['accent']};color:white;}}")
            if suppressed:
                count = len(suppressed)
                peak  = max(s['vfq_avg'] for s in suppressed)
                make_msgbox(self, "Do Not Disturb",
                    f"{count} reminder(s) suppressed.\nPeak VFQ: {peak:.1f}").exec()
        else:
            sm.break_reminder.enable_dnd()
            self._dnd_btn.setText("Disable")
            self._dnd_btn.setStyleSheet(
                f"QPushButton{{background:{T['accent']};color:white;"
                f"border:none;border-radius:8px;font-size:12px;font-weight:600;}}")

    def _apply_duration(self, text):
        sm = self._get_sm()
        if sm is None: return
        v = {"2 minutes": 120, "5 minutes": 300, "10 minutes": 600}
        sm.break_reminder.config.sustained_duration_sec = float(v.get(text, 300))
        print(f"[Settings] Duration -> {v.get(text,300)}s")

    def _apply_cooldown(self, text):
        sm = self._get_sm()
        if sm is None: return
        v = {"5 minutes": 300, "10 minutes": 600,
             "15 minutes": 900, "30 minutes": 1800}
        sm.break_reminder.config.cooldown_sec = float(v.get(text, 600))
        print(f"[Settings] Cooldown -> {v.get(text,600)}s")

    def _apply_verify(self, text):
        v = {"30 seconds": 30, "45 seconds": 45, "60 seconds": 60}
        secs = v.get(text, 45)
        import reward_system as rs
        rs.VERIFY_WINDOWS['20-20-20 Rule'] = secs
        rs.VERIFY_WINDOWS['Eye Drops']     = secs + 15
        rs.VERIFY_WINDOWS['Neck Stretch']  = secs
        rs.VERIFY_WINDOWS['Stand & Walk']  = secs * 2
        print(f"[Settings] Verify window -> {secs}s")

    def _do_logout(self):
        d = self._get_dashboard()
        if d: d._on_logout()

    def sync_dnd_state(self, active: bool):
        self._dnd_btn.setText("Disable" if active else "Enable")


# ── PROFILE SCREEN ────────────────────────────────────────────────────────────
class ProfileScreen(QWidget):
    def __init__(self, user_id='user_001', parent=None):
        super().__init__(parent)
        self._user_id = user_id
        self._build_ui()

    def set_user(self, user_id: str):
        self._user_id = user_id
        self.refresh()

    def _input_style(self):
        return (f"QLineEdit{{background:{T['surface2']};color:{T['text']};"
                f"border:1px solid {T['border']};border-radius:8px;"
                f"padding:0 12px;font-size:12px;}}"
                f"QLineEdit:focus{{border-color:{T['accent']};}}")

    def _combo_style(self):
        return (f"QComboBox{{background:{T['surface2']};color:{T['text']};"
                f"border:1px solid {T['border']};border-radius:8px;"
                f"padding:0 12px;font-size:12px;}}"
                f"QComboBox::drop-down{{border:none;width:20px;}}"
                f"QComboBox QAbstractItemView{{background:{T['surface2']};"
                f"color:{T['text']};border:1px solid {T['border']};"
                f"selection-background-color:{T['accent']};}}")

    def _section(self, text):
        l = QLabel(text)
        l.setStyleSheet(
            f"color:{T['text']}; font-size:13px; font-weight:600;")
        return l

    def _scard(self, label, val):
        f = QFrame()
        f.setStyleSheet(
            f"QFrame{{background:{T['surface']};border:1px solid {T['border']};"
            f"border-radius:10px;}}")
        l = QVBoxLayout(f)
        l.setContentsMargins(16, 12, 16, 12); l.setSpacing(2)
        vl = QLabel(val)
        vl.setStyleSheet(
            f"color:{T['text']};font-size:18px;font-weight:700;")
        vl.setObjectName("sv")
        ll = QLabel(label)
        ll.setStyleSheet(f"color:{T['text3']};font-size:10px;")
        l.addWidget(vl); l.addWidget(ll)
        return f

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 24, 32, 24); outer.setSpacing(20)

        title = QLabel("Profile")
        title.setStyleSheet(
            f"color:{T['text']}; font-size:20px; font-weight:700;")
        outer.addWidget(title)

        # Avatar card
        top = QFrame()
        top.setStyleSheet(
            f"QFrame{{background:{T['surface']};border:1px solid {T['border']};"
            f"border-radius:14px;}}")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(24, 20, 24, 20); tl.setSpacing(20)
        self._avatar_lbl = QLabel(); self._avatar_lbl.setFixedSize(64, 64)
        tl.addWidget(self._avatar_lbl)
        nc = QVBoxLayout(); nc.setSpacing(4)
        self._name_lbl  = QLabel("")
        self._name_lbl.setStyleSheet(
            f"color:{T['text']};font-size:17px;font-weight:700;")
        self._uname_lbl = QLabel("")
        self._uname_lbl.setStyleSheet(
            f"color:{T['text3']};font-size:12px;")
        self._occ_lbl   = QLabel("")
        self._occ_lbl.setStyleSheet(
            f"color:{T['text2']};font-size:12px;")
        nc.addWidget(self._name_lbl)
        nc.addWidget(self._uname_lbl)
        nc.addWidget(self._occ_lbl)
        tl.addLayout(nc); tl.addStretch()
        pb = QPushButton("Change Photo")
        pb.setFixedHeight(30); pb.setCursor(Qt.CursorShape.PointingHandCursor)
        pb.setStyleSheet(
            f"QPushButton{{background:{T['surface2']};color:{T['text2']};"
            f"border:1px solid {T['border']};border-radius:8px;"
            f"font-size:11px;padding:0 12px;}}"
            f"QPushButton:hover{{color:{T['text']};}}")
        pb.clicked.connect(self._change_photo)
        tl.addWidget(pb); outer.addWidget(top)

        # Stats
        sr = QHBoxLayout(); sr.setSpacing(12)
        self._s_sessions = self._scard("Sessions", "0")
        self._s_points   = self._scard("Total Points", "0")
        self._s_email    = self._scard("Email", "—")
        for w in [self._s_sessions, self._s_points, self._s_email]:
            sr.addWidget(w)
        outer.addLayout(sr)

        # Edit details
        ec = QFrame()
        ec.setStyleSheet(
            f"QFrame{{background:{T['surface']};border:1px solid {T['border']};"
            f"border-radius:14px;}}")
        el = QVBoxLayout(ec)
        el.setContentsMargins(24, 20, 24, 20); el.setSpacing(10)
        el.addWidget(self._section("Edit Details"))
        self._edit_name = QLineEdit()
        self._edit_name.setPlaceholderText("Full name")
        self._edit_name.setFixedHeight(38)
        self._edit_name.setStyleSheet(self._input_style())
        self._edit_occ = QComboBox()
        self._edit_occ.addItems([
            "Student", "IT Professional", "Lecturer",
            "Designer", "Writer", "Other"])
        self._edit_occ.setFixedHeight(38)
        self._edit_occ.setStyleSheet(self._combo_style())
        sb2 = QPushButton("Save Changes")
        sb2.setFixedHeight(38); sb2.setCursor(Qt.CursorShape.PointingHandCursor)
        sb2.setStyleSheet(
            f"QPushButton{{background:{T['accent']};color:white;"
            f"border:none;border-radius:8px;font-size:12px;font-weight:600;}}"
            f"QPushButton:hover{{background:#1D4ED8;}}")
        sb2.clicked.connect(self._save_details)
        for w in [self._edit_name, self._edit_occ, sb2]:
            el.addWidget(w)
        outer.addWidget(ec)

        # Change password
        pc = QFrame()
        pc.setStyleSheet(
            f"QFrame{{background:{T['surface']};border:1px solid {T['border']};"
            f"border-radius:14px;}}")
        pl = QVBoxLayout(pc)
        pl.setContentsMargins(24, 20, 24, 20); pl.setSpacing(10)
        pl.addWidget(self._section("Change Password"))
        self._pw_old = QLineEdit()
        self._pw_old.setPlaceholderText("Current password")
        self._pw_old.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_old.setFixedHeight(38)
        self._pw_old.setStyleSheet(self._input_style())
        self._pw_new = QLineEdit()
        self._pw_new.setPlaceholderText("New password")
        self._pw_new.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_new.setFixedHeight(38)
        self._pw_new.setStyleSheet(self._input_style())
        self._pw_cfm = QLineEdit()
        self._pw_cfm.setPlaceholderText("Confirm new password")
        self._pw_cfm.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_cfm.setFixedHeight(38)
        self._pw_cfm.setStyleSheet(self._input_style())
        self._pw_err = QLabel("")
        self._pw_err.setStyleSheet(f"color:{T['red']};font-size:11px;")
        self._pw_err.hide()
        pb2 = QPushButton("Update Password")
        pb2.setFixedHeight(38); pb2.setCursor(Qt.CursorShape.PointingHandCursor)
        pb2.setStyleSheet(
            f"QPushButton{{background:{T['surface2']};color:{T['text']};"
            f"border:1px solid {T['border']};border-radius:8px;"
            f"font-size:12px;font-weight:600;}}"
            f"QPushButton:hover{{background:{T['accent']};color:white;border:none;}}")
        pb2.clicked.connect(self._change_password)
        for w in [self._pw_old, self._pw_new, self._pw_cfm, self._pw_err, pb2]:
            pl.addWidget(w)
        outer.addWidget(pc)
        outer.addStretch()

    def refresh(self):
        try:
            import json, sys
            sys.path.insert(0, str(Path(__file__).parent))
            from login import load_users
            users = load_users()
            user  = users.get(self._user_id, {})
            _base = Path(__file__).parent.parent
            pp    = _base / 'data' / 'users' / self._user_id / 'profile.json'
            prof  = json.loads(pp.read_text()) if pp.exists() else {}
            rp    = _base / 'data' / 'users' / self._user_id / 'rewards.json'
            pts   = (json.loads(rp.read_text()).get('total_points', 0)
                     if rp.exists() else 0)
        except Exception as e:
            print(f"[Profile] {e}"); return

        full  = user.get('full_name', self._user_id)
        occ   = user.get('occupation', '')
        email = user.get('email', '—')
        sess  = prof.get('total_sessions', 0)

        # Avatar
        ap = user.get('avatar_path', '')
        if ap and os.path.exists(ap):
            px  = QPixmap(ap).scaled(
                64, 64,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            out = QPixmap(64, 64)
            out.fill(Qt.GlobalColor.transparent)
            p   = QPainter(out)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            from PyQt6.QtGui import QPainterPath
            path = QPainterPath()
            path.addEllipse(0, 0, 64, 64)
            p.setClipPath(path)
            p.drawPixmap(0, 0, px); p.end()
            self._avatar_lbl.setPixmap(out)
        else:
            colors = ['#3B82F6','#10B981','#F59E0B',
                      '#EF4444','#8B5CF6','#EC4899']
            color  = colors[sum(ord(c) for c in self._user_id) % len(colors)]
            px = QPixmap(64, 64); px.fill(Qt.GlobalColor.transparent)
            p  = QPainter(px)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            from PyQt6.QtGui import QPainterPath, QFont
            path2 = QPainterPath()
            path2.addEllipse(0, 0, 64, 64); p.setClipPath(path2)
            p.fillRect(0, 0, 64, 64, QColor(color))
            p.setPen(QColor('white'))
            p.setFont(QFont('Arial', 22, QFont.Weight.Bold))
            p.drawText(0, 0, 64, 64, Qt.AlignmentFlag.AlignCenter,
                       full[:2].upper()); p.end()
            self._avatar_lbl.setPixmap(px)

        self._name_lbl.setText(full)
        self._uname_lbl.setText(f"@{self._user_id}")
        self._occ_lbl.setText(occ)
        self._edit_name.setText(full)
        if occ in [self._edit_occ.itemText(i)
                   for i in range(self._edit_occ.count())]:
            self._edit_occ.setCurrentText(occ)
        for w in self._s_sessions.findChildren(QLabel):
            if w.objectName() == "sv": w.setText(str(sess))
        for w in self._s_points.findChildren(QLabel):
            if w.objectName() == "sv": w.setText(str(pts))
        for w in self._s_email.findChildren(QLabel):
            if w.objectName() == "sv":
                w.setText(email[:18] + ("..." if len(email) > 18 else ""))

    def _change_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Photo", "",
            "Images (*.png *.jpg *.jpeg *.webp)")
        if not path: return
        try:
            import shutil, pathlib, sys
            sys.path.insert(0, str(Path(__file__).parent))
            from login import load_users, save_users
            users = load_users(); user = users.get(self._user_id, {})
            _base = Path(__file__).parent.parent
            udir  = _base / 'data' / 'users' / self._user_id
            udir.mkdir(parents=True, exist_ok=True)
            ext  = pathlib.Path(path).suffix
            dest = str(udir / f'avatar{ext}')
            shutil.copy2(path, dest)
            user['avatar_path']  = dest
            users[self._user_id] = user
            save_users(users); self.refresh()
        except Exception as e:
            make_msgbox(self, "Error", str(e)).exec()

    def _save_details(self):
        name = self._edit_name.text().strip()
        occ  = self._edit_occ.currentText()
        if not name: return
        try:
            import sys; sys.path.insert(0, str(Path(__file__).parent))
            from login import load_users, save_users
            users = load_users(); user = users.get(self._user_id, {})
            user['full_name'] = name; user['occupation'] = occ
            users[self._user_id] = user; save_users(users)
            self._name_lbl.setText(name); self._occ_lbl.setText(occ)
            make_msgbox(self, "Saved", "Profile updated.").exec()
        except Exception as e:
            make_msgbox(self, "Error", str(e)).exec()

    def _change_password(self):
        import hashlib
        cur = self._pw_old.text()
        new = self._pw_new.text()
        cfm = self._pw_cfm.text()
        if not all([cur, new, cfm]):
            self._pw_err.setText("All fields required.")
            self._pw_err.show(); return
        if len(new) < 6:
            self._pw_err.setText("Minimum 6 characters.")
            self._pw_err.show(); return
        if new != cfm:
            self._pw_err.setText("Passwords do not match.")
            self._pw_err.show(); return
        try:
            import sys; sys.path.insert(0, str(Path(__file__).parent))
            from login import load_users, save_users
            users = load_users(); user = users.get(self._user_id, {})
            if (hashlib.sha256(cur.encode()).hexdigest()
                    != user.get('password_hash', '')):
                self._pw_err.setText("Current password incorrect.")
                self._pw_err.show(); return
            user['password_hash']  = hashlib.sha256(new.encode()).hexdigest()
            users[self._user_id]   = user
            save_users(users)
            self._pw_old.clear(); self._pw_new.clear(); self._pw_cfm.clear()
            self._pw_err.hide()
            make_msgbox(self, "Password Changed", "Password updated.").exec()
        except Exception as e:
            self._pw_err.setText(str(e)); self._pw_err.show()


# ── TEST MODE SCREEN ──────────────────────────────────────────────────────────
class TestModeScreen(QWidget):
    """Demo/reviewer mode — fires interventions rapidly for demonstration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._test_active = False
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 24, 32, 24); outer.setSpacing(20)

        title = QLabel("Test Mode")
        title.setStyleSheet(
            f"color:{T['text']}; font-size:20px; font-weight:700;")
        outer.addWidget(title)

        warn = QFrame()
        warn.setStyleSheet(
            "QFrame{background:#1C1209;border:1px solid #92400E;border-radius:12px;}")
        wl = QVBoxLayout(warn)
        wl.setContentsMargins(20, 16, 20, 16); wl.setSpacing(6)
        w1 = QLabel("For Reviewers and Demo Purposes Only")
        w1.setStyleSheet("color:#F59E0B;font-size:13px;font-weight:700;")
        w2 = QLabel(
            "Uses VFQ threshold 20, duration 5s, cooldown 5s. "
            "Interventions fire rapidly to demonstrate the system. "
            "All values revert to personal baseline when disabled.")
        w2.setStyleSheet("color:#D97706;font-size:11px;")
        w2.setWordWrap(True)
        wl.addWidget(w1); wl.addWidget(w2); outer.addWidget(warn)

        info_card = QFrame()
        info_card.setStyleSheet(
            f"QFrame{{background:{T['surface']};border:1px solid {T['border']};"
            f"border-radius:14px;}}")
        il = QVBoxLayout(info_card)
        il.setContentsMargins(24, 20, 24, 20); il.setSpacing(8)
        for label, val in [
            ("VFQ Threshold", "20"),
            ("Trigger Duration", "5 seconds"),
            ("Cooldown", "5 seconds"),
            ("Predictor Warmup", "20 seconds"),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{T['text2']};font-size:12px;")
            vlbl = QLabel(val)
            vlbl.setStyleSheet(
                f"color:{T['text']};font-size:12px;font-weight:600;")
            row.addWidget(lbl); row.addStretch(); row.addWidget(vlbl)
            il.addLayout(row)
        outer.addWidget(info_card)

        self._test_btn = QPushButton("Enable Test Mode")
        self._test_btn.setFixedHeight(44)
        self._test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._test_btn.setStyleSheet(
            f"QPushButton{{background:{T['surface2']};color:{T['text']};"
            f"border:1px solid {T['border']};border-radius:10px;"
            f"font-size:13px;font-weight:600;}}"
            f"QPushButton:hover{{background:{T['accent']};color:white;border:none;}}")
        self._test_btn.clicked.connect(self._toggle)
        outer.addWidget(self._test_btn)
        outer.addStretch()

    def _get_sm(self):
        w = self.parent()
        while w:
            if isinstance(w, Dashboard): return w.session_manager
            w = w.parent() if hasattr(w, 'parent') else None
        return None

    def _toggle(self):
        sm = self._get_sm()
        if sm is None:
            make_msgbox(self, "No Session",
                        "Start a session first.").exec()
            return
        if not self._test_active:
            self._test_active = True
            sm.break_reminder.config.vfq_threshold          = 20.0
            sm.break_reminder.config.sustained_duration_sec = 5.0
            sm.break_reminder.config.cooldown_sec            = 5.0
            try: sm.strain_predictor.MIN_DATA_SECONDS = 20
            except Exception: pass
            self._test_btn.setText("Disable Test Mode")
            self._test_btn.setStyleSheet(
                f"QPushButton{{background:{T['red']};color:white;"
                f"border:none;border-radius:10px;"
                f"font-size:13px;font-weight:600;}}"
                f"QPushButton:hover{{background:#B91C1C;}}")
            print("[TestMode] ENABLED — VFQ=20, 5s/5s")
        else:
            self._test_active = False
            try:
                sm._apply_personal_threshold()
            except Exception:
                sm.break_reminder.config.vfq_threshold          = 40.0
                sm.break_reminder.config.sustained_duration_sec = 300.0
                sm.break_reminder.config.cooldown_sec            = 600.0
            self._test_btn.setText("Enable Test Mode")
            self._test_btn.setStyleSheet(
                f"QPushButton{{background:{T['surface2']};color:{T['text']};"
                f"border:1px solid {T['border']};border-radius:10px;"
                f"font-size:13px;font-weight:600;}}"
                f"QPushButton:hover{{background:{T['accent']};color:white;border:none;}}")
            print("[TestMode] DISABLED — reverted to personal threshold")


class Dashboard(QMainWindow):

    session_start_requested  = pyqtSignal()
    session_stop_requested   = pyqtSignal()
    pipeline_data_received   = pyqtSignal(dict)
    tcn_prediction_received  = pyqtSignal(str, list)
    reward_received          = pyqtSignal(int, int, float, str)
    verification_failed      = pyqtSignal()
    break_reminder_triggered = pyqtSignal(float)
    strain_forecast_received = pyqtSignal(str, str, float)
    logout_requested         = pyqtSignal()

    def __init__(self, session_manager=None, user_id='user_001'):
        super().__init__()
        self.session_manager     = session_manager
        self._current_user_id    = user_id
        self.pipeline            = MockPipeline() if session_manager is None else None
        self._session_active     = False
        self._session_seconds  = 0
        self._reward_points    = 0
        self._high_strain_secs = 0
        self._vfq_buffer       = []
        self._vfq_at_trigger   = 0.0
        self._last_vfq         = 0.0
        self._intervention     = None
        self._popup_showing    = False  # True while action selection popup is open

        self.setWindowTitle("EyeStrain AI")
        self.setMinimumSize(1000, 660)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self._build_ui()
        self._start_timers()

        QTimer.singleShot(3000, self._check_weekly_ping)
        self._ping_timer = QTimer(self)
        self._ping_timer.timeout.connect(self._check_weekly_ping)
        self._ping_timer.start(3600 * 1000)

    def _build_ui(self):
        self.setStyleSheet(f"QMainWindow{{background:{T['bg']};}}")
        central = QWidget(); central.setStyleSheet(f"background:{T['bg']};")
        self.setCentralWidget(central)
        root = QHBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        self.sidebar = QFrame(); self.sidebar.setFixedWidth(200)
        self.sidebar.setStyleSheet(
            f"QFrame{{background:{T['surface']};border-right:1px solid {T['border']};}}")
        sb = QVBoxLayout(self.sidebar); sb.setContentsMargins(0,20,0,20); sb.setSpacing(2)

        # ── App title ──
        logo_row = QHBoxLayout(); logo_row.setContentsMargins(4, 0, 4, 12); logo_row.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background:{T['accent']}; border-radius:4px;")
        logo_lbl = QLabel("EyeStrain AI")
        logo_lbl.setStyleSheet(
            f"color:{T['text']}; font-size:13px; font-weight:700; letter-spacing:0.5px;")
        logo_row.addWidget(dot)
        logo_row.addWidget(logo_lbl)
        logo_row.addStretch()
        sb.addLayout(logo_row)
        sb.addSpacing(4)

        self.nav_live      = NavButton("", "Live Monitor")
        self.nav_analytics = NavButton("", "Analytics")
        self.nav_reports   = NavButton("", "Reports")
        self.nav_settings  = NavButton("", "Settings")
        self.nav_profile   = NavButton("", "Profile")
        self.nav_testmode  = NavButton("", "Test Mode")
        self.nav_live.setChecked(True)

        for i, btn in enumerate([self.nav_live, self.nav_analytics,
                                  self.nav_reports, self.nav_settings,
                                  self.nav_profile, self.nav_testmode]):
            btn.clicked.connect(lambda _, idx=i: self._switch_screen(idx))
            sb.addWidget(btn)

        sb.addStretch()
        session_wrap = QWidget()
        session_wrap.setContentsMargins(12, 0, 12, 0)
        sw_lay = QVBoxLayout(session_wrap); sw_lay.setContentsMargins(0,0,0,0)
        self.sidebar_session_btn = QPushButton("Start Session")
        self.sidebar_session_btn.setFixedHeight(38)
        self.sidebar_session_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._style_session_btn(False)
        self.sidebar_session_btn.clicked.connect(self._toggle_session)
        sw_lay.addWidget(self.sidebar_session_btn)
        sb.addWidget(session_wrap); sb.addSpacing(6)

        dot_wrap = QWidget(); dot_wrap.setContentsMargins(12,0,12,0)
        dw_lay = QHBoxLayout(dot_wrap); dw_lay.setContentsMargins(0,0,0,0)
        self.status_dot = QLabel("Idle")
        self.status_dot.setStyleSheet(
            f"color:{T['text3']}; font-size:11px; padding:4px 0;")
        dw_lay.addWidget(self.status_dot)
        sb.addWidget(dot_wrap)
        root.addWidget(self.sidebar)

        right_widget = QWidget(); right_widget.setStyleSheet(f"background:{T['bg']};")
        right_layout = QVBoxLayout(right_widget); right_layout.setContentsMargins(0,0,0,0); right_layout.setSpacing(0)

        self._weekly_banner = QFrame()
        self._weekly_banner.setStyleSheet("QFrame{background:#FEF3C7;border-bottom:2px solid #F59E0B;}")
        self._weekly_banner.setFixedHeight(52); self._weekly_banner.hide()
        bl = QHBoxLayout(self._weekly_banner); bl.setContentsMargins(20,0,20,0); bl.setSpacing(12)
        bell = QLabel("")
        banner_text = QLabel("Your weekly eye health report is ready — download it from the Reports tab.")
        banner_text.setStyleSheet("color:#92400E;font-size:12px;font-weight:600;background:transparent;")
        dl_now = QPushButton("Download Now"); dl_now.setFixedHeight(30); dl_now.setFixedWidth(120)
        dl_now.setCursor(Qt.CursorShape.PointingHandCursor)
        dl_now.setStyleSheet("QPushButton{background:#F59E0B;color:white;border:none;border-radius:6px;font-size:11px;font-weight:700;}QPushButton:hover{background:#D97706;}")
        dl_now.clicked.connect(self._on_weekly_banner_download)
        remind = QPushButton("Remind Later"); remind.setFixedHeight(30); remind.setFixedWidth(100)
        remind.setCursor(Qt.CursorShape.PointingHandCursor)
        remind.setStyleSheet("QPushButton{background:transparent;color:#92400E;border:1px solid #F59E0B;border-radius:6px;font-size:11px;}QPushButton:hover{background:#FDE68A;}")
        remind.clicked.connect(self._on_weekly_banner_dismiss)
        bl.addWidget(bell); bl.addWidget(banner_text); bl.addStretch(); bl.addWidget(dl_now); bl.addWidget(remind)

        self.stack = QStackedWidget(); self.stack.setStyleSheet(f"background:{T['bg']};")
        self.screen_live      = LiveScreen()
        self.screen_analytics = AnalyticsScreen(user_id=getattr(self, '_current_user_id', 'user_001'))
        self.screen_reports   = ReportsScreen(user_id=getattr(self, '_current_user_id', 'user_001'))
        self.screen_settings  = SettingsScreen()
        self.screen_profile   = ProfileScreen(user_id=getattr(self, '_current_user_id', 'user_001'))
        self.screen_testmode  = TestModeScreen()
        for s in [self.screen_live, self.screen_analytics,
                  self.screen_reports, self.screen_settings,
                  self.screen_profile, self.screen_testmode]:
            self.stack.addWidget(s)

        # ── Custom titlebar (frameless window drag handle + controls) ──────────
        self._titlebar = QWidget()
        self._titlebar.setFixedHeight(44)
        self._titlebar.setStyleSheet(
            f"background:{T['surface']}; border-bottom:1px solid {T['border']};")
        self._drag_pos = None

        def _tb_mouse_press(e):
            if e.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        def _tb_mouse_move(e):
            if e.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
                self.move(e.globalPosition().toPoint() - self._drag_pos)
        def _tb_mouse_release(e):
            self._drag_pos = None
        self._titlebar.mousePressEvent   = _tb_mouse_press
        self._titlebar.mouseMoveEvent    = _tb_mouse_move
        self._titlebar.mouseReleaseEvent = _tb_mouse_release

        hbl = QHBoxLayout(self._titlebar)
        hbl.setContentsMargins(16, 0, 12, 0)
        hbl.setSpacing(10)
        hbl.addStretch()

        self._header_user_lbl = QLabel("")
        self._header_user_lbl.setStyleSheet(
            f"color:{T['text3']}; font-size:11px;")
        hbl.addWidget(self._header_user_lbl)

        # Separator
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color:{T['border']}; max-width:1px;")
        sep.setFixedHeight(16)
        hbl.addWidget(sep)

        self._header_logout_btn = QPushButton("Sign Out")
        self._header_logout_btn.setFixedHeight(26)
        self._header_logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header_logout_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{T['text3']};"
            f"border:none;font-size:11px;padding:0 8px;}}"
            f"QPushButton:hover{{color:{T['text']};}}")
        self._header_logout_btn.clicked.connect(self._on_logout)
        hbl.addWidget(self._header_logout_btn)

        # Window controls
        for symbol, tip, slot in [
            ("–", "Minimize", self.showMinimized),
            ("□", "Maximize", lambda: self.showNormal() if self.isMaximized() else self.showMaximized()),
            ("×", "Close",    self.close),
        ]:
            btn = QPushButton(symbol)
            btn.setFixedSize(32, 32)
            btn.setToolTip(tip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            is_close = symbol == "×"
            btn.setStyleSheet(
                f"QPushButton{{background:transparent;color:{T['text2']};"
                f"border:none;font-size:{'16' if is_close else '14'}px;border-radius:4px;}}"
                f"QPushButton:hover{{background:{'#C42B1C' if is_close else T['surface2']};"
                f"color:{'white' if is_close else T['text']};}}")
            btn.clicked.connect(slot)
            hbl.addWidget(btn)

        right_layout.addWidget(self._titlebar)

        right_layout.addWidget(self._weekly_banner)
        right_layout.addWidget(self.stack)
        root.addWidget(right_widget)

        self.pipeline_data_received.connect(self._on_pipeline_data)
        self.tcn_prediction_received.connect(self._on_tcn_prediction)
        self.reward_received.connect(self._on_reward)
        self.verification_failed.connect(self._on_verification_failed)
        self.break_reminder_triggered.connect(self._on_break_reminder)
        self.strain_forecast_received.connect(self._on_strain_forecast)

    def _style_session_btn(self, active):
        if active:
            self.sidebar_session_btn.setText("Stop Session")
            self.sidebar_session_btn.setStyleSheet(
                f"QPushButton{{background:{T['red']}40;color:{T['red']};"
                f"border:1px solid {T['red']}60;border-radius:8px;"
                f"font-size:12px;font-weight:600;}}"
                f"QPushButton:hover{{background:{T['red']}60;}}")
        else:
            self.sidebar_session_btn.setText("Start Session")
            self.sidebar_session_btn.setStyleSheet(
                f"QPushButton{{background:{T['accent']};color:white;"
                f"border:none;border-radius:8px;font-size:12px;font-weight:600;}}"
                f"QPushButton:hover{{background:{T['accent2']};}}")

    def _switch_screen(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, btn in enumerate([self.nav_live, self.nav_analytics,
                                  self.nav_reports, self.nav_settings,
                                  self.nav_profile, self.nav_testmode]):
            btn.setChecked(i == idx)
        if idx == 1:
            self.screen_analytics.load_history()
        if idx == 4:  # Profile
            self.screen_profile.refresh()

    def _toggle_session(self):
        if self._session_active:
            self._session_active=False; self._session_seconds=0; self._vfq_buffer=[]
            self._style_session_btn(False)
            self.status_dot.setText("Idle"); self.status_dot.setStyleSheet(f"color:{T['text3']};font-size:11px;")
            self.screen_live.chart.clear(); self.screen_analytics.clear_live_session()
            if self.session_manager is not None: self.session_stop_requested.emit()
        else:
            self._session_active=True; self._session_seconds=0
            self._reward_points=0; self._high_strain_secs=0; self._vfq_buffer=[]
            self._style_session_btn(True)
            self.status_dot.setText("Live"); self.status_dot.setStyleSheet(f"color:{T['green']};font-size:11px;font-weight:600;")
            self.screen_live.chart.clear()
            if self.session_manager is not None:
                self.session_start_requested.emit()
                try:
                    self._reward_points=self.session_manager.reward_system.total_points
                    self.screen_live.update_rewards(self._reward_points)
                except Exception: pass

    def _start_timers(self):
        self.data_timer = QTimer(self); self.data_timer.timeout.connect(self._tick); self.data_timer.start(1000)

    def _tick(self):
        if not self._session_active: return
        if self.session_manager is not None:
            self._session_seconds += 1; self.screen_live.update_timer(self._session_seconds)
            vfq = self._last_vfq; self._vfq_buffer.append(vfq)
            if len(self._vfq_buffer)>300: self._vfq_buffer.pop(0)
            if vfq>=60: self._high_strain_secs+=1
            prevented=max(0,(self._session_seconds*0.5-self._high_strain_secs))/60
            self.screen_live.update_prevented(prevented); self.screen_live.update_rewards(self._reward_points)
            return
        data=self.pipeline.update() if self.pipeline else {}
        self._session_seconds+=1; self.screen_live.update_timer(self._session_seconds)
        self.screen_live.update_data(data); self.screen_live.chart.add_point(data.get('vfq_score',0))
        vfq=data.get('vfq_score',0); self._last_vfq=vfq; self._vfq_buffer.append(vfq)
        if len(self._vfq_buffer)>300: self._vfq_buffer.pop(0)
        if vfq>=60: self._high_strain_secs+=1
        prevented=max(0,(self._session_seconds*0.5-self._high_strain_secs))/60
        self.screen_live.update_prevented(prevented); self.screen_live.update_rewards(self._reward_points)

    def _load_ping_state(self):
        try:
            if PING_PATH.exists():
                with open(PING_PATH) as f: return json.load(f)
        except Exception: pass
        return {'last_ping':None,'last_download':None}

    def _save_ping_state(self, state):
        try:
            PING_PATH.parent.mkdir(parents=True,exist_ok=True)
            with open(PING_PATH,'w') as f: json.dump(state,f,indent=2)
        except Exception as e: print(f"[WeeklyPing] {e}")

    def _check_weekly_ping(self):
        state=self._load_ping_state(); now=datetime.now()
        last_ping=state.get('last_ping')
        if last_ping:
            try:
                if (now-datetime.fromisoformat(last_ping)).days<7: return
            except Exception: pass
        self._weekly_banner.show()

    def _on_weekly_banner_download(self):
        self._weekly_banner.hide()
        state=self._load_ping_state()
        state['last_ping']=state['last_download']=datetime.now().isoformat()
        self._save_ping_state(state); self._switch_screen(2)
        QTimer.singleShot(400,lambda:self.screen_reports._generate_ai_report('7days'))

    def _on_weekly_banner_dismiss(self):
        self._weekly_banner.hide()
        state=self._load_ping_state()
        state['last_ping']=(datetime.now()-timedelta(days=6)).isoformat()
        self._save_ping_state(state)

    def trigger_break_reminder(self, vfq: float):
        self.break_reminder_triggered.emit(vfq)

    def _on_logout(self):
        """Stop session if running, emit logout_requested for session_manager to handle."""
        if self._session_active:
            self._toggle_session()
        self.logout_requested.emit()
        self.hide()

    def update_strain_forecast(self, level, message, minutes):
        """Called from session_manager background thread — safe emit."""
        self.strain_forecast_received.emit(
            level or '',
            str(message),
            float(minutes if minutes and minutes >= 0 else -1)
        )

    def _on_strain_forecast(self, level: str, message: str, minutes: float):
        """
        Runs on main thread.
        Shows a small non-intrusive toast in the bottom-right corner.
        No sidebar glow — keeps the UI clean.
        """
        if not hasattr(self, '_forecast_toast'):
            self._forecast_toast = QLabel("", self)
            self._forecast_toast.setFixedWidth(240)
            self._forecast_toast.setWordWrap(True)
            self._forecast_toast.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self._forecast_toast.hide()
        if not hasattr(self, '_forecast_timer'):
            self._forecast_timer = QTimer(self)
            self._forecast_timer.setSingleShot(True)
            self._forecast_timer.timeout.connect(self._forecast_toast.hide)

        if level == 'orange':
            msg  = f"Strain predicted in {minutes:.0f} min" if minutes > 0 else "Strain imminent"
            col  = "#F97316"
            bg   = "#1C0A00"
            bord = "#92400E"
        elif level == 'yellow':
            msg  = f"Strain expected ~{minutes:.0f} min"
            col  = "#F59E0B"
            bg   = "#1A1200"
            bord = "#854D0E"
        else:
            self._forecast_toast.hide()
            self._forecast_timer.stop()
            return

        self._forecast_toast.setText(msg)
        self._forecast_toast.setStyleSheet(
            f"QLabel{{background:{bg}; color:{col}; border:1px solid {bord};"
            f"border-radius:8px; padding:8px 12px; font-size:11px;"
            f"font-weight:600;}}")
        self._forecast_toast.adjustSize()

        # Position: bottom-right of the main window content area
        geo  = self.geometry()
        tw   = self._forecast_toast.width()
        th   = self._forecast_toast.height()
        self._forecast_toast.move(geo.width() - tw - 20,
                                  geo.height() - th - 20)
        self._forecast_toast.raise_()
        self._forecast_toast.show()
        self._forecast_timer.start(8000)  # auto-hide after 8 seconds

    def _on_break_reminder(self, vfq: float):
        # Block if intervention screen is already open
        if self._intervention is not None:
            print("[Dashboard] Break reminder skipped — intervention already open")
            return
        # Block if recovery popup is already showing (user is choosing action)
        if getattr(self, '_popup_showing', False):
            print("[Dashboard] Break reminder skipped — action popup already open")
            return
        if not self._session_active:
            print("[Dashboard] Break reminder skipped — no active session")
            return
        self._vfq_at_trigger = vfq
        self._fire_break_reminder()

    def _fire_break_reminder(self):
        print(f"[Dashboard] Firing break reminder — VFQ={self._vfq_at_trigger:.1f}")
        self._popup_showing = True   # block any new reminders while popup is open
        popup = RecoveryPopup(self._vfq_at_trigger, self)
        # Center exactly on screen
        screen_geo = QApplication.primaryScreen().geometry()
        popup.adjustSize()
        popup.move(
            screen_geo.center().x() - popup.width()  // 2,
            screen_geo.center().y() - popup.height() // 2
        )
        popup.raise_()
        popup.activateWindow()
        result = popup.exec()
        self._popup_showing = False  # popup closed — allow reminders again

        print(f"[Dashboard] Break popup result={result} selected={popup.get_selected_action()}")
        if result == QDialog.DialogCode.Accepted:
            action = popup.get_selected_action()
            if not action:
                return
            print(f"[Dashboard] Action selected: {action}")
            if self.session_manager is not None:
                self.session_manager.reward_system.on_break_triggered(
                    vfq_at_trigger=self._vfq_at_trigger, action=action)
            self._intervention = InterventionScreen(
                action=action, vfq_at_trigger=self._vfq_at_trigger, parent=self)
            self._intervention.closed_signal.connect(self._on_intervention_closed)
            self._intervention.show()
            # Center on screen
            screen_geo = QApplication.primaryScreen().geometry()
            self._intervention.move(
                screen_geo.center().x() - self._intervention.width()  // 2,
                screen_geo.center().y() - self._intervention.height() // 2
            )
            self._intervention.raise_()
            self._intervention.activateWindow()
        else:
            print("[Dashboard] Break reminder — no action selected")
            if self.session_manager is not None:
                self.session_manager.reward_system.on_break_skipped()

    def _on_intervention_closed(self, reason: str):
        if reason=='completed':
            if self._intervention and self._intervention._tier:
                self._reward_points+=self._intervention._tier['points']
                self.screen_live.update_rewards(self._reward_points)
        self._intervention=None

    def update_from_pipeline(self, data: dict):
        self.pipeline_data_received.emit(data)

    def _on_pipeline_data(self, data: dict):
        vfq = data.get('vfq_score', 0) or 0
        self._last_vfq = vfq
        # Pass full data dict to update_data so gauge, label, trend all update
        self.screen_live.update_data(data)
        self.screen_live.chart.add_point(vfq)
        try:
            recoveries=0
            if self.session_manager is not None:
                recoveries=self.session_manager.reward_system.total_recoveries
            self.screen_analytics.update_live(data=data,session_active=self._session_active,
                session_seconds=self._session_seconds,reward_points=self._reward_points,
                session_recoveries=recoveries)
        except Exception as e: print(f"[Analytics Live] {e}")

        if self._intervention:
            try:
                if not self._intervention.isVisible(): self._intervention=None
                else:
                    self._intervention.update_vfq(vfq)
                    if self.session_manager is not None:
                        rs=self.session_manager.reward_system
                        conf=0.0; av=False; st=""
                        if rs._action_verifier:
                            conf=rs._action_verifier.confidence
                            av=rs._action_verifier.verified
                            st=rs._action_verifier.status_text
                        self._intervention.update_action_confidence(conf,av,st)
            except RuntimeError: self._intervention=None

    def update_tcn_prediction(self, label, probs):
        self.tcn_prediction_received.emit(label,list(probs))

    def _on_tcn_prediction(self, label: str, probs: list):
        self.screen_live.update_tcn_prediction(label,probs)

    def show_reward(self, points, total, drop, tier_name='Bronze'):
        self.reward_received.emit(int(points),int(total),float(drop),tier_name)

    def _on_reward(self, points: int, total: int, drop: float, tier_name: str='Bronze'):
        self._reward_points=total; self.screen_live.update_rewards(total)
        if self._intervention:
            try:
                if self._intervention.isVisible():
                    tier={'name':tier_name,
                        'icon':{'Gold':'G','Silver':'S','Bronze':'B'}.get(tier_name,'B'),
                        'color':{'Gold':'#F59E0B','Silver':'#9CA3AF','Bronze':'#B45309'}.get(tier_name,'#B45309'),
                        'border':{'Gold':'#F59E0B','Silver':'#9CA3AF','Bronze':'#D97706'}.get(tier_name,'#D97706'),
                        'points':points}
                    self._intervention.on_recovery_confirmed(tier,drop)
            except RuntimeError: self._intervention=None

    def show_verification_failed(self): self.verification_failed.emit()
    def _on_verification_failed(self): pass
    def run(self): self.show()


# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("EyeStrain AI")
    # Load font and apply global stylesheet from ui_system
    try:
        from ui_system import setup_font, global_stylesheet
        setup_font(app)
        app.setStyleSheet(global_stylesheet())
    except ImportError:
        app.setStyleSheet(f"""
            * {{ font-family: 'Segoe UI', sans-serif; font-size: 13px; }}
            QToolTip {{ background:{T['surface']}; color:{T['text']};
                       border:1px solid {T['border']}; border-radius:6px; padding:4px 8px; }}
        """)
    window = Dashboard()
    window.show()
    sys.exit(app.exec())

if __name__=='__main__':
    main()