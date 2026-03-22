"""
dashboard/main.py
EyeStrain AI — Main Dashboard
PyQt6 | Auto theme | Smooth, minimal, professional

Screens:
  1. Live Monitor  — VFQ gauge, strain, blink, timer, chart
  2. Analytics     — 7-day chart, session table, strain pie, blink trend, focus points
  3. Reports       — Monthly PDF + CSV export
  4. Settings      — Thresholds, preferences

Run standalone (mock data):
  python dashboard/main.py

Run wired to live pipeline:
  python src/session_manager.py --dashboard
"""

import sys
import os
import json
import random
import math
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QFrame, QStackedWidget,
    QDialog, QGridLayout, QSizePolicy, QScrollArea,
    QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QPainterPath, QPalette
)

# ── PATHS ─────────────────────────────────────────────────────────────────────
ROOT_DIR      = Path(__file__).parent.parent
DATA_DIR      = ROOT_DIR / 'data'
REPORTS_DIR   = ROOT_DIR / 'reports'
REPORTS_DIR.mkdir(exist_ok=True)

# ── THEME ─────────────────────────────────────────────────────────────────────
def is_dark_mode():
    app = QApplication.instance()
    if app:
        return app.palette().color(QPalette.ColorRole.Window).lightness() < 128
    return False

def make_theme():
    dark = is_dark_mode()
    if dark:
        return {
            'bg': '#0F0F0F', 'surface': '#1A1A1A', 'surface2': '#242424',
            'border': '#2E2E2E', 'text': '#F0F0F0', 'text2': '#8A8A8A',
            'text3': '#555555', 'accent': '#3B82F6', 'accent_soft': '#1D4ED8',
            'green': '#10B981', 'yellow': '#F59E0B', 'orange': '#F97316',
            'red': '#EF4444', 'dark': True,
        }
    return {
        'bg': '#F5F5F5', 'surface': '#FFFFFF', 'surface2': '#F0F0F0',
        'border': '#E5E5E5', 'text': '#111111', 'text2': '#666666',
        'text3': '#AAAAAA', 'accent': '#2563EB', 'accent_soft': '#DBEAFE',
        'green': '#059669', 'yellow': '#D97706', 'orange': '#EA580C',
        'red': '#DC2626', 'dark': False,
    }

T = make_theme()

VERIFY_WINDOW_SECS = 300

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
        self.vfq = 25.0
        self.blink_rate = 9.5
        self.trend = 'STABLE'

    def update(self):
        self.vfq = max(0, min(100, self.vfq + random.gauss(0, 2)))
        self.blink_rate = max(2, min(20, self.blink_rate + random.gauss(0, 0.3)))
        self.trend = ('WORSENING' if self.vfq > 50
                      else 'IMPROVING' if self.vfq < 25 else 'STABLE')
        return {
            'vfq_score': self.vfq, 'blink_rate': self.blink_rate,
            'strain_trend': self.trend,
            'strain_label': strain_label_from_vfq(self.vfq),
        }

# ── CUSTOM WIDGETS ────────────────────────────────────────────────────────────

class VFQGauge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._target = 0.0
        self.setMinimumSize(220, 220)
        self.setMaximumSize(220, 220)
        t = QTimer(self)
        t.timeout.connect(self._animate)
        t.start(16)

    def set_value(self, v):
        self._target = max(0.0, min(100.0, v))

    def _animate(self):
        diff = self._target - self._value
        if abs(diff) > 0.3:
            self._value += diff * 0.12
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2
        r = min(w, h) // 2 - 18
        pen_w = 14
        p.setPen(QPen(QColor(T['border']), pen_w, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.drawArc(cx-r, cy-r, r*2, r*2, 225*16, -270*16)
        color = QColor(strain_color(self._value))
        angle = int((self._value / 100.0) * 270 * 16)
        p.setPen(QPen(color, pen_w, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.drawArc(cx-r, cy-r, r*2, r*2, 225*16, -angle)
        p.setPen(QColor(T['text']))
        f = QFont('SF Pro Display', 32, QFont.Weight.Bold)
        f.setStyleHint(QFont.StyleHint.SansSerif)
        p.setFont(f)
        p.drawText(0, cy-28, w, 40, Qt.AlignmentFlag.AlignCenter,
                   f"{int(self._value)}")
        p.setPen(QColor(T['text2']))
        f2 = QFont('SF Pro Display', 10)
        f2.setStyleHint(QFont.StyleHint.SansSerif)
        p.setFont(f2)
        p.drawText(0, cy+10, w, 24, Qt.AlignmentFlag.AlignCenter, 'VFQ Score')
        p.setPen(QColor(strain_color(self._value)))
        f3 = QFont('SF Pro Display', 11, QFont.Weight.Bold)
        f3.setStyleHint(QFont.StyleHint.SansSerif)
        p.setFont(f3)
        p.drawText(0, cy+30, w, 24, Qt.AlignmentFlag.AlignCenter,
                   strain_label_from_vfq(self._value))
        p.end()


class MiniChart(QWidget):
    def __init__(self, max_points=120, parent=None):
        super().__init__(parent)
        self.max_points = max_points
        self.data = []
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
        pad = 12
        ch = h - pad * 2
        cw = w - pad * 2
        n = len(self.data)
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
            else: path.lineTo(x, y)
        last_v = self.data[-1]
        color = QColor(strain_color(last_v))
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
    """Simple pie chart for strain level breakdown."""

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
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        r = min(w, h) // 2 - 8
        cx, cy = w // 2, h // 2
        total = sum(v for v, _ in self.data) or 1
        angle = 90 * 16
        for val, color in self.data:
            span = int((val / total) * 360 * 16)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(color)))
            p.drawPie(cx-r, cy-r, r*2, r*2, angle, -span)
            angle -= span
        # White center hole
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
        self._label_w.setStyleSheet(
            f"color:{T['text2']}; font-size:11px; border:none;")
        self._value_w = QLabel(value)
        self._value_w.setStyleSheet(
            f"color:{color or T['text']}; font-size:22px;"
            f"font-weight:700; border:none;")
        self._unit_w = QLabel(unit)
        self._unit_w.setStyleSheet(
            f"color:{T['text3']}; font-size:10px; border:none;")
        layout.addWidget(self._label_w)
        layout.addWidget(self._value_w)
        layout.addWidget(self._unit_w)

    def set_value(self, v, color=None):
        self._value_w.setText(str(v))
        if color:
            self._value_w.setStyleSheet(
                f"color:{color}; font-size:22px; font-weight:700; border:none;")


class NavButton(QPushButton):
    def __init__(self, icon_text, label, parent=None):
        super().__init__(parent)
        self.setText(f"  {icon_text}  {label}")
        self.setCheckable(True)
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style(False)

    def _update_style(self, active):
        if active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {T['accent']}; color: white;
                    border: none; border-radius: 10px;
                    font-size: 13px; font-weight: 600;
                    text-align: left; padding-left: 12px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {T['text2']};
                    border: none; border-radius: 10px;
                    font-size: 13px; text-align: left; padding-left: 12px;
                }}
                QPushButton:hover {{
                    background: {T['surface2']}; color: {T['text']};
                }}
            """)

    def setChecked(self, v):
        super().setChecked(v)
        self._update_style(v)


# ── POPUPS ────────────────────────────────────────────────────────────────────

class RecoveryPopup(QDialog):
    ACTIONS = [
        ("👀", "20-20-20 Rule",  "Look 20ft away for 20 seconds"),
        ("💧", "Eye Drops",       "Blink rapidly 10 times"),
        ("🧘", "Neck Stretch",    "Tilt head side to side slowly"),
        ("🚶", "Stand & Walk",    "Step away from screen for 2 min"),
        ("🌿", "Look at Nature",  "Find something green to focus on"),
    ]

    def __init__(self, vfq_at_trigger, parent=None):
        super().__init__(parent)
        self.vfq_at_trigger  = vfq_at_trigger
        self._selected_action = None
        self.setWindowTitle("Break Time")
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedWidth(400)
        self.setStyleSheet(f"""
            QDialog {{
                background: {T['surface']};
                border: 1px solid {T['border']};
                border-radius: 16px;
            }}
        """)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)
        header = QLabel("⚠️  Break Reminder")
        header.setStyleSheet(
            f"color:{T['orange']}; font-size:16px; font-weight:700;")
        layout.addWidget(header)
        sub = QLabel(
            f"Your VFQ reached {int(self.vfq_at_trigger)} — "
            f"{strain_label_from_vfq(self.vfq_at_trigger)} strain detected")
        sub.setStyleSheet(f"color:{T['text2']}; font-size:12px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"color:{T['border']};")
        layout.addWidget(div)
        action_lbl = QLabel("Choose a recovery action:")
        action_lbl.setStyleSheet(
            f"color:{T['text']}; font-size:13px; font-weight:600;")
        layout.addWidget(action_lbl)
        for icon, name, desc in self.ACTIONS:
            btn = QPushButton(f"{icon}  {name}  —  {desc}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {T['surface2']}; color: {T['text']};
                    border: 1px solid {T['border']}; border-radius: 10px;
                    padding: 10px 14px; font-size: 12px; text-align: left;
                }}
                QPushButton:hover {{
                    background: {T['accent_soft']};
                    border-color: {T['accent']}; color: {T['accent']};
                }}
            """)
            btn.clicked.connect(lambda _, n=name: self._action_selected(n))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            layout.addWidget(btn)
        skip = QPushButton("Skip for now")
        skip.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {T['text3']};
                border: none; font-size: 11px;
            }}
            QPushButton:hover {{ color: {T['text2']}; }}
        """)
        skip.clicked.connect(self.reject)
        layout.addWidget(skip, alignment=Qt.AlignmentFlag.AlignCenter)

    def _action_selected(self, action_name):
        self._selected_action = action_name
        self.accept()

    def get_selected_action(self):
        return self._selected_action


class RewardPopup(QDialog):
    def __init__(self, points, total, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint |
                            Qt.WindowType.Dialog)
        self.setFixedSize(320, 220)
        self.setStyleSheet(f"""
            QDialog {{
                background: {T['surface']};
                border: 2px solid {T['green']};
                border-radius: 16px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(12)
        star = QLabel("🏆")
        star.setStyleSheet("font-size: 40px;")
        star.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(star)
        title = QLabel("Recovery Verified!")
        title.setStyleSheet(
            f"color:{T['green']}; font-size:18px; font-weight:700;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        pts = QLabel(f"+{points} points  ·  Total: {total}")
        pts.setStyleSheet(f"color:{T['text2']}; font-size:12px;")
        pts.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(pts)
        ok = QPushButton("Continue")
        ok.setStyleSheet(f"""
            QPushButton {{
                background: {T['green']}; color: white;
                border: none; border-radius: 10px;
                padding: 10px; font-size: 13px; font-weight: 600;
            }}
        """)
        ok.clicked.connect(self.accept)
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(ok)
        QTimer.singleShot(4000, self.accept)


# ── SCREENS ───────────────────────────────────────────────────────────────────

class LiveScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(16)

        title = QLabel("Live Monitor")
        title.setStyleSheet(
            f"color:{T['text']}; font-size:20px; font-weight:700;")
        layout.addWidget(title)

        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        gauge_card = QFrame()
        gauge_card.setStyleSheet(f"""
            QFrame {{
                background: {T['surface']};
                border: 1px solid {T['border']};
                border-radius: 16px;
            }}
        """)
        gl = QVBoxLayout(gauge_card)
        gl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gauge = VFQGauge()
        gl.addWidget(self.gauge, alignment=Qt.AlignmentFlag.AlignCenter)
        trend_row = QHBoxLayout()
        self.trend_label = QLabel("→  STABLE")
        self.trend_label.setStyleSheet(
            f"color:{T['text2']}; font-size:12px; font-weight:600;")
        trend_row.addStretch()
        trend_row.addWidget(self.trend_label)
        trend_row.addStretch()
        gl.addLayout(trend_row)

        # TCN prediction label
        self.tcn_label_w = QLabel("🤖 Model: --")
        self.tcn_label_w.setStyleSheet(
            f"color:{T['text3']}; font-size:12px; font-weight:600;")
        trend_row2 = QHBoxLayout()
        trend_row2.addStretch()
        trend_row2.addWidget(self.tcn_label_w)
        trend_row2.addStretch()
        gl.addLayout(trend_row2)

        top_row.addWidget(gauge_card)

        stats_widget = QWidget()
        stats_grid = QGridLayout(stats_widget)
        stats_grid.setSpacing(10)
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
            QFrame {{
                background: {T['surface']};
                border: 1px solid {T['border']};
                border-radius: 16px;
            }}
        """)
        cl = QVBoxLayout(chart_card)
        cl.setContentsMargins(16, 12, 16, 12)
        ch_header = QHBoxLayout()
        chart_lbl = QLabel("VFQ — Current Session")
        chart_lbl.setStyleSheet(
            f"color:{T['text']}; font-size:13px; font-weight:600;")
        self.live_lbl = QLabel("● LIVE")
        self.live_lbl.setStyleSheet(f"color:{T['red']}; font-size:11px;")
        ch_header.addWidget(chart_lbl)
        ch_header.addStretch()
        ch_header.addWidget(self.live_lbl)
        cl.addLayout(ch_header)
        self.chart = MiniChart(max_points=180)
        cl.addWidget(self.chart)
        layout.addWidget(chart_card)

    def update_data(self, data):
        vfq   = data.get('vfq_score', 0)
        blink = data.get('blink_rate', 0)
        trend = data.get('strain_trend', 'STABLE')
        self.gauge.set_value(vfq)
        self.blink_card.set_value(f"{blink:.1f}", T['accent'])
        arrows = {'IMPROVING': '↓', 'STABLE': '→', 'WORSENING': '↑'}
        colors = {'IMPROVING': T['green'], 'STABLE': T['text2'],
                  'WORSENING': T['red']}
        self.trend_label.setText(
            f"{arrows.get(trend,'→')}  {trend}")
        self.trend_label.setStyleSheet(
            f"color:{colors.get(trend, T['text2'])};"
            f"font-size:12px; font-weight:600;")

    def update_timer(self, seconds):
        m, s = divmod(seconds, 60)
        self.timer_card.set_value(f"{m}:{s:02d}")

    def update_rewards(self, points):
        self.reward_card.set_value(str(points), T['green'])

    def update_prevented(self, minutes):
        self.prevent_card.set_value(f"{minutes:.0f}", T['yellow'])

    def update_tcn_prediction(self, label, probs):
        """Show TCN model prediction alongside VFQ score."""
        if not hasattr(self, 'tcn_label_w'):
            return
        self.tcn_label_w.setText(f"🤖 Model: {label}")
        color = strain_color(
            [0, 20, 40, 60, 80][
                ['NORMAL', 'LOW', 'MODERATE', 'HIGH', 'SEVERE'].index(label)
                if label in ['NORMAL', 'LOW', 'MODERATE', 'HIGH', 'SEVERE']
                else 0
            ]
        )
        self.tcn_label_w.setStyleSheet(
            f"color:{color}; font-size:12px; font-weight:600;"
        )


class AnalyticsScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        content = QWidget()
        layout  = QVBoxLayout(content)
        layout.setContentsMargins(28, 20, 28, 28)
        layout.setSpacing(16)

        # Title + refresh
        title_row = QHBoxLayout()
        title = QLabel("Analytics")
        title.setStyleSheet(
            f"color:{T['text']}; font-size:20px; font-weight:700;")
        refresh_btn = QPushButton("↻  Refresh")
        refresh_btn.setFixedHeight(32)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {T['surface2']}; color: {T['text2']};
                border: 1px solid {T['border']}; border-radius: 8px;
                font-size: 12px; padding: 0 14px;
            }}
            QPushButton:hover {{
                background: {T['accent']}; color: white;
                border-color: {T['accent']};
            }}
        """)
        refresh_btn.clicked.connect(self.load_history)
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(refresh_btn)
        layout.addLayout(title_row)

        # ── Stat summary row ──
        stat_row = QHBoxLayout()
        stat_row.setSpacing(10)
        self.avg_card      = StatCard("Avg VFQ",          "--", "",    T['accent'])
        self.high_card     = StatCard("High Strain",       "--", "min", T['orange'])
        self.sessions_card = StatCard("Sessions (7d)",     "--", "",    T['text'])
        self.blink_avg_card= StatCard("Avg Blink Rate",    "--", "/min",T['green'])
        for c in [self.avg_card, self.high_card,
                  self.sessions_card, self.blink_avg_card]:
            stat_row.addWidget(c)
        layout.addLayout(stat_row)

        # ── 7-day VFQ chart ──
        vfq_card = self._make_card()
        vl = QVBoxLayout(vfq_card)
        vl.setContentsMargins(16, 14, 16, 14)
        lbl = QLabel("VFQ — Last 7 Days")
        lbl.setStyleSheet(
            f"color:{T['text']}; font-size:13px; font-weight:600;")
        vl.addWidget(lbl)
        self.week_chart = MiniChart(max_points=300)
        self.week_chart.setMinimumHeight(130)
        vl.addWidget(self.week_chart)
        layout.addWidget(vfq_card)

        # ── Blink rate trend ──
        blink_card = self._make_card()
        bl = QVBoxLayout(blink_card)
        bl.setContentsMargins(16, 14, 16, 14)
        blbl = QLabel("Blink Rate — Last 7 Days")
        blbl.setStyleSheet(
            f"color:{T['text']}; font-size:13px; font-weight:600;")
        bl.addWidget(blbl)
        self.blink_chart = MiniChart(max_points=300)
        self.blink_chart.setMinimumHeight(100)
        bl.addWidget(self.blink_chart)
        layout.addWidget(blink_card)

        # ── Strain breakdown + Focus points ──
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        # Strain pie
        strain_card = self._make_card()
        strain_card.setMinimumWidth(260)
        sl = QVBoxLayout(strain_card)
        sl.setContentsMargins(16, 14, 16, 14)
        sl.setSpacing(10)
        slbl = QLabel("Strain Breakdown")
        slbl.setStyleSheet(
            f"color:{T['text']}; font-size:13px; font-weight:600;")
        sl.addWidget(slbl)
        pie_row = QHBoxLayout()
        self.pie_chart = PieChart()
        pie_row.addWidget(self.pie_chart,
                          alignment=Qt.AlignmentFlag.AlignVCenter)
        # Legend
        legend_layout = QVBoxLayout()
        legend_layout.setSpacing(5)
        self.legend_labels = []
        for level, color in zip(STRAIN_LEVELS, STRAIN_COLORS):
            row = QHBoxLayout()
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{color}; font-size:12px;")
            lv  = QLabel(f"{level}  0%")
            lv.setStyleSheet(
                f"color:{T['text2']}; font-size:11px;")
            row.addWidget(dot)
            row.addWidget(lv)
            row.addStretch()
            self.legend_labels.append(lv)
            legend_layout.addLayout(row)
        pie_row.addLayout(legend_layout)
        sl.addLayout(pie_row)
        bottom_row.addWidget(strain_card)

        # Focus points
        focus_card = self._make_card()
        fl = QVBoxLayout(focus_card)
        fl.setContentsMargins(16, 14, 16, 14)
        fl.setSpacing(10)
        flbl = QLabel("🎯  Focus Points")
        flbl.setStyleSheet(
            f"color:{T['text']}; font-size:13px; font-weight:700;")
        fl.addWidget(flbl)
        self.focus_layout = QVBoxLayout()
        self.focus_layout.setSpacing(8)
        fl.addLayout(self.focus_layout)
        fl.addStretch()
        bottom_row.addWidget(focus_card)

        layout.addLayout(bottom_row)

        # ── Per-session table ──
        table_card = self._make_card()
        tl = QVBoxLayout(table_card)
        tl.setContentsMargins(16, 14, 16, 14)
        tlbl = QLabel("Session History")
        tlbl.setStyleSheet(
            f"color:{T['text']}; font-size:13px; font-weight:600;")
        tl.addWidget(tlbl)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Duration", "Avg VFQ", "Max VFQ",
             "High Strain %", "Blink Rate"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background: {T['surface']};
                border: none;
                gridline-color: {T['border']};
                font-size: 12px;
                color: {T['text']};
            }}
            QTableWidget::item {{
                padding: 8px;
            }}
            QHeaderView::section {{
                background: {T['surface2']};
                color: {T['text2']};
                border: none;
                border-bottom: 1px solid {T['border']};
                padding: 8px;
                font-size: 11px;
                font-weight: 600;
            }}
            QTableWidget::item:alternate {{
                background: {T['surface2']};
            }}
        """)
        self.table.setMinimumHeight(200)
        tl.addWidget(self.table)
        layout.addWidget(table_card)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _make_card(self):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {T['surface']};
                border: 1px solid {T['border']};
                border-radius: 16px;
            }}
        """)
        return card

    def _add_focus_point(self, icon, text, color):
        row = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"font-size:16px;")
        icon_lbl.setFixedWidth(24)
        txt_lbl = QLabel(text)
        txt_lbl.setStyleSheet(
            f"color:{color}; font-size:12px; font-weight:500;")
        txt_lbl.setWordWrap(True)
        row.addWidget(icon_lbl)
        row.addWidget(txt_lbl)
        row.addStretch()
        w = QWidget()
        w.setLayout(row)
        self.focus_layout.addWidget(w)

    def _clear_focus_points(self):
        for i in reversed(range(self.focus_layout.count())):
            item = self.focus_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()

    def load_history(self):
        """Load all session CSV data and populate analytics."""
        import glob as g
        import pandas as pd

        files = sorted(g.glob(str(DATA_DIR / 'user_001_session_*.csv')))

        if not files:
            self._add_focus_point(
                "ℹ️", "No session files found in data folder.", T['text3'])
            return

        all_vfq       = []
        all_blink     = []
        all_high_secs = 0
        n_sessions    = 0
        strain_counts = {lv: 0 for lv in STRAIN_LEVELS}
        session_rows  = []

        for f in files:
            try:
                df = pd.read_csv(f)

                # Skip empty files
                if df is None or len(df) == 0:
                    continue

                n_sessions += 1

                # ── VFQ ──
                if 'vfq_score' in df.columns:
                    vfqs = pd.to_numeric(
                        df['vfq_score'], errors='coerce'
                    ).dropna().tolist()
                    all_vfq.extend(vfqs)
                    all_high_secs += sum(1 for v in vfqs if v >= 60)
                    avg_vfq  = round(sum(vfqs) / len(vfqs), 1) if vfqs else 0
                    max_vfq  = round(max(vfqs), 1) if vfqs else 0
                    high_pct = round(
                        sum(1 for v in vfqs if v >= 60) / len(vfqs) * 100, 1
                    ) if vfqs else 0
                else:
                    avg_vfq = max_vfq = high_pct = 0
                    vfqs = []

                # ── Blink rate ──
                if 'blink_rate' in df.columns:
                    blinks = pd.to_numeric(
                        df['blink_rate'], errors='coerce'
                    ).dropna().tolist()
                    all_blink.extend(blinks)
                    avg_blink = round(
                        sum(blinks) / len(blinks), 1) if blinks else 0
                else:
                    avg_blink = 0

                # ── Strain label counts ──
                if 'strain_label' in df.columns:
                    for lv in STRAIN_LEVELS:
                        strain_counts[lv] += int(
                            (df['strain_label'] == lv).sum())

                # ── Date string ──
                try:
                    date_str = str(df['timestamp'].iloc[0])[:16]
                except Exception:
                    date_str = os.path.basename(f)[-19:-4]

                duration = len(df)
                session_rows.append({
                    'date':     date_str,
                    'duration': f"{duration // 60}m {duration % 60}s",
                    'avg_vfq':  avg_vfq,
                    'max_vfq':  max_vfq,
                    'high_pct': f"{high_pct}%",
                    'blink':    avg_blink,
                })

            except Exception as e:
                print(f"  [Analytics] Skipped {f}: {e}")
                continue

        # ── Update stat cards ──
        if all_vfq:
            self.avg_card.set_value(
                f"{sum(all_vfq)/len(all_vfq):.1f}", T['accent'])
            self.high_card.set_value(
                f"{all_high_secs//60}", T['orange'])
        self.sessions_card.set_value(str(n_sessions))
        if all_blink:
            self.blink_avg_card.set_value(
                f"{sum(all_blink)/len(all_blink):.1f}", T['green'])

        # ── VFQ chart ──
        self.week_chart.clear()
        for v in all_vfq[-300:]:
            self.week_chart.add_point(v)

        # ── Blink chart ──
        self.blink_chart.clear()
        for v in all_blink[-300:]:
            self.blink_chart.add_point(min(100, (v / 20) * 100))

        # ── Pie chart ──
        total_labels = sum(strain_counts.values()) or 1
        pie_values   = [strain_counts[lv] for lv in STRAIN_LEVELS]
        self.pie_chart.set_data(pie_values, STRAIN_COLORS)
        for lv, lbl_w in zip(STRAIN_LEVELS, self.legend_labels):
            pct = round(strain_counts[lv] / total_labels * 100, 1)
            lbl_w.setText(f"{lv}  {pct}%")

        # ── Focus points ──
        self._clear_focus_points()

        if not all_vfq:
            self._add_focus_point(
                "ℹ️",
                "No VFQ data found. Run a session to see focus points.",
                T['text3'])
        else:
            avg       = sum(all_vfq) / len(all_vfq)
            blink_avg = sum(all_blink) / len(all_blink) if all_blink else 0
            high_pct_overall = (
                strain_counts['HIGH'] + strain_counts['SEVERE']
            ) / total_labels * 100

            if avg >= 50:
                self._add_focus_point(
                    "🔴",
                    f"Avg VFQ {avg:.1f} — consistently high. "
                    "Take more frequent breaks.",
                    T['red'])
            elif avg >= 30:
                self._add_focus_point(
                    "🟡",
                    f"Avg VFQ {avg:.1f} — moderate strain. "
                    "Watch long sessions.",
                    T['yellow'])
            else:
                self._add_focus_point(
                    "🟢",
                    f"Avg VFQ {avg:.1f} — good eye health. Keep it up!",
                    T['green'])

            if blink_avg < 5:
                self._add_focus_point(
                    "👁️",
                    f"Blink rate {blink_avg:.1f}/min is below the "
                    "clinical safe threshold of 5/min. "
                    "Try conscious blinking.",
                    T['red'])
            elif blink_avg < 8:
                self._add_focus_point(
                    "👁️",
                    f"Blink rate {blink_avg:.1f}/min is low. "
                    "Blink more during screen use.",
                    T['yellow'])
            else:
                self._add_focus_point(
                    "👁️",
                    f"Blink rate {blink_avg:.1f}/min is healthy.",
                    T['green'])

            if high_pct_overall > 15:
                self._add_focus_point(
                    "⚠️",
                    f"{high_pct_overall:.1f}% of time was HIGH or SEVERE. "
                    "Reduce continuous screen time.",
                    T['red'])

            if n_sessions >= 3:
                self._add_focus_point(
                    "📅",
                    f"{n_sessions} sessions logged. Great consistency!",
                    T['green'])

            if all_high_secs > 600:
                self._add_focus_point(
                    "🕐",
                    f"{all_high_secs//60} minutes in HIGH strain. "
                    "Use the 20-20-20 rule more actively.",
                    T['orange'])

        # ── Session table ──
        self.table.setRowCount(len(session_rows))
        for row_idx, row in enumerate(reversed(session_rows)):
            vals = [
                row['date'], row['duration'],
                str(row['avg_vfq']), str(row['max_vfq']),
                row['high_pct'], str(row['blink'])
            ]
            for col_idx, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col_idx == 2:
                    try:
                        item.setForeground(
                            QColor(strain_color(float(val))))
                    except Exception:
                        pass
                self.table.setItem(row_idx, col_idx, item)

        print(f"[Analytics] Loaded {n_sessions} sessions, "
              f"{len(all_vfq)} VFQ points, "
              f"{len(all_blink)} blink points")


class ReportsScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(16)

        title = QLabel("Reports")
        title.setStyleSheet(
            f"color:{T['text']}; font-size:20px; font-weight:700;")
        layout.addWidget(title)

        export_card = QFrame()
        export_card.setStyleSheet(f"""
            QFrame {{
                background: {T['surface']};
                border: 1px solid {T['border']};
                border-radius: 16px;
            }}
        """)
        el = QVBoxLayout(export_card)
        el.setContentsMargins(24, 20, 24, 20)
        el.setSpacing(12)
        eh = QLabel("Export Monthly Report")
        eh.setStyleSheet(
            f"color:{T['text']}; font-size:14px; font-weight:700;")
        el.addWidget(eh)
        ed = QLabel(
            "Generates a full summary of strain levels, blink rates, "
            "recovery actions and rewards for the current month.")
        ed.setStyleSheet(f"color:{T['text2']}; font-size:12px;")
        ed.setWordWrap(True)
        el.addWidget(ed)
        btn_row = QHBoxLayout()
        pdf_btn = QPushButton("⬇  Export PDF")
        csv_btn = QPushButton("⬇  Export CSV")
        for btn in [pdf_btn, csv_btn]:
            btn.setFixedHeight(38)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {T['surface2']}; color: {T['text']};
                    border: 1px solid {T['border']}; border-radius: 10px;
                    font-size: 13px; padding: 0 20px;
                }}
                QPushButton:hover {{
                    background: {T['accent']}; color: white;
                    border-color: {T['accent']};
                }}
            """)
        pdf_btn.clicked.connect(self._export_pdf)
        csv_btn.clicked.connect(self._export_csv)
        btn_row.addWidget(pdf_btn)
        btn_row.addWidget(csv_btn)
        btn_row.addStretch()
        el.addLayout(btn_row)
        layout.addWidget(export_card)

        prev_card = QFrame()
        prev_card.setStyleSheet(f"""
            QFrame {{
                background: {T['surface']};
                border: 1px solid {T['border']};
                border-radius: 16px;
            }}
        """)
        pl = QVBoxLayout(prev_card)
        pl.setContentsMargins(24, 20, 24, 20)
        pl.setSpacing(8)
        ph = QLabel("Previous Reports")
        ph.setStyleSheet(
            f"color:{T['text']}; font-size:14px; font-weight:700;")
        pl.addWidget(ph)
        self.prev_list_layout = QVBoxLayout()
        pl.addLayout(self.prev_list_layout)
        layout.addWidget(prev_card)
        layout.addStretch()
        self._refresh_prev_reports()

    def _refresh_prev_reports(self):
        for i in reversed(range(self.prev_list_layout.count())):
            w = self.prev_list_layout.itemAt(i).widget()
            if w:
                w.deleteLater()
        reports = (sorted(REPORTS_DIR.glob('*.pdf')) +
                   sorted(REPORTS_DIR.glob('*.csv')))
        if not reports:
            lbl = QLabel("No reports yet.")
            lbl.setStyleSheet(f"color:{T['text3']}; font-size:12px;")
            self.prev_list_layout.addWidget(lbl)
            return
        for r in sorted(reports, reverse=True)[:10]:
            row = QHBoxLayout()
            name = QLabel(r.name)
            name.setStyleSheet(f"color:{T['text']}; font-size:12px;")
            size = QLabel(f"{r.stat().st_size // 1024} KB")
            size.setStyleSheet(f"color:{T['text3']}; font-size:11px;")
            row.addWidget(name)
            row.addStretch()
            row.addWidget(size)
            w = QWidget()
            w.setLayout(row)
            self.prev_list_layout.addWidget(w)

    def _gather_data(self):
        import glob as g
        import pandas as pd
        files  = sorted(g.glob(str(DATA_DIR / 'user_001_session_*.csv')))
        cutoff = datetime.now().replace(day=1, hour=0, minute=0, second=0)
        rows   = []
        for f in files:
            try:
                df = pd.read_csv(f)
                if 'timestamp' in df.columns:
                    df['timestamp'] = pd.to_datetime(
                        df['timestamp'], errors='coerce')
                    df = df[df['timestamp'] >= cutoff]
                rows.append(df)
            except Exception:
                pass
        return (pd.concat(rows, ignore_index=True)
                if rows else None)

    def _export_csv(self):
        df = self._gather_data()
        if df is None or len(df) == 0:
            QMessageBox.information(
                self, "No Data", "No session data found for this month.")
            return
        name = f"eyestrain_report_{datetime.now().strftime('%Y_%m')}.csv"
        path = REPORTS_DIR / name
        df.to_csv(path, index=False)
        QMessageBox.information(self, "Exported", f"CSV saved to:\n{path}")
        self._refresh_prev_reports()

    def _export_pdf(self):
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas as rl_canvas
            from reportlab.lib import colors
        except ImportError:
            QMessageBox.warning(
                self, "Missing Library",
                "pip install reportlab --break-system-packages")
            return
        df = self._gather_data()
        name = f"eyestrain_report_{datetime.now().strftime('%Y_%m')}.pdf"
        path = str(REPORTS_DIR / name)
        c = rl_canvas.Canvas(path, pagesize=A4)
        w, h = A4
        c.setFont("Helvetica-Bold", 20)
        c.drawString(50, h-60, "EyeStrain AI — Monthly Report")
        c.setFont("Helvetica", 12)
        c.setFillColor(colors.grey)
        c.drawString(50, h-85,
                     f"Generated: {datetime.now().strftime('%B %Y')}")
        c.setFillColor(colors.black)
        y = h - 140
        if df is not None and len(df) > 0:
            stats = [
                ("Total rows logged", str(len(df))),
                ("Sessions this month",
                 str(df['session_id'].nunique()
                     if 'session_id' in df.columns else '--')),
                ("Avg VFQ",
                 f"{df['vfq_score'].mean():.1f}"
                 if 'vfq_score' in df.columns else '--'),
                ("Max VFQ",
                 f"{df['vfq_score'].max():.1f}"
                 if 'vfq_score' in df.columns else '--'),
            ]
            if 'strain_label' in df.columns:
                total = len(df)
                for lv in STRAIN_LEVELS:
                    pct = (df['strain_label'] == lv).sum() / total * 100
                    stats.append((f"{lv} %", f"{pct:.1f}%"))
            c.setFont("Helvetica-Bold", 13)
            c.drawString(50, y, "Summary Statistics")
            y -= 25
            c.setFont("Helvetica", 11)
            for k, v in stats:
                c.drawString(70, y, f"{k}:  {v}")
                y -= 20
        else:
            c.drawString(50, y, "No session data found for this month.")
        c.save()
        QMessageBox.information(self, "Exported", f"PDF saved to:\n{path}")
        self._refresh_prev_reports()


class SettingsScreen(QWidget):
    SETTINGS = [
        ("🔔", "Break trigger VFQ",         "40",
         "VFQ threshold to fire break reminder",    ""),
        ("⏱",  "Break trigger duration",     "5",
         "How long VFQ must stay above threshold",  "min"),
        ("🔕", "Reminder cooldown",          "10",
         "Minimum time between reminders",          "min"),
        ("✅", "Verification window",        "5",
         "Time to verify VFQ drop after break",     "min"),
        ("📉", "VFQ drop for reward",        "20",
         "Minimum VFQ drop to confirm recovery",    "pts"),
        ("🏆", "Reward points per recovery", "10",
         "Points awarded for verified recovery",    "pts"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 20, 28, 20)
        outer.setSpacing(0)

        title = QLabel("Settings")
        title.setStyleSheet(
            f"color:{T['text']}; font-size:20px; font-weight:700;"
            f"margin-bottom:16px;")
        outer.addWidget(title)

        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {T['surface']};
                border: 1px solid {T['border']};
                border-radius: 16px;
            }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        for i, (icon, label, value, desc, unit) in enumerate(self.SETTINGS):
            row_w = QWidget()
            row_w.setStyleSheet("""
                QWidget { background: transparent; }
                QWidget:hover { background: rgba(128,128,128,0.05); }
            """)
            rl = QHBoxLayout(row_w)
            rl.setContentsMargins(24, 18, 24, 18)
            rl.setSpacing(16)

            icon_lbl = QLabel(icon)
            icon_lbl.setFixedSize(38, 38)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setStyleSheet(f"""
                background: {T['surface2']};
                border: 1px solid {T['border']};
                border-radius: 19px; font-size: 16px;
            """)

            tb = QVBoxLayout()
            tb.setSpacing(2)
            lbl = QLabel(label)
            lbl.setStyleSheet(
                f"color:{T['text']}; font-size:13px; font-weight:600;"
                f"background:transparent;")
            dsc = QLabel(desc)
            dsc.setStyleSheet(
                f"color:{T['text3']}; font-size:11px; background:transparent;")
            tb.addWidget(lbl)
            tb.addWidget(dsc)

            vc = QFrame()
            vc.setFixedWidth(90)
            vc.setFixedHeight(36)
            vc.setStyleSheet(f"""
                QFrame {{
                    background: {T['accent_soft']
                                 if not T['dark'] else '#1e3a5f'};
                    border: 1.5px solid {T['accent']};
                    border-radius: 18px;
                }}
            """)
            vl2 = QHBoxLayout(vc)
            vl2.setContentsMargins(10, 0, 10, 0)
            vl2.setSpacing(3)
            val_lbl = QLabel(value)
            val_lbl.setStyleSheet(
                f"color:{T['accent']}; font-size:13px; font-weight:700;"
                f"background:transparent; border:none;")
            val_lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if unit:
                ul = QLabel(unit)
                ul.setStyleSheet(
                    f"color:{T['accent']}; font-size:10px; font-weight:500;"
                    f"background:transparent; border:none;")
                ul.setAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                vl2.addWidget(val_lbl)
                vl2.addWidget(ul)
            else:
                val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                vl2.addWidget(val_lbl)

            rl.addWidget(icon_lbl)
            rl.addLayout(tb)
            rl.addStretch()
            rl.addWidget(vc)
            cl.addWidget(row_w)

            if i < len(self.SETTINGS) - 1:
                div = QFrame()
                div.setFrameShape(QFrame.Shape.HLine)
                div.setStyleSheet(f"""
                    QFrame {{
                        background: {T['border']}; border: none;
                        max-height: 1px; margin: 0 24px;
                    }}
                """)
                cl.addWidget(div)

        outer.addWidget(card)

        save_row = QHBoxLayout()
        save_row.setContentsMargins(0, 16, 0, 0)
        save_btn = QPushButton("Save Settings")
        save_btn.setFixedHeight(40)
        save_btn.setFixedWidth(140)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {T['accent']}; color: white;
                border: none; border-radius: 12px;
                font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{
                background: {'#1D4ED8' if not T['dark'] else T['accent_soft']};
            }}
        """)
        save_row.addStretch()
        save_row.addWidget(save_btn)
        outer.addLayout(save_row)
        outer.addStretch()


# ── MAIN WINDOW ───────────────────────────────────────────────────────────────

class Dashboard(QMainWindow):

    # Signal emitted when Start/Stop pressed in real pipeline mode
    session_start_requested  = pyqtSignal()
    session_stop_requested   = pyqtSignal()
    pipeline_data_received   = pyqtSignal(dict)
    tcn_prediction_received  = pyqtSignal(str, list)
    reward_received          = pyqtSignal(int, int, float)
    verification_failed      = pyqtSignal()
    break_reminder_triggered = pyqtSignal(float)

    def __init__(self, session_manager=None):
        super().__init__()
        self.session_manager = session_manager
        self.pipeline        = (MockPipeline()
                                if session_manager is None else None)

        self._session_active   = False
        self._session_seconds  = 0
        self._reward_points    = 0
        self._high_strain_secs = 0
        self._vfq_buffer       = []
        self._vfq_at_trigger   = 0.0
        self._break_pending    = False
        self._break_cooldown   = 0
        self._verifying        = False
        self._verify_countdown = 0
        self._last_vfq         = 0.0

        self.setWindowTitle("EyeStrain AI")
        self.setMinimumSize(900, 620)
        self._build_ui()
        self._start_timers()

    def _build_ui(self):
        self.setStyleSheet(
            f"QMainWindow {{ background: {T['bg']}; }}")

        central = QWidget()
        central.setStyleSheet(f"background: {T['bg']};")
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ──
        sidebar = QFrame()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(f"""
            QFrame {{
                background: {T['surface']};
                border-right: 1px solid {T['border']};
            }}
        """)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(12, 20, 12, 20)
        sb.setSpacing(4)

        logo = QLabel("👁  EyeStrain AI")
        logo.setStyleSheet(
            f"color:{T['text']}; font-size:14px; font-weight:700;"
            f"padding: 8px 4px 20px 4px;")
        sb.addWidget(logo)

        self.nav_live      = NavButton("◉", "Live Monitor")
        self.nav_analytics = NavButton("📈", "Analytics")
        self.nav_reports   = NavButton("📄", "Reports")
        self.nav_settings  = NavButton("⚙", "Settings")
        self.nav_live.setChecked(True)

        for i, btn in enumerate([self.nav_live, self.nav_analytics,
                                  self.nav_reports, self.nav_settings]):
            btn.clicked.connect(lambda _, idx=i: self._switch_screen(idx))
            sb.addWidget(btn)

        sb.addStretch()

        # ── Session button in sidebar ──
        self.sidebar_session_btn = QPushButton("▶  Start Session")
        self.sidebar_session_btn.setFixedHeight(40)
        self.sidebar_session_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._style_session_btn(False)
        self.sidebar_session_btn.clicked.connect(self._toggle_session)
        sb.addWidget(self.sidebar_session_btn)

        sb.addSpacing(8)
        self.status_dot = QLabel("● Idle")
        self.status_dot.setStyleSheet(
            f"color:{T['text3']}; font-size:11px; padding: 4px;")
        sb.addWidget(self.status_dot)
        root.addWidget(sidebar)

        # ── Stack ──
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background: {T['bg']};")

        self.screen_live      = LiveScreen()
        self.screen_analytics = AnalyticsScreen()
        self.screen_reports   = ReportsScreen()
        self.screen_settings  = SettingsScreen()

        self.stack.addWidget(self.screen_live)
        self.stack.addWidget(self.screen_analytics)
        self.stack.addWidget(self.screen_reports)
        self.stack.addWidget(self.screen_settings)
        root.addWidget(self.stack)

        # Wire thread-safe signals to main-thread slots
        self.pipeline_data_received.connect(self._on_pipeline_data)
        self.tcn_prediction_received.connect(self._on_tcn_prediction)
        self.reward_received.connect(self._on_reward)
        self.verification_failed.connect(self._on_verification_failed)
        self.break_reminder_triggered.connect(self._on_break_reminder)

    def _style_session_btn(self, active):
        if active:
            self.sidebar_session_btn.setText("■  Stop Session")
            self.sidebar_session_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {T['red']}; color: white;
                    border: none; border-radius: 10px;
                    font-size: 12px; font-weight: 600;
                }}
                QPushButton:hover {{ opacity: 0.85; }}
            """)
        else:
            self.sidebar_session_btn.setText("▶  Start Session")
            self.sidebar_session_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {T['accent']}; color: white;
                    border: none; border-radius: 10px;
                    font-size: 12px; font-weight: 600;
                }}
                QPushButton:hover {{ opacity: 0.85; }}
            """)

    def _switch_screen(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, btn in enumerate([self.nav_live, self.nav_analytics,
                                  self.nav_reports, self.nav_settings]):
            btn.setChecked(i == idx)
        if idx == 1:
            self.screen_analytics.load_history()

    def _toggle_session(self):
        if self._session_active:
            # Stop
            self._session_active  = False
            self._session_seconds = 0
            self._vfq_buffer      = []
            self._style_session_btn(False)
            self.status_dot.setText("● Idle")
            self.status_dot.setStyleSheet(
                f"color:{T['text3']}; font-size:11px; padding:4px;")
            self.screen_live.chart.clear()

            if self.session_manager is not None:
                self.session_stop_requested.emit()
        else:
            # Start
            self._session_active   = True
            self._session_seconds  = 0
            self._reward_points    = 0
            self._high_strain_secs = 0
            self._vfq_buffer       = []
            self._style_session_btn(True)
            self.status_dot.setText("● Live")
            self.status_dot.setStyleSheet(
                f"color:{T['green']}; font-size:11px; padding:4px;")
            self.screen_live.chart.clear()

            if self.session_manager is not None:
                self.session_start_requested.emit()

    def _start_timers(self):
        self.data_timer = QTimer(self)
        self.data_timer.timeout.connect(self._tick)
        self.data_timer.start(1000)

    def _tick(self):
        if not self._session_active:
            return

        # ── Real pipeline mode ──
        if self.session_manager is not None:
            self._session_seconds += 1
            self.screen_live.update_timer(self._session_seconds)

            vfq = self._last_vfq
            self._vfq_buffer.append(vfq)
            if len(self._vfq_buffer) > 300:
                self._vfq_buffer.pop(0)
            if vfq >= 60:
                self._high_strain_secs += 1

            prevented = max(
                0, (self._session_seconds * 0.5 - self._high_strain_secs)
            ) / 60
            self.screen_live.update_prevented(prevented)
            self.screen_live.update_rewards(self._reward_points)
            self._check_break_reminder(vfq)
            return

        # ── Mock mode ──
        data = self.pipeline.update() if self.pipeline else {}
        self._session_seconds += 1
        self.screen_live.update_timer(self._session_seconds)
        self.screen_live.update_data(data)
        self.screen_live.chart.add_point(data.get('vfq_score', 0))

        vfq = data.get('vfq_score', 0)
        self._last_vfq = vfq
        self._vfq_buffer.append(vfq)
        if len(self._vfq_buffer) > 300:
            self._vfq_buffer.pop(0)
        if vfq >= 60:
            self._high_strain_secs += 1

        prevented = max(
            0, (self._session_seconds * 0.5 - self._high_strain_secs)
        ) / 60
        self.screen_live.update_prevented(prevented)
        self.screen_live.update_rewards(self._reward_points)
        self._check_break_reminder(vfq)

    def _check_break_reminder(self, vfq):
        # Break reminder is now handled by BreakReminderSystem background thread
        # which calls trigger_break_reminder() via callback.
        # Only handle mock-mode verification here.
        if self._break_cooldown > 0:
            self._break_cooldown -= 1

        if self._verifying:
            self._verify_countdown -= 1
            if self._verify_countdown <= 0:
                self._verifying = False
                if self._vfq_at_trigger - vfq >= 20:
                    self._reward_points += 10
                    self.screen_live.update_rewards(self._reward_points)
                    self._on_reward(10, self._reward_points,
                                    self._vfq_at_trigger - vfq)

    def trigger_break_reminder(self, vfq: float):
        """Called from BreakReminderSystem background thread — emit to main thread."""
        self.break_reminder_triggered.emit(vfq)

    def _on_break_reminder(self, vfq: float):
        """Called from background thread via signal — safe on main thread."""
        self._vfq_at_trigger = vfq
        self._break_pending  = False
        self._fire_break_reminder()

    def _fire_break_reminder(self):
        popup = RecoveryPopup(self._vfq_at_trigger, self)
        popup.raise_()
        popup.activateWindow()
        result = popup.exec()
        self._break_pending  = False
        self._break_cooldown = 600

        if result == QDialog.DialogCode.Accepted:
            action = popup.get_selected_action()
            # Tell reward system verification has started
            if self.session_manager is not None:
                self.session_manager.reward_system.on_break_triggered(
                    vfq_at_trigger=self._vfq_at_trigger,
                    action=action
                )
            else:
                # Mock mode — start internal verification
                self._verifying        = True
                self._verify_countdown = VERIFY_WINDOW_SECS
        else:
            if self.session_manager is not None:
                self.session_manager.reward_system.on_break_skipped()

    def update_from_pipeline(self, data: dict):
        """
        Called from background thread — must NOT touch widgets directly.
        Emits signal so main thread handles the UI update safely.
        """
        self.pipeline_data_received.emit(data)

    def _on_pipeline_data(self, data: dict):
        """Runs on main thread — safe to update widgets."""
        vfq   = data.get('vfq_score', 0)
        blink = data.get('blink_rate', 0)
        trend = data.get('strain_trend', 'STABLE')
        self._last_vfq = vfq

        self.screen_live.update_data({
            'vfq_score':    vfq,
            'blink_rate':   blink,
            'strain_trend': trend,
            'strain_label': data.get('strain_label', 'NORMAL'),
        })
        self.screen_live.chart.add_point(vfq)

    def update_tcn_prediction(self, label, probs):
        self.tcn_prediction_received.emit(label, list(probs))

    def _on_tcn_prediction(self, label: str, probs: list):
        """Runs on main thread."""
        self.screen_live.update_tcn_prediction(label, probs)

    def show_reward(self, points, total, drop):
        self.reward_received.emit(int(points), int(total), float(drop))

    def _on_reward(self, points: int, total: int, drop: float):
        self._reward_points = total
        self.screen_live.update_rewards(total)
        rw = RewardPopup(points, total, self)
        rw.exec()

    def show_verification_failed(self):
        self.verification_failed.emit()

    def _on_verification_failed(self):
        from PyQt6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle("Verification Failed")
        msg.setText(
            "Your VFQ did not drop enough during the break window.\n"
            "No reward this time — try a longer recovery action."
        )
        msg.setIcon(QMessageBox.Icon.Information)
        msg.exec()

    def run(self):
        self.show()


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("EyeStrain AI")
    app.setStyleSheet(f"""
        * {{
            font-family: -apple-system, 'Segoe UI',
                         'SF Pro Display', sans-serif;
        }}
        QToolTip {{
            background: {T['surface']}; color: {T['text']};
            border: 1px solid {T['border']};
            border-radius: 6px; padding: 4px 8px;
        }}
    """)
    window = Dashboard()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()