# src/break_reminder.py
"""
Break Reminder System — Day 13
Triggers a popup when VFQ stays above 40 for more than 5 continuous minutes.
"""

import time
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
import platform


@dataclass
class BreakReminderConfig:
    vfq_threshold: float = 40.0           # VFQ level that counts as "high"
    sustained_duration_sec: float = 300.0  # 5 minutes
    cooldown_sec: float = 600.0            # 10 min between reminders
    check_interval_sec: float = 5.0        # How often to evaluate


class BreakReminderSystem:
    """
    Monitors VFQ scores over time and triggers a break reminder
    when sustained high strain is detected.
    
    Usage:
        reminder = BreakReminderSystem()
        reminder.start()
        
        # In your main loop:
        reminder.update(vfq_score)
        
        reminder.stop()
    """

    def __init__(self, config: BreakReminderConfig = None):
        self.config = config or BreakReminderConfig()
        
        # Stores (timestamp, vfq_score) tuples
        self._buffer: deque = deque()
        
        self._last_reminder_time: float = 0.0
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # Stats for logging
        self.total_reminders_sent: int = 0
        self.last_trigger_vfq_avg: float = 0.0
        self._dashboard_callback = None

    def update(self, vfq_score: float) -> None:
        """Call this every second with the latest VFQ score."""
        now = time.time()
        with self._lock:
            self._buffer.append((now, vfq_score))
            # Prune entries older than sustained_duration + buffer margin
            cutoff = now - (self.config.sustained_duration_sec + 60)
            while self._buffer and self._buffer[0][0] < cutoff:
                self._buffer.popleft()

    def _check_sustained_strain(self) -> bool:
        """
        Returns True if the average VFQ over the last
        sustained_duration_sec has been above threshold.
        Uses average instead of requiring every single second
        to be above threshold — handles natural VFQ fluctuation.
        """
        now = time.time()
        with self._lock:
            if not self._buffer:
                return False

            # Get entries from the last sustained_duration_sec
            cutoff  = now - self.config.sustained_duration_sec
            recent  = [(ts, vfq) for ts, vfq in self._buffer
                       if ts >= cutoff]

            # Need at least half the window filled
            min_entries = max(3, self.config.sustained_duration_sec / 2)
            if len(recent) < min_entries:
                return False

            # Average must be above threshold
            avg_vfq = sum(v for _, v in recent) / len(recent)
            return avg_vfq > self.config.vfq_threshold

    def _get_window_avg_vfq(self) -> float:
        """Average VFQ over the sustained window."""
        with self._lock:
            if not self._buffer:
                return 0.0
            now = time.time()
            cutoff = now - self.config.sustained_duration_sec
            recent = [v for ts, v in self._buffer if ts >= cutoff]
            return sum(recent) / len(recent) if recent else 0.0

    def _can_send_reminder(self) -> bool:
        elapsed = time.time() - self._last_reminder_time
        return elapsed >= self.config.cooldown_sec

    def _send_reminder(self, avg_vfq: float) -> None:
        self.total_reminders_sent += 1
        self.last_trigger_vfq_avg = avg_vfq
        self._last_reminder_time = time.time()
        print(f"\n[BREAK REMINDER] VFQ avg={avg_vfq:.1f} — firing")

        # Call dashboard callback if wired
        if hasattr(self, '_dashboard_callback') and self._dashboard_callback:
            try:
                self._dashboard_callback(avg_vfq)
            except Exception as e:
                print(f"[BreakReminder] Dashboard callback error: {e}")

    def set_dashboard_callback(self, callback):
        """Wire dashboard popup to fire when reminder triggers."""
        self._dashboard_callback = callback

    def _monitor_loop(self) -> None:
        """Background thread: checks for sustained strain periodically."""
        while self._running:
            time.sleep(self.config.check_interval_sec)
            if not self._running:
                break

            sustained = self._check_sustained_strain()
            can_send  = self._can_send_reminder()
            avg_vfq   = self._get_window_avg_vfq()

            print(f"[BreakReminder] check — sustained={sustained} "
                  f"can_send={can_send} avg_vfq={avg_vfq:.1f} "
                  f"buffer_size={len(self._buffer)}")

            if sustained and can_send:
                self._send_reminder(avg_vfq)

    def start(self) -> None:
        """Start the background monitoring thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print("[BreakReminder] Monitoring started — threshold VFQ>40 for 5 min")

    def stop(self) -> None:
        """Stop the background thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        print(f"[BreakReminder] Stopped. Total reminders sent: {self.total_reminders_sent}")

    def get_status(self) -> dict:
        """Returns current state for dashboard display."""
        now = time.time()
        with self._lock:
            if not self._buffer:
                high_streak_sec = 0.0
                current_vfq = 0.0
            else:
                current_vfq = self._buffer[-1][1]
                # Measure current contiguous high streak
                streak_start = None
                for ts, vfq in reversed(self._buffer):
                    if vfq > self.config.vfq_threshold:
                        streak_start = ts
                    else:
                        break
                high_streak_sec = (now - streak_start) if streak_start else 0.0

        return {
            "current_vfq": current_vfq,
            "high_streak_sec": high_streak_sec,
            "high_streak_pct": min(100.0, high_streak_sec / self.config.sustained_duration_sec * 100),
            "cooldown_remaining_sec": max(0.0, self.config.cooldown_sec - (now - self._last_reminder_time)),
            "total_reminders": self.total_reminders_sent,
            "last_avg_vfq": self.last_trigger_vfq_avg,
        }