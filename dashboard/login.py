"""
dashboard/login.py
EyeStrain AI — Multi-User Login System

Flow:
  1. PIN screen     — 4-digit system-wide PIN
  2. Profile screen — Netflix-style user cards
  3. Auth screen    — password OR Google OAuth (Gmail) / OTP (Yahoo/Outlook)
  4. Register form  — new account creation with email verification

Auth methods:
  - Gmail accounts  → Google OAuth 2.0 (opens browser, no password typed)
  - Yahoo / Outlook / Hotmail → SMTP OTP (6-digit code sent to their email)
  - All accounts    → password login always available as fallback

Data layout per user:
  data/users/{username}/
    sessions/           ← CSVs written here
    profile.json        ← baseline, session history
    rewards.json        ← points, recovery history
    personalization.json
    avatar.png          ← optional uploaded photo
"""

import os
import sys
import json
import hashlib
import secrets
import smtplib
import threading
import time
import re
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFrame, QGridLayout, QFileDialog,
    QComboBox, QStackedWidget, QScrollArea, QSizePolicy,
    QMessageBox, QDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QObject
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPixmap, QPainterPath,
    QBrush, QPen, QPalette
)

# ── PATHS ─────────────────────────────────────────────────────────────────────
ROOT_DIR     = Path(__file__).parent.parent
APP_DIR      = ROOT_DIR / 'data' / 'app'
USERS_DIR    = ROOT_DIR / 'data' / 'users'
USERS_JSON   = APP_DIR / 'users.json'
PIN_JSON     = APP_DIR / 'system_pin.json'
EMAIL_CONFIG = APP_DIR / 'email_config.json'

APP_DIR.mkdir(parents=True, exist_ok=True)
USERS_DIR.mkdir(parents=True, exist_ok=True)

# ── THEME ─────────────────────────────────────────────────────────────────────
T = {
    'bg':      '#111111', 'surface': '#1A1A1A', 'surface2': '#222222',
    'border':  '#2A2A2A', 'text':    '#E8E8E8', 'text2':    '#888888',
    'text3':   '#4A4A4A', 'accent':  '#3B82F6', 'green':    '#10B981',
    'red':     '#EF4444', 'yellow':  '#F59E0B', 'orange':   '#F97316',
}

# ── HELPERS ───────────────────────────────────────────────────────────────────

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

def make_otp() -> str:
    return str(secrets.randbelow(900000) + 100000)  # 6-digit

def is_gmail(email: str) -> bool:
    return email.lower().endswith('@gmail.com')

def get_smtp_host(email: str) -> tuple:
    """Return (host, port) for the email provider."""
    domain = email.lower().split('@')[-1]
    hosts = {
        'yahoo.com':   ('smtp.mail.yahoo.com', 587),
        'yahoo.co.in': ('smtp.mail.yahoo.com', 587),
        'outlook.com': ('smtp-mail.outlook.com', 587),
        'hotmail.com': ('smtp-mail.outlook.com', 587),
        'live.com':    ('smtp-mail.outlook.com', 587),
    }
    return hosts.get(domain, ('smtp.gmail.com', 587))

def load_users() -> dict:
    if USERS_JSON.exists():
        try:
            with open(USERS_JSON) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_users(users: dict):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with open(USERS_JSON, 'w') as f:
        json.dump(users, f, indent=2)

def load_pin() -> str | None:
    if PIN_JSON.exists():
        try:
            with open(PIN_JSON) as f:
                return json.load(f).get('pin_hash')
        except Exception:
            pass
    return None

def save_pin(pin: str):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    with open(PIN_JSON, 'w') as f:
        json.dump({'pin_hash': sha256(pin)}, f)

def load_email_config() -> dict | None:
    if EMAIL_CONFIG.exists():
        try:
            with open(EMAIL_CONFIG) as f:
                return json.load(f)
        except Exception:
            pass
    return None

def user_data_dir(username: str) -> Path:
    return USERS_DIR / username

def user_sessions_dir(username: str) -> Path:
    p = USERS_DIR / username / 'sessions'
    p.mkdir(parents=True, exist_ok=True)
    return p

def user_profile_path(username: str) -> Path:
    return USERS_DIR / username / 'profile.json'

def user_rewards_path(username: str) -> Path:
    return USERS_DIR / username / 'rewards.json'

def user_avatar_path(username: str) -> Path:
    return USERS_DIR / username / 'avatar.png'

# ── EMAIL SENDER ──────────────────────────────────────────────────────────────

class EmailSender(QObject):
    """Sends emails in a background thread to avoid blocking the UI."""
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, to_email: str, subject: str, body: str):
        super().__init__()
        self.to_email = to_email
        self.subject  = subject
        self.body     = body

    def send(self):
        cfg = load_email_config()
        if not cfg:
            self.finished.emit(False,
                "Email not configured. Add data/app/email_config.json")
            return
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = self.subject
            msg['From']    = cfg['sender_email']
            msg['To']      = self.to_email
            msg.attach(MIMEText(self.body, 'html'))

            host, port = get_smtp_host(cfg['sender_email'])
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls()
                server.login(cfg['sender_email'], cfg['sender_password'])
                server.send_message(msg)
            self.finished.emit(True, "Email sent successfully")
        except Exception as e:
            self.finished.emit(False, str(e))

def send_email_async(to_email: str, subject: str, body: str,
                     callback=None):
    """Fire and forget email in background thread."""
    sender = EmailSender(to_email, subject, body)
    if callback:
        sender.finished.connect(callback)
    thread = QThread()
    sender.moveToThread(thread)
    thread.started.connect(sender.send)
    sender.finished.connect(thread.quit)
    thread.start()
    return thread, sender  # keep references alive

def welcome_email_body(full_name: str, username: str) -> str:
    return f"""
    <html><body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:20px;">
    <div style="max-width:480px;margin:0 auto;background:white;border-radius:12px;
                padding:32px;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
      <h2 style="color:#2563EB;margin-bottom:8px;">EyeStrain AI</h2>
      <h3 style="color:#111;margin-bottom:16px;">Welcome, {full_name}!</h3>
      <p style="color:#444;line-height:1.6;">
        Your account has been created successfully.<br>
        Username: <strong>{username}</strong>
      </p>
      <p style="color:#444;line-height:1.6;">
        EyeStrain AI will monitor your eye health in real time and alert you
        before strain becomes a problem. Start a session from the dashboard
        to begin your first baseline calibration.
      </p>
      <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
      <p style="color:#888;font-size:12px;">
        This email was sent automatically. Do not reply.
      </p>
    </div></body></html>
    """

def otp_email_body(full_name: str, otp: str) -> str:
    return f"""
    <html><body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:20px;">
    <div style="max-width:480px;margin:0 auto;background:white;border-radius:12px;
                padding:32px;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
      <h2 style="color:#2563EB;margin-bottom:8px;">EyeStrain AI</h2>
      <h3 style="color:#111;margin-bottom:16px;">Email Verification</h3>
      <p style="color:#444;">Hi {full_name}, your verification code is:</p>
      <div style="font-size:36px;font-weight:bold;color:#2563EB;letter-spacing:8px;
                  text-align:center;margin:24px 0;">{otp}</div>
      <p style="color:#888;font-size:13px;">
        This code expires in 10 minutes. Do not share it with anyone.
      </p>
    </div></body></html>
    """

# ── GOOGLE OAUTH ──────────────────────────────────────────────────────────────

def google_oauth_login(callback):
    """
    Opens browser for Google OAuth 2.0.
    callback(email: str | None) — called with the verified email or None.

    Requires: data/app/google_client_secret.json
    Get this from Google Cloud Console → OAuth 2.0 credentials → Desktop App.
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        client_secret = APP_DIR / 'google_client_secret.json'
        if not client_secret.exists():
            callback(None, "google_client_secret.json not found in data/app/")
            return
        SCOPES = ['openid',
                  'https://www.googleapis.com/auth/userinfo.email',
                  'https://www.googleapis.com/auth/userinfo.profile']
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secret), SCOPES)

        def run():
            try:
                creds = flow.run_local_server(port=0, open_browser=True)
                import urllib.request, json as _json
                req = urllib.request.Request(
                    'https://www.googleapis.com/oauth2/v2/userinfo',
                    headers={'Authorization': f'Bearer {creds.token}'}
                )
                with urllib.request.urlopen(req) as resp:
                    info  = _json.loads(resp.read())
                    email = info.get('email', '')
                callback(email, None)
            except Exception as e:
                callback(None, str(e))

        threading.Thread(target=run, daemon=True).start()
    except ImportError:
        callback(None,
            "google-auth-oauthlib not installed.\n"
            "Run: pip install google-auth-oauthlib")

# ── AVATAR WIDGET ─────────────────────────────────────────────────────────────

class AvatarWidget(QWidget):
    """Circular avatar — shows image if available, otherwise initials."""

    def __init__(self, username: str, size: int = 80, parent=None):
        super().__init__(parent)
        self.username = username
        self.size     = size
        self.setFixedSize(size, size)
        self._pixmap  = None

        avatar_path = user_avatar_path(username)
        if avatar_path.exists():
            px = QPixmap(str(avatar_path))
            if not px.isNull():
                self._pixmap = px.scaled(
                    size, size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addEllipse(0, 0, self.size, self.size)
        p.setClipPath(path)

        if self._pixmap:
            p.drawPixmap(0, 0, self._pixmap)
        else:
            # Colour based on username hash
            colours = ['#3B82F6','#10B981','#F59E0B','#EF4444',
                       '#8B5CF6','#EC4899','#06B6D4','#F97316']
            idx  = sum(ord(c) for c in self.username) % len(colours)
            p.fillPath(path, QBrush(QColor(colours[idx])))

            initials = self.username[:2].upper()
            p.setPen(QColor('#FFFFFF'))
            f = QFont('Arial', self.size // 3, QFont.Weight.Bold)
            p.setFont(f)
            p.drawText(0, 0, self.size, self.size,
                       Qt.AlignmentFlag.AlignCenter, initials)
        p.end()

# ── PIN SCREEN ────────────────────────────────────────────────────────────────

class PINScreen(QWidget):
    """
    System-wide 4-digit PIN.
    First launch: asks to set a PIN.
    Subsequent launches: asks to enter the PIN.
    """
    pin_accepted = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_setup = load_pin() is None
        self._digits   = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(24)

        logo = QLabel("EyeStrain AI")
        logo.setStyleSheet(
            f"color:{T['accent']}; font-size:28px; font-weight:700;")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        self._title = QLabel(
            "Create a 4-digit PIN for this device"
            if self._is_setup else "Enter PIN to continue")
        self._title.setStyleSheet(
            f"color:{T['text']}; font-size:16px; font-weight:600;")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title)

        # Dot indicators
        dot_row = QHBoxLayout()
        dot_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dot_row.setSpacing(16)
        self._dots = []
        for _ in range(4):
            dot = QLabel("○")
            dot.setStyleSheet(f"color:{T['text3']}; font-size:28px;")
            self._dots.append(dot)
            dot_row.addWidget(dot)
        layout.addLayout(dot_row)

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet(f"color:{T['red']}; font-size:13px;")
        self._error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._error_lbl)

        # Numpad
        numpad = QGridLayout()
        numpad.setSpacing(12)
        buttons = [
            ('1', 0, 0), ('2', 0, 1), ('3', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('7', 2, 0), ('8', 2, 1), ('9', 2, 2),
            ('',  3, 0), ('0', 3, 1), ('⌫', 3, 2),
        ]
        for label, row, col in buttons:
            if not label:
                continue
            btn = QPushButton(label)
            btn.setFixedSize(72, 72)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if label == '⌫':
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background:{T['surface2']}; color:{T['text2']};
                        border:1px solid {T['border']}; border-radius:36px;
                        font-size:20px;
                    }}
                    QPushButton:hover {{ background:{T['border']}; }}
                """)
                btn.clicked.connect(self._backspace)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background:{T['surface']}; color:{T['text']};
                        border:1px solid {T['border']}; border-radius:36px;
                        font-size:22px; font-weight:600;
                    }}
                    QPushButton:hover {{
                        background:{T['accent']}; color:white;
                        border-color:{T['accent']};
                    }}
                """)
                btn.clicked.connect(lambda _, d=label: self._digit(d))
            numpad.addWidget(btn, row, col)

        numpad_widget = QWidget()
        numpad_widget.setLayout(numpad)
        layout.addWidget(numpad_widget, alignment=Qt.AlignmentFlag.AlignCenter)

    def _digit(self, d: str):
        if len(self._digits) >= 4:
            return
        self._digits.append(d)
        self._update_dots()
        if len(self._digits) == 4:
            QTimer.singleShot(100, self._submit)

    def _backspace(self):
        if self._digits:
            self._digits.pop()
            self._update_dots()
            self._error_lbl.setText("")

    def _update_dots(self):
        for i, dot in enumerate(self._dots):
            if i < len(self._digits):
                dot.setText("●")
                dot.setStyleSheet(f"color:{T['accent']}; font-size:28px;")
            else:
                dot.setText("○")
                dot.setStyleSheet(f"color:{T['text3']}; font-size:28px;")

    def _submit(self):
        pin = ''.join(self._digits)
        if self._is_setup:
            save_pin(pin)
            self._is_setup = False
            self._title.setText("PIN set. Enter it again to confirm.")
            self._digits = []
            self._update_dots()
            self._first_pin = pin
            # On second entry — verify match
            self._is_setup      = False
            self._confirming    = True
            self._first_pin_val = pin
        elif hasattr(self, '_confirming') and self._confirming:
            if pin == self._first_pin_val:
                save_pin(pin)
                self.pin_accepted.emit()
            else:
                self._error_lbl.setText("PINs did not match. Try again.")
                self._digits = []
                self._update_dots()
        else:
            stored = load_pin()
            if stored and sha256(pin) == stored:
                self.pin_accepted.emit()
            else:
                self._error_lbl.setText("Wrong PIN. Try again.")
                self._digits = []
                self._update_dots()

# ── PROFILE CARD ──────────────────────────────────────────────────────────────

class ProfileCard(QFrame):
    clicked = pyqtSignal(str)  # username

    def __init__(self, username: str, full_name: str, parent=None):
        super().__init__(parent)
        self.username  = username
        self.full_name = full_name
        self.setFixedSize(150, 180)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{
                background: {T['surface']};
                border: 1px solid {T['border']};
                border-radius: 16px;
            }}
            QFrame:hover {{
                border: 2px solid {T['accent']};
                background: {T['surface2']};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        self.avatar = AvatarWidget(username, size=80)
        layout.addWidget(self.avatar, alignment=Qt.AlignmentFlag.AlignCenter)

        name_lbl = QLabel(full_name)
        name_lbl.setStyleSheet(
            f"color:{T['text']}; font-size:13px; font-weight:600;")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setWordWrap(True)
        layout.addWidget(name_lbl)

        user_lbl = QLabel(f"@{username}")
        user_lbl.setStyleSheet(f"color:{T['text3']}; font-size:11px;")
        user_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(user_lbl)

    def mousePressEvent(self, event):
        self.clicked.emit(self.username)

# ── PROFILE SELECTION SCREEN ──────────────────────────────────────────────────

class ProfileScreen(QWidget):
    profile_selected = pyqtSignal(str)   # username
    add_profile      = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(32)

        title = QLabel("Select Profile")
        title.setStyleSheet(
            f"color:{T['text']}; font-size:22px; font-weight:700;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._cards_widget = QWidget()
        self._cards_layout = QHBoxLayout(self._cards_widget)
        self._cards_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cards_layout.setSpacing(20)
        layout.addWidget(self._cards_widget)

        self.refresh()

    def refresh(self):
        # Clear existing cards
        for i in reversed(range(self._cards_layout.count())):
            w = self._cards_layout.itemAt(i).widget()
            if w:
                w.deleteLater()

        users = load_users()
        for username, info in users.items():
            card = ProfileCard(username, info.get('full_name', username))
            card.clicked.connect(self.profile_selected.emit)
            self._cards_layout.addWidget(card)

        # Add profile card
        add_card = QFrame()
        add_card.setFixedSize(150, 180)
        add_card.setCursor(Qt.CursorShape.PointingHandCursor)
        add_card.setStyleSheet(f"""
            QFrame {{
                background: transparent;
                border: 2px dashed {T['border']};
                border-radius: 16px;
            }}
            QFrame:hover {{
                border-color: {T['accent']};
            }}
        """)
        al = QVBoxLayout(add_card)
        al.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus = QLabel("+")
        plus.setStyleSheet(
            f"color:{T['text3']}; font-size:40px; font-weight:300;")
        plus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        txt = QLabel("Add Profile")
        txt.setStyleSheet(f"color:{T['text3']}; font-size:13px;")
        txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        al.addWidget(plus); al.addWidget(txt)
        add_card.mousePressEvent = lambda _: self.add_profile.emit()
        self._cards_layout.addWidget(add_card)

# ── PASSWORD / AUTH SCREEN ────────────────────────────────────────────────────

class AuthScreen(QWidget):
    """
    Shown after user selects a profile.
    Offers password login OR email-based login.
    Email login:
      - Gmail → Google OAuth (browser popup)
      - Others → OTP sent via SMTP
    """
    login_success = pyqtSignal(str)   # username
    go_back       = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._username      = ""
        self._otp_code      = ""
        self._otp_expires   = None
        self._email_threads = []
        self._build_ui()

    def set_user(self, username: str):
        self._username = username
        users = load_users()
        info  = users.get(username, {})

        self._avatar.username = username
        self._avatar.update()
        self._name_lbl.setText(info.get('full_name', username))
        self._user_lbl.setText(f"@{username}")

        # Detect email type for login button label
        email = info.get('email', '')
        if is_gmail(email):
            self._email_btn.setText("Sign in with Google")
        elif email:
            self._email_btn.setText(f"Send OTP to {email[:20]}...")
        else:
            self._email_btn.hide()

        self._pw_input.clear()
        self._error_lbl.setText("")
        self._otp_frame.hide()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        back_btn = QPushButton("← Back")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color:{T['text3']};
                border: none; font-size: 13px;
            }}
            QPushButton:hover {{ color:{T['text']}; }}
        """)
        back_btn.clicked.connect(self.go_back)
        back_row = QHBoxLayout()
        back_row.addWidget(back_btn); back_row.addStretch()
        layout.addLayout(back_row)

        self._avatar = AvatarWidget("?", size=90)
        layout.addWidget(self._avatar, alignment=Qt.AlignmentFlag.AlignCenter)

        self._name_lbl = QLabel("")
        self._name_lbl.setStyleSheet(
            f"color:{T['text']}; font-size:18px; font-weight:700;")
        self._name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._name_lbl)

        self._user_lbl = QLabel("")
        self._user_lbl.setStyleSheet(f"color:{T['text3']}; font-size:13px;")
        self._user_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._user_lbl)

        # Password input
        self._pw_input = QLineEdit()
        self._pw_input.setPlaceholderText("Enter password")
        self._pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_input.setFixedWidth(300)
        self._pw_input.setFixedHeight(44)
        self._pw_input.setStyleSheet(f"""
            QLineEdit {{
                background:{T['surface2']}; color:{T['text']};
                border:1px solid {T['border']}; border-radius:10px;
                padding:0 16px; font-size:14px;
            }}
            QLineEdit:focus {{ border-color:{T['accent']}; }}
        """)
        self._pw_input.returnPressed.connect(self._submit_password)
        layout.addWidget(self._pw_input, alignment=Qt.AlignmentFlag.AlignCenter)

        # Login button
        login_btn = QPushButton("Sign In")
        login_btn.setFixedWidth(300)
        login_btn.setFixedHeight(44)
        login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        login_btn.setStyleSheet(f"""
            QPushButton {{
                background:{T['accent']}; color:white;
                border:none; border-radius:10px;
                font-size:14px; font-weight:600;
            }}
            QPushButton:hover {{ background:#1D4ED8; }}
        """)
        login_btn.clicked.connect(self._submit_password)
        layout.addWidget(login_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Small spacer before email OTP option

        # Email login button
        self._email_btn = QPushButton("Login with Email OTP")
        self._email_btn.setFixedWidth(300)
        self._email_btn.setFixedHeight(44)
        self._email_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._email_btn.setStyleSheet(f"""
            QPushButton {{
                background:{T['surface2']}; color:{T['text']};
                border:1px solid {T['border']}; border-radius:10px;
                font-size:13px; font-weight:600;
            }}
            QPushButton:hover {{ background:{T['border']}; }}
        """)
        self._email_btn.clicked.connect(self._email_login)
        layout.addWidget(self._email_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # OTP entry frame (hidden until OTP sent)
        self._otp_frame = QFrame()
        self._otp_frame.hide()
        otp_layout = QVBoxLayout(self._otp_frame)
        otp_layout.setSpacing(10)
        otp_lbl = QLabel("Enter the 6-digit code sent to your email:")
        otp_lbl.setStyleSheet(f"color:{T['text2']}; font-size:12px;")
        otp_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        otp_layout.addWidget(otp_lbl)
        self._otp_input = QLineEdit()
        self._otp_input.setPlaceholderText("000000")
        self._otp_input.setMaxLength(6)
        self._otp_input.setFixedWidth(200)
        self._otp_input.setFixedHeight(44)
        self._otp_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._otp_input.setStyleSheet(f"""
            QLineEdit {{
                background:{T['surface2']}; color:{T['text']};
                border:1px solid {T['border']}; border-radius:10px;
                padding:0 16px; font-size:20px; font-weight:700;
                letter-spacing:8px;
            }}
            QLineEdit:focus {{ border-color:{T['accent']}; }}
        """)
        otp_layout.addWidget(self._otp_input,
                              alignment=Qt.AlignmentFlag.AlignCenter)
        otp_submit = QPushButton("Verify Code")
        otp_submit.setFixedWidth(200)
        otp_submit.setFixedHeight(40)
        otp_submit.setCursor(Qt.CursorShape.PointingHandCursor)
        otp_submit.setStyleSheet(f"""
            QPushButton {{
                background:{T['green']}; color:white; border:none;
                border-radius:10px; font-size:13px; font-weight:600;
            }}
            QPushButton:hover {{ background:#047857; }}
        """)
        otp_submit.clicked.connect(self._verify_otp)
        otp_layout.addWidget(otp_submit,
                              alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._otp_frame,
                         alignment=Qt.AlignmentFlag.AlignCenter)

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet(f"color:{T['red']}; font-size:13px;")
        self._error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_lbl.setWordWrap(True)
        self._error_lbl.setFixedWidth(300)
        layout.addWidget(self._error_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

    def _submit_password(self):
        pw = self._pw_input.text().strip()
        if not pw:
            self._error_lbl.setText("Please enter your password.")
            return
        users = load_users()
        info  = users.get(self._username, {})
        if sha256(pw) == info.get('password_hash', ''):
            self._update_last_login()
            self.login_success.emit(self._username)
        else:
            self._error_lbl.setText("Incorrect password. Try again.")
            self._pw_input.clear()

    def _email_login(self):
        users = load_users()
        email = users.get(self._username, {}).get('email', '')
        if not email:
            self._error_lbl.setText("No email registered for this account.")
            return

        if is_gmail(email):
            self._error_lbl.setText("Opening browser for Google sign-in...")
            google_oauth_login(self._on_google_auth)
        else:
            # Send OTP
            self._otp_code    = make_otp()
            self._otp_expires = datetime.now() + timedelta(minutes=10)
            full_name = users.get(self._username, {}).get('full_name', '')
            self._error_lbl.setText("Sending OTP to your email...")
            t, s = send_email_async(
                email,
                "EyeStrain AI — Login Verification Code",
                otp_email_body(full_name, self._otp_code),
                self._on_otp_sent
            )
            self._email_threads.append((t, s))

    def _on_otp_sent(self, success: bool, message: str):
        if success:
            self._otp_frame.show()
            self._error_lbl.setText("")
        else:
            self._error_lbl.setText(f"Could not send email: {message}")

    def _verify_otp(self):
        entered = self._otp_input.text().strip()
        if not self._otp_code:
            self._error_lbl.setText("Request an OTP first.")
            return
        if datetime.now() > self._otp_expires:
            self._error_lbl.setText("OTP expired. Request a new one.")
            return
        if entered == self._otp_code:
            self._update_last_login()
            self.login_success.emit(self._username)
        else:
            self._error_lbl.setText("Incorrect code. Try again.")

    def _on_google_auth(self, email: str | None, error: str | None):
        if error:
            self._error_lbl.setText(f"Google sign-in failed: {error}")
            return
        users = load_users()
        registered_email = users.get(self._username, {}).get('email', '')
        if email and email.lower() == registered_email.lower():
            self._update_last_login()
            self.login_success.emit(self._username)
        else:
            self._error_lbl.setText(
                f"Google account ({email}) does not match "
                f"registered email for this profile.")

    def _update_last_login(self):
        users = load_users()
        if self._username in users:
            users[self._username]['last_login'] = \
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_users(users)

# ── REGISTRATION FORM ─────────────────────────────────────────────────────────

class RegistrationForm(QWidget):
    """
    New account creation form.
    Fields: full name, username, password, occupation, email, optional avatar.
    Sends welcome email on success.
    """
    registration_done = pyqtSignal(str)  # username of newly created user
    go_back           = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._avatar_path  = None
        self._email_threads = []
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border:none; background: transparent; }")

        content = QWidget()
        layout  = QVBoxLayout(content)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)
        layout.setContentsMargins(40, 30, 40, 30)

        back_btn = QPushButton("← Back")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(f"""
            QPushButton {{
                background:transparent; color:{T['text3']};
                border:none; font-size:13px;
            }}
            QPushButton:hover {{ color:{T['text']}; }}
        """)
        back_btn.clicked.connect(self.go_back)
        back_row = QHBoxLayout()
        back_row.addWidget(back_btn); back_row.addStretch()
        layout.addLayout(back_row)

        title = QLabel("Create Account")
        title.setStyleSheet(
            f"color:{T['text']}; font-size:22px; font-weight:700;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("Set up your personal eye health profile")
        sub.setStyleSheet(f"color:{T['text3']}; font-size:13px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        # Avatar upload
        av_row = QHBoxLayout()
        av_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._av_preview = QLabel("")
        self._av_preview.setFixedSize(80, 80)
        self._av_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._av_preview.setStyleSheet(f"""
            QLabel {{
                background:{T['surface2']}; border:1px solid {T['border']};
                border-radius:40px; font-size:36px;
            }}
        """)
        av_btn = QPushButton("Upload Photo (optional)")
        av_btn.setFixedHeight(32)
        av_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        av_btn.setStyleSheet(f"""
            QPushButton {{
                background:transparent; color:{T['text3']};
                border:1px solid {T['border']}; border-radius:8px;
                font-size:12px; padding:0 12px;
            }}
            QPushButton:hover {{ color:{T['text']}; border-color:{T['accent']}; }}
        """)
        av_btn.clicked.connect(self._pick_avatar)
        av_row.addWidget(self._av_preview)
        av_row.addSpacing(16)
        av_row.addWidget(av_btn)
        layout.addLayout(av_row)

        # Form fields
        fields = [
            ("Full Name *",    "_f_fullname",  "e.g. Alice Smith",       False),
            ("Username *",     "_f_username",  "letters, numbers, _",    False),
            ("Password *",     "_f_password",  "min 8 characters",       True),
            ("Confirm Password *","_f_confirm","re-enter password",       True),
            ("Email Address *","_f_email",     "Gmail / Yahoo / Outlook", False),
        ]
        for label, attr, placeholder, is_pw in fields:
            lbl = QLabel(label)
            lbl.setStyleSheet(
                f"color:{T['text2']}; font-size:12px; font-weight:600;")
            layout.addWidget(lbl)
            inp = QLineEdit()
            inp.setPlaceholderText(placeholder)
            inp.setFixedHeight(42)
            inp.setFixedWidth(360)
            if is_pw:
                inp.setEchoMode(QLineEdit.EchoMode.Password)
            inp.setStyleSheet(f"""
                QLineEdit {{
                    background:{T['surface2']}; color:{T['text']};
                    border:1px solid {T['border']}; border-radius:10px;
                    padding:0 14px; font-size:13px;
                }}
                QLineEdit:focus {{ border-color:{T['accent']}; }}
            """)
            setattr(self, attr, inp)
            layout.addWidget(inp, alignment=Qt.AlignmentFlag.AlignCenter)

        # Occupation
        occ_lbl = QLabel("Occupation *")
        occ_lbl.setStyleSheet(
            f"color:{T['text2']}; font-size:12px; font-weight:600;")
        layout.addWidget(occ_lbl)

        occ_row = QHBoxLayout()
        self._occ_combo = QComboBox()
        self._occ_combo.addItems([
            "Student", "IT Professional", "Lecturer", "Other"])
        self._occ_combo.setFixedHeight(42)
        self._occ_combo.setFixedWidth(200)
        self._occ_combo.setStyleSheet(f"""
            QComboBox {{
                background:{T['surface2']}; color:{T['text']};
                border:1px solid {T['border']}; border-radius:10px;
                padding:0 14px; font-size:13px;
            }}
            QComboBox::drop-down {{ border:none; }}
            QComboBox QAbstractItemView {{
                background:{T['surface']}; color:{T['text']};
                selection-background-color:{T['accent']};
                border:1px solid {T['border']};
            }}
        """)
        self._occ_combo.currentTextChanged.connect(self._occ_changed)

        self._occ_other = QLineEdit()
        self._occ_other.setPlaceholderText("Specify occupation")
        self._occ_other.setFixedHeight(42)
        self._occ_other.setFixedWidth(152)
        self._occ_other.hide()
        self._occ_other.setStyleSheet(f"""
            QLineEdit {{
                background:{T['surface2']}; color:{T['text']};
                border:1px solid {T['border']}; border-radius:10px;
                padding:0 14px; font-size:13px;
            }}
            QLineEdit:focus {{ border-color:{T['accent']}; }}
        """)
        occ_row.addWidget(self._occ_combo)
        occ_row.addSpacing(8)
        occ_row.addWidget(self._occ_other)
        occ_widget = QWidget(); occ_widget.setFixedWidth(360)
        occ_widget.setLayout(occ_row)
        layout.addWidget(occ_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet(f"color:{T['red']}; font-size:12px;")
        self._error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_lbl.setWordWrap(True)
        self._error_lbl.setFixedWidth(360)
        layout.addWidget(self._error_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            f"color:{T['green']}; font-size:12px;")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_lbl)

        submit_btn = QPushButton("Create Account")
        submit_btn.setFixedWidth(360)
        submit_btn.setFixedHeight(46)
        submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        submit_btn.setStyleSheet(f"""
            QPushButton {{
                background:{T['accent']}; color:white; border:none;
                border-radius:12px; font-size:14px; font-weight:700;
            }}
            QPushButton:hover {{ background:#1D4ED8; }}
        """)
        submit_btn.clicked.connect(self._submit)
        layout.addWidget(submit_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _occ_changed(self, text):
        self._occ_other.setVisible(text == "Other")

    def _pick_avatar(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Profile Photo", "",
            "Images (*.png *.jpg *.jpeg *.webp)")
        if path:
            self._avatar_path = path
            px = QPixmap(path).scaled(
                80, 80,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            self._av_preview.setPixmap(px)
            self._av_preview.setText("")

    def _submit(self):
        full_name = self._f_fullname.text().strip()
        username  = self._f_username.text().strip().lower()
        password  = self._f_password.text()
        confirm   = self._f_confirm.text()
        email     = self._f_email.text().strip().lower()
        occ       = self._occ_combo.currentText()
        if occ == "Other":
            occ = self._occ_other.text().strip() or "Other"

        # Validation
        if not all([full_name, username, password, confirm, email]):
            self._error_lbl.setText("All fields marked * are required.")
            return
        if not re.match(r'^[a-z0-9_]{3,20}$', username):
            self._error_lbl.setText(
                "Username: 3-20 chars, letters/numbers/underscore only.")
            return
        if username in load_users():
            self._error_lbl.setText("Username already taken.")
            return
        if len(password) < 8:
            self._error_lbl.setText("Password must be at least 8 characters.")
            return
        if password != confirm:
            self._error_lbl.setText("Passwords do not match.")
            return
        if '@' not in email or '.' not in email.split('@')[-1]:
            self._error_lbl.setText("Please enter a valid email address.")
            return

        self._error_lbl.setText("")

        # Create user record
        users = load_users()
        users[username] = {
            "username":      username,
            "full_name":     full_name,
            "password_hash": sha256(password),
            "email":         email,
            "occupation":    occ,
            "avatar_path":   "",
            "created_at":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_login":    None,
        }

        # Copy avatar if uploaded
        user_data_dir(username).mkdir(parents=True, exist_ok=True)
        if self._avatar_path:
            import shutil
            dest = user_avatar_path(username)
            shutil.copy2(self._avatar_path, dest)
            users[username]['avatar_path'] = str(dest)

        # Create sessions folder
        user_sessions_dir(username)

        save_users(users)

        # Send welcome email
        self._status_lbl.setText("Sending welcome email...")
        t, s = send_email_async(
            email,
            "Welcome to EyeStrain AI",
            welcome_email_body(full_name, username),
            self._on_email_sent
        )
        self._email_threads.append((t, s))

        # Proceed immediately — don't block on email
        self.registration_done.emit(username)

    def _on_email_sent(self, success: bool, message: str):
        if not success:
            print(f"[Registration] Welcome email failed: {message}")

# ── MAIN LOGIN WINDOW ─────────────────────────────────────────────────────────

class LoginWindow(QWidget):
    """
    Top-level login window. Contains:
      PIN screen → Profile screen → Auth screen
      With registration form accessible from profile screen.
    Emits login_complete(username) when user is authenticated.
    """
    login_complete = pyqtSignal(str)   # authenticated username

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EyeStrain AI")
        self.setMinimumSize(900, 640)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setStyleSheet(
            f"QWidget {{ background:{T['bg']}; font-family: 'Segoe UI', Arial; }}")
        self._drag_pos = None
        self._build_ui()

    def showEvent(self, e):
        super().showEvent(e)
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.center().x() - self.width()//2,
                  screen.center().y() - self.height()//2)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            self.move(e.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Custom titlebar
        tb = QWidget(); tb.setFixedHeight(40)
        tb.setStyleSheet(f"background:{T['surface']}; border-bottom:1px solid {T['border']};")
        tbl = QHBoxLayout(tb); tbl.setContentsMargins(16, 0, 8, 0); tbl.setSpacing(6)
        app_lbl = QLabel("EyeStrain AI")
        app_lbl.setStyleSheet(f"color:{T['text2']}; font-size:11px; font-weight:600;")
        tbl.addWidget(app_lbl); tbl.addStretch()
        for sym, tip, slot in [("–","Minimize",self.showMinimized),("×","Close",self.close)]:
            b = QPushButton(sym); b.setFixedSize(28,28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            is_x = sym == "×"
            b.setStyleSheet(
                f"QPushButton{{background:transparent;color:{T['text2']};border:none;"
                f"font-size:{'14' if is_x else '12'}px;border-radius:4px;}}"
                f"QPushButton:hover{{background:{'#C42B1C' if is_x else T['surface2']};"
                f"color:{'white' if is_x else T['text']};}}")
            b.clicked.connect(slot); tbl.addWidget(b)
        main_layout.addWidget(tb)

        self._stack = QStackedWidget(self)
        main_layout.addWidget(self._stack)

        # Screens
        self._pin_screen   = PINScreen()
        self._prof_screen  = ProfileScreen()
        self._auth_screen  = AuthScreen()
        self._reg_form     = RegistrationForm()

        self._stack.addWidget(self._pin_screen)   # 0
        self._stack.addWidget(self._prof_screen)  # 1
        self._stack.addWidget(self._auth_screen)  # 2
        self._stack.addWidget(self._reg_form)     # 3

        # Connections
        self._pin_screen.pin_accepted.connect(
            lambda: self._stack.setCurrentIndex(1))

        self._prof_screen.profile_selected.connect(self._on_profile_selected)
        self._prof_screen.add_profile.connect(
            lambda: self._stack.setCurrentIndex(3))

        self._auth_screen.login_success.connect(self._on_login_success)
        self._auth_screen.go_back.connect(
            lambda: self._stack.setCurrentIndex(1))

        self._reg_form.registration_done.connect(self._on_registration_done)
        self._reg_form.go_back.connect(
            lambda: self._stack.setCurrentIndex(1))

    def _on_profile_selected(self, username: str):
        self._auth_screen.set_user(username)
        self._stack.setCurrentIndex(2)

    def _on_login_success(self, username: str):
        self.login_complete.emit(username)

    def _on_registration_done(self, username: str):
        self._prof_screen.refresh()
        self._stack.setCurrentIndex(1)

# ── STANDALONE TEST ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("EyeStrain AI")
    w   = LoginWindow()
    w.login_complete.connect(lambda u: print(f"Logged in as: {u}"))
    w.show()
    sys.exit(app.exec())