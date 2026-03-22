"""
reward_system.py
Lead Developer — AI Core

Camera-verified reward system.
Monitors VFQ after a break reminder fires.
Verifies physiological recovery — no user input needed.
Issues reward only when real VFQ drop is confirmed by webcam.
"""

import os
import json
import time
import threading
from datetime import datetime
from collections import deque


# ── CONFIG ────────────────────────────────────────────────────────────────────
VERIFY_WINDOW_SECS  = 300   # 5 minutes to verify recovery
MIN_VFQ_DROP        = 20    # VFQ must drop by this much to confirm recovery
POINTS_PER_RECOVERY = 10    # points awarded per verified recovery
SMOOTHING_WINDOW    = 10    # average over last 10 VFQ readings for stability

REWARDS_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'profiles', 'rewards.json'
)


class RewardSystem:
    """
    Monitors VFQ after a break reminder fires.
    Verification is passive — the webcam does all the work.

    Usage:
        reward = RewardSystem(user_id='user_001')
        reward.on_break_triggered(vfq_at_trigger=65.0)
        # Every second, feed VFQ:
        reward.update(current_vfq)
        # Check if reward was just earned:
        if reward.reward_just_earned:
            points = reward.total_points
    """

    def __init__(self, user_id='user_001'):
        self.user_id             = user_id
        self._lock               = threading.Lock()

        # State
        self._verifying          = False
        self._vfq_at_trigger     = 0.0
        self._verify_start_time  = None
        self._verify_elapsed     = 0
        self._vfq_window         = deque(maxlen=SMOOTHING_WINDOW)
        self._action_selected    = None

        # Reward tracking
        self.total_points        = 0
        self.total_recoveries    = 0
        self.reward_just_earned  = False
        self._last_reward_time   = None
        self._session_rewards    = []

        # Load existing points
        self._load_rewards()

    # ── Public API ────────────────────────────────────────────────────────────

    def on_break_triggered(self, vfq_at_trigger: float, action: str = None):
        """
        Call this when break reminder fires and user selects an action.
        Starts the 5-minute verification window.
        """
        with self._lock:
            self._verifying         = True
            self._vfq_at_trigger    = vfq_at_trigger
            self._verify_start_time = time.time()
            self._verify_elapsed    = 0
            self._action_selected   = action
            self._vfq_window.clear()
            self.reward_just_earned = False

        print(f"[RewardSystem] Verification started.")
        print(f"  VFQ at trigger: {vfq_at_trigger:.1f}")
        print(f"  Action selected: {action}")
        print(f"  Need VFQ to drop to: {vfq_at_trigger - MIN_VFQ_DROP:.1f}")
        print(f"  Window: {VERIFY_WINDOW_SECS // 60} minutes")

    def on_break_skipped(self):
        """Call this when user skips the break. No verification started."""
        with self._lock:
            self._verifying = False
            self._vfq_window.clear()

    def update(self, current_vfq: float) -> dict:
        """
        Call every second with the current VFQ from the live pipeline.
        Returns a status dict describing current verification state.
        """
        with self._lock:
            self.reward_just_earned = False

            if not self._verifying:
                return self._status(verified=False, expired=False)

            # Add to smoothing window
            self._vfq_window.append(current_vfq)
            smoothed_vfq = (
                sum(self._vfq_window) / len(self._vfq_window)
            )

            # Update elapsed time
            self._verify_elapsed = time.time() - self._verify_start_time
            time_remaining = max(0, VERIFY_WINDOW_SECS - self._verify_elapsed)

            # Check if VFQ dropped enough — use smoothed value for stability
            drop = self._vfq_at_trigger - smoothed_vfq
            recovered = drop >= MIN_VFQ_DROP

            if recovered:
                # ── Recovery confirmed ──
                self._verifying         = False
                self.total_recoveries  += 1
                self.total_points      += POINTS_PER_RECOVERY
                self.reward_just_earned = True
                self._last_reward_time  = datetime.now()

                reward_event = {
                    "timestamp":       datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"),
                    "vfq_at_trigger":  round(self._vfq_at_trigger, 1),
                    "vfq_at_recovery": round(smoothed_vfq, 1),
                    "vfq_drop":        round(drop, 1),
                    "action":          self._action_selected,
                    "points_earned":   POINTS_PER_RECOVERY,
                    "total_points":    self.total_points,
                    "verify_time_sec": round(self._verify_elapsed, 1),
                }
                self._session_rewards.append(reward_event)
                self._save_rewards()

                print(f"\n[RewardSystem] ✅ Recovery VERIFIED")
                print(f"  VFQ dropped {drop:.1f} points "
                      f"({self._vfq_at_trigger:.1f} → {smoothed_vfq:.1f})")
                print(f"  Time to recovery: {self._verify_elapsed:.0f}s")
                print(f"  Points earned: +{POINTS_PER_RECOVERY}")
                print(f"  Total points: {self.total_points}")

                return self._status(
                    verified=True, expired=False,
                    drop=drop, smoothed_vfq=smoothed_vfq
                )

            elif time_remaining <= 0:
                # ── Window expired — no recovery ──
                self._verifying = False
                print(f"\n[RewardSystem] ⏰ Verification window expired.")
                print(f"  VFQ only dropped {drop:.1f} points "
                      f"(needed {MIN_VFQ_DROP})")
                return self._status(verified=False, expired=True, drop=drop)

            # ── Still verifying ──
            return self._status(
                verified=False, expired=False,
                drop=drop,
                smoothed_vfq=smoothed_vfq,
                time_remaining=int(time_remaining),
                progress=self._verify_elapsed / VERIFY_WINDOW_SECS
            )

    def get_status(self) -> dict:
        """Returns current verification state for dashboard polling."""
        with self._lock:
            return {
                "verifying":        self._verifying,
                "vfq_at_trigger":   self._vfq_at_trigger,
                "elapsed":          self._verify_elapsed,
                "total_points":     self.total_points,
                "total_recoveries": self.total_recoveries,
                "reward_just_earned": self.reward_just_earned,
            }

    def end_session(self) -> dict:
        """
        Call at session end to get session reward summary.
        Saves rewards to disk.
        """
        with self._lock:
            self._verifying = False
            summary = {
                "session_recoveries": len(self._session_rewards),
                "session_points":     sum(
                    r['points_earned'] for r in self._session_rewards),
                "total_points":       self.total_points,
                "total_recoveries":   self.total_recoveries,
                "events":             self._session_rewards.copy()
            }
            self._session_rewards = []
            self._save_rewards()
            return summary

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_rewards(self):
        try:
            if os.path.exists(REWARDS_PATH):
                with open(REWARDS_PATH, 'r') as f:
                    data = json.load(f)
                self.total_points     = data.get('total_points', 0)
                self.total_recoveries = data.get('total_recoveries', 0)
                print(f"[RewardSystem] Loaded — "
                      f"{self.total_points} pts, "
                      f"{self.total_recoveries} recoveries")
        except Exception as e:
            print(f"[RewardSystem] Could not load rewards: {e}")

    def _save_rewards(self):
        try:
            os.makedirs(os.path.dirname(REWARDS_PATH), exist_ok=True)
            data = {
                "user_id":          self.user_id,
                "total_points":     self.total_points,
                "total_recoveries": self.total_recoveries,
                "last_updated":     datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"),
                "history":          self._session_rewards
            }
            with open(REWARDS_PATH, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[RewardSystem] Could not save rewards: {e}")

    def _status(self, verified, expired, drop=0,
                smoothed_vfq=None, time_remaining=None, progress=0):
        return {
            "verifying":      self._verifying,
            "verified":       verified,
            "expired":        expired,
            "vfq_at_trigger": self._vfq_at_trigger,
            "drop":           round(drop, 1),
            "smoothed_vfq":   smoothed_vfq,
            "time_remaining": time_remaining,
            "progress":       progress,
            "total_points":   self.total_points,
        }