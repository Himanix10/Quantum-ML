"""
strain_predictor.py
EyeStrain AI — Predictive Strain Warning System

Uses linear regression on recent VFQ history to forecast when strain
will cross the break threshold. Fires a warning 5 minutes early (yellow)
and 2 minutes early (orange) so user can take a voluntary break.

Integrated into session_manager.py — called every 30 seconds.
Sends warning level to dashboard sidebar via signal.

Warning levels:
  None    — no warning, strain not projected to cross threshold
  'yellow' — strain projected to cross threshold in ~5 minutes
  'orange' — strain projected to cross threshold in ~2 minutes
"""

import time
import numpy as np
from collections import deque
from dataclasses import dataclass


@dataclass
class PredictionResult:
    warning_level: str | None   # None, 'yellow', 'orange'
    projected_vfq: float        # projected VFQ at horizon
    minutes_to_threshold: float # minutes until threshold is crossed (-1 if never)
    current_slope: float        # VFQ change per minute (positive = worsening)
    confidence: float           # 0-1, how reliable the projection is
    message: str                # human-readable status


class StrainPredictor:
    """
    Watches VFQ readings over time and forecasts future strain level.

    Algorithm:
      1. Collect (timestamp, vfq) pairs into a rolling 10-minute buffer
      2. Every 30 seconds, fit a linear regression to the last 5 minutes
      3. Compute slope (VFQ/min) and project forward 5 minutes
      4. If projected VFQ crosses threshold — warn

    Requires at least 90 seconds of data before making predictions.
    """

    BUFFER_MINUTES      = 10    # how much history to keep
    MIN_DATA_SECONDS    = 90    # minimum data before predicting
    FIT_WINDOW_MINUTES  = 5     # window used for regression
    YELLOW_MINUTES      = 5.0   # warn this many minutes ahead
    ORANGE_MINUTES      = 2.0   # escalate this many minutes ahead
    MIN_SLOPE_TO_WARN   = 0.5   # minimum VFQ/min rise to bother warning

    def __init__(self, vfq_threshold: float = 40.0):
        self.vfq_threshold  = vfq_threshold
        self._buffer: deque = deque()   # (timestamp_float, vfq_float)
        self._last_result   = PredictionResult(
            warning_level=None, projected_vfq=0.0,
            minutes_to_threshold=-1, current_slope=0.0,
            confidence=0.0, message="Collecting data..."
        )

    def update_threshold(self, threshold: float):
        """Sync threshold with break_reminder config."""
        self.vfq_threshold = threshold

    def add_vfq(self, vfq: float):
        """Call every second with the current VFQ score."""
        now = time.time()
        self._buffer.append((now, float(vfq)))
        # Trim old entries
        cutoff = now - self.BUFFER_MINUTES * 60
        while self._buffer and self._buffer[0][0] < cutoff:
            self._buffer.popleft()

    def predict(self) -> PredictionResult:
        """
        Run regression and return a PredictionResult.
        Call this every 30 seconds from session_manager.
        """
        if not self._buffer:
            return self._no_data("No data yet")

        now      = time.time()
        earliest = self._buffer[0][0]

        # Need at least MIN_DATA_SECONDS of history
        if (now - earliest) < self.MIN_DATA_SECONDS:
            secs_remaining = int(self.MIN_DATA_SECONDS - (now - earliest))
            return self._no_data(f"Collecting data ({secs_remaining}s remaining)")

        # Use last FIT_WINDOW_MINUTES for regression
        fit_cutoff = now - self.FIT_WINDOW_MINUTES * 60
        fit_points = [(t, v) for t, v in self._buffer if t >= fit_cutoff]

        if len(fit_points) < 10:
            return self._no_data("Insufficient data for prediction")

        # Convert timestamps to minutes-since-start for cleaner numbers
        t0   = fit_points[0][0]
        x    = np.array([(t - t0) / 60.0 for t, _ in fit_points])
        y    = np.array([v for _, v in fit_points])

        # Linear regression: y = slope * x + intercept
        try:
            coeffs     = np.polyfit(x, y, 1)
            slope      = float(coeffs[0])   # VFQ per minute
            intercept  = float(coeffs[1])
        except Exception:
            return self._no_data("Regression failed")

        # Residuals → confidence (lower residual = more confident)
        y_pred     = np.polyval(coeffs, x)
        residuals  = np.abs(y - y_pred)
        rmse       = float(np.sqrt(np.mean(residuals ** 2)))
        confidence = max(0.0, min(1.0, 1.0 - rmse / 20.0))

        current_vfq = float(y[-1])
        x_now       = float(x[-1])  # minutes into the fit window

        # Project forward: when does slope cross vfq_threshold?
        if slope <= self.MIN_SLOPE_TO_WARN:
            # Not rising fast enough to worry
            return PredictionResult(
                warning_level=None,
                projected_vfq=current_vfq + slope * self.YELLOW_MINUTES,
                minutes_to_threshold=-1,
                current_slope=slope,
                confidence=confidence,
                message=f"Strain stable (slope: {slope:+.1f} VFQ/min)"
            )

        # Minutes until VFQ reaches threshold from now
        # threshold = slope * (x_now + dt) + intercept
        # dt = (threshold - intercept - slope * x_now) / slope
        if slope > 0:
            dt = (self.vfq_threshold - intercept - slope * x_now) / slope
        else:
            dt = float('inf')

        # Projected VFQ at the yellow warning horizon
        projected_5min = current_vfq + slope * self.YELLOW_MINUTES
        projected_2min = current_vfq + slope * self.ORANGE_MINUTES

        # Already above threshold
        if current_vfq >= self.vfq_threshold:
            return PredictionResult(
                warning_level=None,   # break_reminder handles this
                projected_vfq=current_vfq,
                minutes_to_threshold=0,
                current_slope=slope,
                confidence=confidence,
                message="Break reminder active"
            )

        # Determine warning level
        if dt <= 0:
            warning = None
            message = "Break reminder active"
        elif dt <= self.ORANGE_MINUTES:
            warning = 'orange'
            message = f"⚠️ Strain imminent — {dt:.1f} min to threshold"
        elif dt <= self.YELLOW_MINUTES:
            warning = 'yellow'
            message = f"👁 Strain building — ~{dt:.0f} min to threshold"
        else:
            warning = None
            message = f"Strain rising (+{slope:.1f} VFQ/min), {dt:.0f} min to threshold"

        result = PredictionResult(
            warning_level=warning,
            projected_vfq=projected_5min,
            minutes_to_threshold=max(0, dt),
            current_slope=slope,
            confidence=confidence,
            message=message
        )
        self._last_result = result
        return result

    def get_last_result(self) -> PredictionResult:
        return self._last_result

    def reset(self):
        """Call when session ends."""
        self._buffer.clear()
        self._last_result = PredictionResult(
            warning_level=None, projected_vfq=0.0,
            minutes_to_threshold=-1, current_slope=0.0,
            confidence=0.0, message="Session ended"
        )

    def _no_data(self, msg: str) -> PredictionResult:
        return PredictionResult(
            warning_level=None, projected_vfq=0.0,
            minutes_to_threshold=-1, current_slope=0.0,
            confidence=0.0, message=msg
        )