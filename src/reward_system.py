"""
reward_system.py
EyeStrain AI — Lead Developer

Dual-layer camera-verified reward system.
Each action has its own accurate verifier based on what physically happens.

Verification logic:
  20-20-20 Rule  — gaze away sustained 20 consecutive seconds
  Eye Drops      — 20 blinks counted from trigger
  Neck Stretch   — head turned right (yaw > +15) AND left (yaw < -15)
  Stand & Walk   — face not detected for 20 consecutive seconds

Reward tiers:
  Gold   (action verified + VFQ drop >= 50)  → 50 pts
  Silver (action verified + VFQ drop >= 30)  → 25 pts
  Bronze (action verified)                   → 10 pts
"""

import os
import json
import time
import threading
from datetime import datetime
from collections import deque


# ── CONFIG ────────────────────────────────────────────────────────────────────
SMOOTHING_WINDOW = 10

# Per-action verification windows (seconds)
VERIFY_WINDOWS = {
    '20-20-20 Rule': 40,
    'Eye Drops':     60,
    'Neck Stretch':  45,
    'Stand & Walk':  120,
}

# Rewards path is now instance-level per user — see RewardSystem.__init__

# ── REWARD TIERS ──────────────────────────────────────────────────────────────
REWARD_TIERS = [
    {'name': 'Gold',   'icon': '🥇', 'min_drop': 50, 'points': 50, 'color': '#F59E0B'},
    {'name': 'Silver', 'icon': '🥈', 'min_drop': 30, 'points': 25, 'color': '#9CA3AF'},
    {'name': 'Bronze', 'icon': '🥉', 'min_drop': 20, 'points': 10, 'color': '#B45309'},
]


def get_reward_tier(drop: float) -> dict | None:
    for tier in REWARD_TIERS:
        if drop >= tier['min_drop']:
            return tier
    return None


# ── ACTION VERIFIERS ──────────────────────────────────────────────────────────

class ActionVerifier:
    """Base class for all action verifiers."""

    def __init__(self):
        self.verified    = False
        self.verified_at = None
        self.confidence  = 0.0
        self.status_text = "Waiting — perform the action"

    def update(self, features: dict, elapsed: float) -> bool:
        raise NotImplementedError

    def get_status(self) -> dict:
        return {
            'verified':    self.verified,
            'confidence':  self.confidence,
            'status_text': self.status_text,
        }


class Verifier2020(ActionVerifier):
    """
    20-20-20 Rule verifier.
    Uses real wall-clock time so frame rate does not affect the count.
    Requires gaze away for 20 CONSECUTIVE real seconds.
    Gate: keystrokes/mouse must be idle.
    """
    REQUIRED_CONSECUTIVE = 20  # real seconds

    def __init__(self, baseline_gaze=1.08):
        super().__init__()
        self.baseline_gaze   = baseline_gaze
        # Threshold: baseline + 0.7, but capped at 2.0 for uncalibrated users.
        # Without a real baseline, baseline_gaze=1.08 gives threshold=1.78
        # which is often too tight — small head movements cross it momentarily.
        # Cap at 2.0 ensures the threshold is reachable by a new user looking away.
        raw_threshold          = baseline_gaze + 0.7
        self._gaze_threshold   = min(raw_threshold, 2.0)
        self._gaze_away_since  = None  # wall time when gaze first went away
        self._gaze_miss_frames = 0    # consecutive below-threshold frames

    def update(self, features: dict, elapsed: float) -> bool:
        gaze  = features.get('gaze_deviation', 0) or 0
        keys  = features.get('keystrokes_per_min', 0) or 0
        mouse = features.get('mouse_dist_per_min', 0) or 0

        # Gate — must not be typing or using mouse
        # Gate: block only if actively typing (>=10 keys/min) OR
        # mouse distance is very high (>=5000 px/min = active scrolling/dragging)
        # Raised from 2000 to 5000 — 15s rolling window accumulates distance
        # even from incidental movements when picking up/putting down mouse
        if keys >= 10 or mouse >= 5000:
            self._gaze_away_since = None
            self.confidence       = 0.0
            self.status_text      = "Stop typing — look away from screen"
            print(f"  [20-20-20] GATE: still working (keys={keys:.1f} mouse={mouse:.0f})")
            return False

        now = time.time()

        if gaze > self._gaze_threshold:
            # Gaze is away — start or continue streak
            if self._gaze_away_since is None:
                self._gaze_away_since = now
            self._gaze_miss_frames = 0
            secs = int(now - self._gaze_away_since)
        else:
            # Allow up to 3 consecutive frames below threshold before reset.
            # Natural tracking noise causes 1-2 frame drops even when the
            # user is genuinely looking away at something 20 feet distant.
            self._gaze_miss_frames += 1
            if self._gaze_miss_frames > 3:
                self._gaze_away_since  = None
                self._gaze_miss_frames = 0
                secs = 0
            else:
                secs = int(now - self._gaze_away_since)                     if self._gaze_away_since else 0

        self.confidence = min(1.0, secs / self.REQUIRED_CONSECUTIVE)

        if secs >= self.REQUIRED_CONSECUTIVE and not self.verified:
            self.verified    = True
            self.verified_at = elapsed
            self.status_text = "✅  20 seconds of looking away — verified!"
        elif secs > 0:
            self.status_text = (
                f"👀  Looking away... "
                f"{secs}/{self.REQUIRED_CONSECUTIVE}s sustained"
            )
        else:
            self.status_text = (
                f"Look at something far away "
                f"(need {self.REQUIRED_CONSECUTIVE}s continuous)"
            )

        print(f"  [20-20-20] gaze={gaze:.2f}(need>{self._gaze_threshold:.2f}) "
              f"secs={secs}s conf={self.confidence:.2f}")
        return self.verified


class VerifierBlink(ActionVerifier):
    """
    Eye Drops / Blink Exercise verifier.
    Requires: 20 blinks from the moment verification starts.
    Tracks cumulative blink_count from eye_features.py.
    """
    REQUIRED_BLINKS = 20

    def __init__(self):
        super().__init__()
        self._blink_count_start = None
        self._blinks_done       = 0

    def update(self, features: dict, elapsed: float) -> bool:
        blink_count = features.get('blink_count', 0) or 0

        # Record baseline on first call
        if self._blink_count_start is None:
            self._blink_count_start = blink_count
            print(f"  [Blink] Baseline blink_count={blink_count}")

        self._blinks_done = max(0, blink_count - self._blink_count_start)
        self.confidence   = min(1.0, self._blinks_done / self.REQUIRED_BLINKS)

        if self._blinks_done >= self.REQUIRED_BLINKS and not self.verified:
            self.verified    = True
            self.verified_at = elapsed
            self.status_text = f"✅  {self._blinks_done} blinks detected — verified!"
        else:
            self.status_text = (
                f"💧  {self._blinks_done}/{self.REQUIRED_BLINKS} blinks detected"
            )

        print(f"  [Blink] blink_count={blink_count} "
              f"blinks_done={self._blinks_done}/{self.REQUIRED_BLINKS} "
              f"conf={self.confidence:.2f}")
        return self.verified


class VerifierNeck(ActionVerifier):
    """
    Neck Stretch verifier.
    Requires: head turned RIGHT (yaw > +15) AND LEFT (yaw < -15).
    Both directions must be visited within the verification window.
    """
    YAW_THRESHOLD = 15.0

    def __init__(self):
        super().__init__()
        self._turned_right = False
        self._turned_left  = False

    def update(self, features: dict, elapsed: float) -> bool:
        yaw  = features.get('head_yaw', 0) or 0
        # No keystroke gate for Neck Stretch — user physically cannot type
        # while turning head 90 degrees. Rolling window also keeps rate
        # falsely elevated for 30-60s after stopping typing.

        if yaw > self.YAW_THRESHOLD:
            self._turned_right = True
        if yaw < -self.YAW_THRESHOLD:
            self._turned_left = True

        self.confidence = (
            (0.5 if self._turned_right else 0) +
            (0.5 if self._turned_left  else 0)
        )

        right_str = "✅ Right" if self._turned_right else "⬜ Right"
        left_str  = "✅ Left"  if self._turned_left  else "⬜ Left"

        if self._turned_right and self._turned_left and not self.verified:
            self.verified    = True
            self.verified_at = elapsed
            self.status_text = "✅  Both directions completed — verified!"
        else:
            self.status_text = f"🧘  {right_str}  |  {left_str}"

        print(f"  [Neck] yaw={yaw:.1f} "
              f"right={self._turned_right} left={self._turned_left} "
              f"conf={self.confidence:.2f}")
        return self.verified


class VerifierWalk(ActionVerifier):
    """
    Stand & Walk verifier.
    Uses real wall-clock time — face must be absent for 20 CONSECUTIVE real seconds.
    """
    REQUIRED_AWAY_SECS = 20

    def __init__(self):
        super().__init__()
        self._away_since = None  # wall time when face first disappeared

    def update(self, features: dict, elapsed: float) -> bool:
        face_detected = features.get('face_detected', True)
        now           = time.time()

        if not face_detected:
            if self._away_since is None:
                self._away_since = now
            secs = int(now - self._away_since)
        else:
            self._away_since = None
            secs = 0

        self.confidence = min(1.0, secs / self.REQUIRED_AWAY_SECS)

        if secs >= self.REQUIRED_AWAY_SECS and not self.verified:
            self.verified    = True
            self.verified_at = elapsed
            self.status_text = "✅  Away from screen 20 seconds — verified!"
        elif secs > 0:
            self.status_text = (
                f"🚶  Away from screen... "
                f"{secs}/{self.REQUIRED_AWAY_SECS}s"
            )
        else:
            self.status_text = "Step away from your screen completely"

        print(f"  [Walk] face_detected={face_detected} "
              f"away_secs={self._away_secs}/{self.REQUIRED_AWAY_SECS} "
              f"conf={self.confidence:.2f}")
        return self.verified


def build_verifier(action: str, baseline: dict) -> ActionVerifier:
    """Factory — returns the correct verifier for the action."""
    baseline_gaze = baseline.get('gaze_mean', 1.08) if baseline else 1.08

    if action == '20-20-20 Rule':
        return Verifier2020(baseline_gaze)
    elif action == 'Eye Drops':
        return VerifierBlink()
    elif action == 'Neck Stretch':
        return VerifierNeck()
    elif action == 'Stand & Walk':
        return VerifierWalk()
    else:
        return Verifier2020(baseline_gaze)


# ── REWARD SYSTEM ─────────────────────────────────────────────────────────────
class RewardSystem:
    """
    Dual-layer verification:
      Layer 1 — Action verifier (physical action detected)
      Layer 2 — VFQ drop (physiological recovery)

    For 20-20-20 and Eye Drops:
      VFQ formula conflicts with these actions (gaze deviation = VFQ goes up)
      So action verification alone earns Bronze.
      Silver/Gold still possible if VFQ also drops.

    For Neck Stretch and Stand & Walk:
      Action verification → Bronze minimum.
      VFQ drop → Silver or Gold.
    """

    def __init__(self, user_id='user_001', baseline: dict = None,
                 rewards_path: str = None,
                 behavioral_extractor=None):
        self.user_id               = user_id
        self.baseline              = baseline or {}
        self._lock                 = threading.Lock()
        self._behavioral_extractor = behavioral_extractor
        # User-scoped rewards path — overrides legacy default
        if rewards_path is not None:
            self._rewards_path = rewards_path
        else:
            _base = os.path.dirname(os.path.abspath(__file__))
            self._rewards_path = os.path.join(
                _base, '..', 'data', 'users', user_id, 'rewards.json'
            )
        os.makedirs(os.path.dirname(self._rewards_path), exist_ok=True)

        self._verifying         = False
        self._vfq_at_trigger    = 0.0
        self._verify_start_time = None
        self._verify_elapsed    = 0.0
        self._verify_window     = 60
        self._vfq_window        = deque(maxlen=SMOOTHING_WINDOW)
        self._action_selected   = None
        self._action_verifier   = None

        self.total_points       = 0
        self.total_recoveries   = 0
        self.reward_just_earned = False
        self.last_tier          = None
        self._last_reward_time  = None
        self._session_rewards   = []

        self._load_rewards()

    def set_baseline(self, baseline: dict):
        self.baseline = baseline or {}

    def set_behavioral_extractor(self, extractor):
        """Wire the behavioral extractor so keyboard history can be reset on verification start."""
        self._behavioral_extractor = extractor

    def on_break_triggered(self, vfq_at_trigger: float, action: str = None):
        with self._lock:
            self._verifying         = True
            self._vfq_at_trigger    = vfq_at_trigger
            self._verify_start_time = time.time()
            self._verify_elapsed    = 0.0
            self._verify_window     = VERIFY_WINDOWS.get(action, 60)
            self._action_selected   = action
            self._vfq_window.clear()
            self.reward_just_earned = False
            self.last_tier          = None
            self._action_verifier   = build_verifier(action, self.baseline)

        # Reset keyboard AND mouse buffers so stale pre-break activity
        # doesn't block gates during verification
        if self._behavioral_extractor is not None:
            try:
                self._behavioral_extractor.reset_keyboard()
                if hasattr(self._behavioral_extractor, 'reset_mouse'):
                    self._behavioral_extractor.reset_mouse()
                print("  [RewardSystem] Behavioral buffers reset for clean gate check")
            except Exception as e:
                print(f"  [RewardSystem] Buffer reset failed: {e}")

        print(f"\n[RewardSystem] Verification started.")
        print(f"  Action:  {action}")
        print(f"  VFQ now: {vfq_at_trigger:.1f}")
        print(f"  Window:  {self._verify_window}s")

    def on_break_skipped(self):
        with self._lock:
            self._verifying       = False
            self._action_verifier = None
            self._vfq_window.clear()

    def update(self, current_vfq: float, features: dict = None) -> dict:
        """Call every second with VFQ + full features dict."""
        with self._lock:
            if not self._verifying:
                return self._status(verified=False, expired=False)

            self._verify_elapsed = time.time() - self._verify_start_time
            time_remaining       = max(0.0, self._verify_window - self._verify_elapsed)

            # ── Layer 1: Action verification ──
            action_verified   = False
            action_confidence = 0.0
            status_text       = "Waiting — perform the action"

            if self._action_verifier and features:
                action_verified   = self._action_verifier.update(
                    features, self._verify_elapsed)
                action_confidence = self._action_verifier.confidence
                status_text       = self._action_verifier.status_text

            # ── Layer 2: VFQ drop ──
            self._vfq_window.append(current_vfq)
            smoothed_vfq = sum(self._vfq_window) / len(self._vfq_window)
            drop         = self._vfq_at_trigger - smoothed_vfq

            # ── Determine tier ──
            tier = None
            if action_verified:
                if self._action_selected in ('20-20-20 Rule', 'Eye Drops'):
                    # VFQ drop unreliable for these — action verification is enough
                    tier = get_reward_tier(max(drop, 10))
                    if tier is None:
                        tier = REWARD_TIERS[-1]  # Bronze guaranteed
                else:
                    # Neck Stretch and Stand & Walk
                    tier = get_reward_tier(drop)
                    if tier is None:
                        tier = REWARD_TIERS[-1]  # Bronze minimum

            if tier:
                self._verifying         = False
                self.total_recoveries  += 1
                self.total_points      += tier['points']
                self.reward_just_earned = True
                self.last_tier          = tier
                self._last_reward_time  = datetime.now()

                reward_event = {
                    "timestamp":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "vfq_at_trigger":   round(self._vfq_at_trigger, 1),
                    "vfq_at_recovery":  round(smoothed_vfq, 1),
                    "vfq_drop":         round(drop, 1),
                    "tier":             tier['name'],
                    "icon":             tier['icon'],
                    "action":           self._action_selected,
                    "action_verified":  action_verified,
                    "action_confidence":round(action_confidence, 2),
                    "points_earned":    tier['points'],
                    "total_points":     self.total_points,
                    "verify_time_sec":  round(self._verify_elapsed, 1),
                }
                self._session_rewards.append(reward_event)
                self._save_rewards()

                print(f"\n[RewardSystem] {tier['icon']} {tier['name'].upper()} VERIFIED")
                print(f"  Action confirmed: {action_verified} "
                      f"(confidence {action_confidence:.0%})")
                print(f"  VFQ drop: {drop:.1f} pts")
                print(f"  Points: +{tier['points']} → total {self.total_points}")

                return self._status(
                    verified=True, expired=False,
                    drop=drop, smoothed_vfq=smoothed_vfq,
                    tier=tier,
                    action_verified=action_verified,
                    action_confidence=action_confidence,
                    status_text=status_text,
                )

            elif time_remaining <= 0:
                self._verifying = False
                print(f"\n[RewardSystem] ⏰ Window expired. "
                      f"drop={drop:.1f} action_verified={action_verified}")
                return self._status(
                    verified=False, expired=True, drop=drop,
                    action_verified=action_verified,
                    action_confidence=action_confidence,
                    status_text=status_text,
                )

            return self._status(
                verified=False, expired=False,
                drop=drop, smoothed_vfq=smoothed_vfq,
                time_remaining=int(time_remaining),
                progress=self._verify_elapsed / self._verify_window,
                action_verified=action_verified,
                action_confidence=action_confidence,
                status_text=status_text,
            )

    def get_status(self) -> dict:
        with self._lock:
            return {
                "verifying":          self._verifying,
                "vfq_at_trigger":     self._vfq_at_trigger,
                "elapsed":            self._verify_elapsed,
                "total_points":       self.total_points,
                "total_recoveries":   self.total_recoveries,
                "reward_just_earned": self.reward_just_earned,
                "last_tier":          self.last_tier,
            }

    def end_session(self) -> dict:
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

    def _load_rewards(self):
        try:
            if os.path.exists(self._rewards_path):
                with open(self._rewards_path, 'r') as f:
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
            os.makedirs(os.path.dirname(self._rewards_path), exist_ok=True)
            data = {
                "user_id":          self.user_id,
                "total_points":     self.total_points,
                "total_recoveries": self.total_recoveries,
                "last_updated":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "history":          self._session_rewards
            }
            with open(self._rewards_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[RewardSystem] Could not save rewards: {e}")

    def _status(self, verified, expired, drop=0,
                smoothed_vfq=None, time_remaining=None,
                progress=0, tier=None,
                action_verified=False, action_confidence=0.0,
                status_text=""):
        return {
            "verifying":          self._verifying,
            "verified":           verified,
            "expired":            expired,
            "vfq_at_trigger":     self._vfq_at_trigger,
            "drop":               round(drop, 1),
            "smoothed_vfq":       smoothed_vfq,
            "time_remaining":     time_remaining,
            "progress":           progress,
            "total_points":       self.total_points,
            "tier":               tier,
            "action_verified":    action_verified,
            "action_confidence":  round(action_confidence, 2),
            "status_text":        status_text,
        }