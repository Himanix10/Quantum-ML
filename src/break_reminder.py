"""
break_reminder.py
EyeStrain AI — Break Reminder System
Triggers popup when VFQ stays above threshold for sustained duration.
Supports Do Not Disturb mode — logs suppressed reminders silently.
"""

import time
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BreakReminderConfig:
    vfq_threshold: float = 40.0
    sustained_duration_sec: float = 300.0
    cooldown_sec: float = 600.0
    check_interval_sec: float = 5.0


class BreakReminderSystem:

    def __init__(self, config: BreakReminderConfig = None):
        self.config = config or BreakReminderConfig()
        self._buffer: deque = deque()
        self._last_reminder_time: float = 0.0
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.total_reminders_sent: int = 0
        self.last_trigger_vfq_avg: float = 0.0
        self._dashboard_callback = None

        # ── Do Not Disturb ──
        self._dnd_active: bool = False
        self._dnd_suppressed: list = []   # list of {timestamp, vfq_avg}

    def update(self, vfq_score: float) -> None:
        now = time.time()
        with self._lock:
            self._buffer.append((now, vfq_score))
            cutoff = now - (self.config.sustained_duration_sec + 60)
            while self._buffer and self._buffer[0][0] < cutoff:
                self._buffer.popleft()

    def _check_sustained_strain(self) -> bool:
        now = time.time()
        with self._lock:
            if not self._buffer:
                return False
            cutoff  = now - self.config.sustained_duration_sec
            recent  = [(ts, vfq) for ts, vfq in self._buffer if ts >= cutoff]
            min_entries = max(3, self.config.sustained_duration_sec / 2)
            if len(recent) < min_entries:
                return False
            avg_vfq = sum(v for _, v in recent) / len(recent)
            return avg_vfq > self.config.vfq_threshold

    def _get_window_avg_vfq(self) -> float:
        with self._lock:
            if not self._buffer:
                return 0.0
            now    = time.time()
            cutoff = now - self.config.sustained_duration_sec
            recent = [v for ts, v in self._buffer if ts >= cutoff]
            return sum(recent) / len(recent) if recent else 0.0

    def _can_send_reminder(self) -> bool:
        return time.time() - self._last_reminder_time >= self.config.cooldown_sec

    def _send_reminder(self, avg_vfq: float) -> None:
        self.total_reminders_sent += 1
        self.last_trigger_vfq_avg = avg_vfq
        self._last_reminder_time  = time.time()

        # ── DND check ──
        if self._dnd_active:
            entry = {
                'timestamp': time.strftime('%H:%M:%S'),
                'vfq_avg':   round(avg_vfq, 1),
            }
            self._dnd_suppressed.append(entry)
            print(f"[BreakReminder] DND active — suppressed reminder "
                  f"(VFQ avg={avg_vfq:.1f})")
            return

        print(f"\n[BREAK REMINDER] VFQ avg={avg_vfq:.1f} — firing")
        if self._dashboard_callback:
            try:
                self._dashboard_callback(avg_vfq)
            except Exception as e:
                print(f"[BreakReminder] Callback error: {e}")

    def set_dashboard_callback(self, callback):
        self._dashboard_callback = callback

    # ── DND public API ────────────────────────────────────────────────────────
    def enable_dnd(self):
        """Turn on Do Not Disturb — reminders suppressed and logged."""
        with self._lock:
            self._dnd_active     = True
            self._dnd_suppressed = []
        print("[BreakReminder] DND enabled")

    def disable_dnd(self) -> list:
        """
        Turn off Do Not Disturb.
        Returns list of suppressed reminders for dashboard summary.
        """
        with self._lock:
            self._dnd_active = False
            suppressed       = self._dnd_suppressed.copy()
            self._dnd_suppressed = []
        print(f"[BreakReminder] DND disabled — "
              f"{len(suppressed)} reminders were suppressed")
        return suppressed

    @property
    def dnd_active(self) -> bool:
        return self._dnd_active

    @property
    def dnd_suppressed_count(self) -> int:
        return len(self._dnd_suppressed)

    # ── Background thread ─────────────────────────────────────────────────────
    def _monitor_loop(self) -> None:
        while self._running:
            time.sleep(self.config.check_interval_sec)
            if not self._running:
                break
            sustained = self._check_sustained_strain()
            can_send  = self._can_send_reminder()
            avg_vfq   = self._get_window_avg_vfq()
            print(f"[BreakReminder] check — sustained={sustained} "
                  f"can_send={can_send} avg_vfq={avg_vfq:.1f} "
                  f"buffer_size={len(self._buffer)}"
                  f"{' [DND]' if self._dnd_active else ''}")
            if sustained and can_send:
                self._send_reminder(avg_vfq)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._monitor_loop, daemon=True)
        self._thread.start()
        print("[BreakReminder] Monitoring started — "
              f"threshold VFQ>{self.config.vfq_threshold} "
              f"for {self.config.sustained_duration_sec}s")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        print(f"[BreakReminder] Stopped. "
              f"Total reminders sent: {self.total_reminders_sent}")

    def get_status(self) -> dict:
        now = time.time()
        with self._lock:
            if not self._buffer:
                high_streak_sec = 0.0
                current_vfq     = 0.0
            else:
                current_vfq  = self._buffer[-1][1]
                streak_start = None
                for ts, vfq in reversed(self._buffer):
                    if vfq > self.config.vfq_threshold:
                        streak_start = ts
                    else:
                        break
                high_streak_sec = (now - streak_start) if streak_start else 0.0
        return {
            "current_vfq":          current_vfq,
            "high_streak_sec":      high_streak_sec,
            "high_streak_pct":      min(100.0, high_streak_sec /
                                        self.config.sustained_duration_sec * 100),
            "cooldown_remaining_sec": max(0.0, self.config.cooldown_sec -
                                          (now - self._last_reminder_time)),
            "total_reminders":      self.total_reminders_sent,
            "last_avg_vfq":         self.last_trigger_vfq_avg,
            "dnd_active":           self._dnd_active,
            "dnd_suppressed_count": len(self._dnd_suppressed),
        }