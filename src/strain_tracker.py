# src/strain_tracker.py
"""
Strain Trend Tracker — Day 14
Tracks VFQ history and computes trend: IMPROVING / STABLE / WORSENING
"""

from collections import deque
import time


class StrainTracker:
    """
    Maintains a rolling buffer of VFQ scores and computes:
    - Current trend (IMPROVING / STABLE / WORSENING)
    - Rolling averages over short and long windows
    - Strain percentage (how much of session was high strain)

    Usage:
        tracker = StrainTracker()
        tracker.update(vfq_score)
        trend = tracker.get_trend()
    """

    def __init__(self, short_window=60, long_window=300):
        # short_window: 60 seconds, long_window: 5 minutes
        self.short_window = short_window
        self.long_window  = long_window

        # Stores (timestamp, vfq) tuples
        self._buffer: deque = deque()

        # Full session history for end-of-session stats
        self._session_history = []

    def update(self, vfq_score: float) -> None:
        """Call every second with latest VFQ score."""
        now = time.time()
        self._buffer.append((now, vfq_score))
        self._session_history.append(vfq_score)

        # Prune old entries beyond long_window
        cutoff = now - self.long_window
        while self._buffer and self._buffer[0][0] < cutoff:
            self._buffer.popleft()

    def _window_avg(self, seconds: int) -> float:
        """Average VFQ over the last N seconds."""
        now = time.time()
        cutoff = now - seconds
        window = [v for ts, v in self._buffer if ts >= cutoff]
        return round(sum(window) / len(window), 2) if window else 0.0

    def get_trend(self) -> str:
        """
        Compares short window avg vs long window avg.
        WORSENING  — recent avg is 5+ points higher than long avg
        IMPROVING  — recent avg is 5+ points lower than long avg
        STABLE     — within 5 points either way
        """
        short_avg = self._window_avg(self.short_window)
        long_avg  = self._window_avg(self.long_window)

        diff = short_avg - long_avg

        if diff >= 5:
            return "WORSENING"
        elif diff <= -5:
            return "IMPROVING"
        else:
            return "STABLE"

    def get_status(self) -> dict:
        """Full status — expose this to dashboard via session_manager."""
        return {
            "short_avg_vfq":    self._window_avg(self.short_window),
            "long_avg_vfq":     self._window_avg(self.long_window),
            "trend":            self.get_trend(),
            "high_strain_pct":  self._high_strain_pct(),
            "buffer_size":      len(self._buffer),
        }

    def _high_strain_pct(self) -> float:
        """Percentage of session spent above VFQ 40."""
        if not self._session_history:
            return 0.0
        high = sum(1 for v in self._session_history if v > 40)
        return round((high / len(self._session_history)) * 100, 1)

    def get_session_summary(self) -> dict:
        """Call at end of session for full summary."""
        if not self._session_history:
            return {}
        return {
            "avg_vfq":         round(sum(self._session_history) / len(self._session_history), 1),
            "max_vfq":         round(max(self._session_history), 1),
            "min_vfq":         round(min(self._session_history), 1),
            "high_strain_pct": self._high_strain_pct(),
            "total_samples":   len(self._session_history),
        }