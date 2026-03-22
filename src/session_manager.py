import os
import json
import time
import numpy as np
from datetime import datetime
from data_logger import DataLogger
from vfq_calculator import VFQCalculator
from break_reminder import BreakReminderSystem
from strain_tracker import StrainTracker
from reward_system import RewardSystem
from personalization import PersonalizationEngine


class SessionManager:
    TCN_FEATURES = [
        'ear', 'blink_rate', 'gaze_x', 'gaze_y', 'gaze_deviation',
        'head_pitch', 'head_yaw', 'head_roll',
        'luminance', 'light_variance', 'glare_detected',
        'keystrokes_per_min', 'backspace_per_min',
        'mouse_dist_per_min', 'clicks_per_min',
        'session_duration',
        'ear_roll_mean', 'ear_roll_std',
        'blink_rate_roll_mean', 'blink_rate_roll_std',
        'gaze_deviation_roll_mean', 'fatigue_progression',
        'ear_trend'
    ]

    def __init__(self, user_id="user_001", profile_dir="../data/profiles"):
        self.user_id      = user_id
        self.profile_dir  = profile_dir
        self.profile_path = os.path.join(profile_dir, f"{user_id}_profile.json")
        self.dashboard    = None  # wired later by dashboard/main.py

        os.makedirs(profile_dir, exist_ok=True)

        self.profile         = self._load_profile()
        self.current_session = None
        self.logger          = None
        self.vfq_calculator  = VFQCalculator(user_id=user_id)
        self.vfq_history     = []
        self.break_reminder  = BreakReminderSystem()
        self.strain_tracker  = StrainTracker()
        self.reward_system   = RewardSystem(user_id=user_id)

        self.personalization          = PersonalizationEngine(user_id=user_id)
        self.personalization.fit()
        self._context_check_interval  = 0

        # Load TCN model for live inference
        self.tcn_model       = None
        self.tcn_device      = None
        self._feature_buffer = []  # rolling 60-second window
        self._load_tcn_model()

    # ── Profile ───────────────────────────────────────────────────────────────

    def _load_profile(self):
        if os.path.exists(self.profile_path):
            with open(self.profile_path, "r") as f:
                return json.load(f)
        profile = {
            "user_id":        self.user_id,
            "created_at":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_sessions": 0,
            "total_duration": 0,
            "baseline_ear":   None,
            "baseline_blink": None,
            "last_session":   None,
            "sessions":       []
        }
        self._save_profile(profile)
        print(f"New user profile created for {self.user_id}")
        return profile

    def _save_profile(self, profile=None):
        if profile is None:
            profile = self.profile
        with open(self.profile_path, "w") as f:
            json.dump(profile, f, indent=2)

    # ── TCN model ─────────────────────────────────────────────────────────────

    def _load_tcn_model(self):
        """Load trained TCN model for live inference."""
        try:
            import torch
            import sys
            sys.path.insert(0, os.path.dirname(__file__))
            from tcn_model import load_model
            model_path = os.path.join(
                os.path.dirname(__file__), '..', 'models', 'tcn_model.pt'
            )
            if os.path.exists(model_path):
                self.tcn_model, self.tcn_device = load_model()
                print("TCN model loaded for live inference.")
            else:
                print("TCN model not found — running VFQ only.")
        except Exception as e:
            print(f"TCN load failed: {e} — running VFQ only.")

    def _run_tcn_inference(self, features):
        """
        Builds a 60-second window and runs TCN prediction.
        Returns (predicted_class, label, probabilities) or None.
        """
        if self.tcn_model is None:
            return None

        try:
            import torch
            from tcn_model import predict

            # Build feature row — 23 values
            row = []
            for col in self.TCN_FEATURES:
                val = features.get(col, 0)
                if val is None or val != val:  # None or NaN
                    val = 0.0
                row.append(float(val))

            # Add to rolling buffer
            self._feature_buffer.append(row)
            if len(self._feature_buffer) > 60:
                self._feature_buffer.pop(0)

            # Only predict when we have a full 60-second window
            if len(self._feature_buffer) < 60:
                return None

            window = np.array(self._feature_buffer, dtype=np.float32)
            pred_class, pred_label, probs = predict(
                self.tcn_model, window, self.tcn_device
            )
            return pred_class, pred_label, probs

        except Exception as e:
            print(f"TCN inference error: {e}")
            return None

    # ── Session lifecycle ─────────────────────────────────────────────────────

    def start_session(self):
        self.vfq_history     = []
        self.current_session = {
            "session_id":     None,
            "start_time":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "end_time":       None,
            "duration":       0,
            "total_blinks":   0,
            "avg_ear":        [],
            "avg_blink_rate": [],
            "strain_events":  0
        }

        self.break_reminder = BreakReminderSystem()
        self.break_reminder.start()

        # Wire break reminder to dashboard — must be after start()
        if self.dashboard is not None:
            self.break_reminder.set_dashboard_callback(
                lambda vfq: self.dashboard.trigger_break_reminder(vfq)
            )
            print("[SessionManager] Break reminder wired to dashboard.")
        else:
            print("[SessionManager] WARNING — dashboard is None, break reminder callback NOT wired.")

        self.logger = DataLogger(user_id=self.user_id, data_dir="../data")
        self.current_session["session_id"] = self.logger.session_id

        self.profile["total_sessions"] += 1
        print(f"Session {self.logger.session_id} started.")
        print(f"Total sessions so far: {self.profile['total_sessions']}")
        return self.logger

    def update_session(self, features):
        # ── Guard — must be first line ──
        if self.current_session is None:
            return None

        # Send to dashboard if wired
        if self.dashboard is not None:
            try:
                self.dashboard.update_from_pipeline(features)
            except Exception:
                pass

        # Compute VFQ
        vfq, components  = self.vfq_calculator.compute(features)
        level, color     = self.vfq_calculator.get_strain_level(vfq)

        features["vfq_score"]    = vfq
        features["strain_label"] = level

        # Track history
        self.vfq_history.append(vfq)
        self.break_reminder.update(vfq)
        self.strain_tracker.update(vfq)
        trend                    = self.strain_tracker.get_trend()
        features["strain_trend"] = trend

        # Reward verification — passive camera monitoring
        reward_status = self.reward_system.update(vfq)

        if reward_status.get('reward_just_earned'):
            if self.dashboard is not None:
                try:
                    self.dashboard.show_reward(
                        points=10,
                        total=self.reward_system.total_points,
                        drop=reward_status.get('drop', 0)
                    )
                except Exception:
                    pass

        elif reward_status.get('expired'):
            if self.dashboard is not None:
                try:
                    self.dashboard.show_verification_failed()
                except Exception:
                    pass

        # Log
        self.logger.log(features)

        # TCN live inference
        tcn_result = self._run_tcn_inference(features)
        if tcn_result:
            tcn_class, tcn_label, tcn_probs = tcn_result
            features['tcn_prediction'] = tcn_label

            # Send to dashboard
            if self.dashboard is not None:
                try:
                    self.dashboard.update_tcn_prediction(tcn_label, tcn_probs)
                except Exception:
                    pass

        # Running stats
        ear = features.get("ear")
        if ear is not None and ear == ear and ear != float('inf'):
            self.current_session["avg_ear"].append(ear)

        blink_rate = features.get("blink_rate")
        if blink_rate is not None:
            self.current_session["avg_blink_rate"].append(blink_rate)

        blink_count = features.get("blink_count")
        if blink_count is not None:
            self.current_session["total_blinks"] = blink_count

        # Re-check context every 5 minutes
        self._context_check_interval += 1
        if self._context_check_interval >= 300:
            self._context_check_interval = 0
            current_feats = {
                'avg_vfq':        np.mean(self.vfq_history[-300:])
                                  if len(self.vfq_history) >= 300
                                  else np.mean(self.vfq_history)
                                  if self.vfq_history else 0,
                'max_vfq':        max(self.vfq_history) if self.vfq_history else 0,
                'high_pct':       sum(1 for v in self.vfq_history if v >= 60)
                                  / max(len(self.vfq_history), 1) * 100,
                'vfq_slope':      0,
                'avg_blink':      features.get('blink_rate', 0),
                'duration_min':   self.current_session['duration'] / 60
                                  if self.current_session else 0,
                'hour_of_day':    datetime.now().hour,
                'avg_keystrokes': features.get('keystrokes_per_min', 0),
            }
            thresholds = self.personalization.predict_context(current_feats)
            # Update break reminder threshold dynamically
            # Update thresholds on the break reminder config dataclass
            self.break_reminder.config.vfq_threshold = thresholds['break_trigger_vfq']
            self.break_reminder.config.sustained_duration_sec = thresholds['break_trigger_duration']

        return vfq, level

    def end_session(self):
        if self.current_session is None:
            return

        self.current_session["end_time"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        duration = self.logger.get_row_count()
        self.current_session["duration"] = duration

        # EAR average
        valid_ear = [
            e for e in self.current_session["avg_ear"]
            if e is not None
            and e == e                # filters NaN
            and e != float('inf')
        ]
        avg_ear = round(sum(valid_ear) / len(valid_ear), 3) if valid_ear else None

        # Blink rate average
        br_list  = self.current_session["avg_blink_rate"]
        avg_blink = round(sum(br_list) / len(br_list), 1) if br_list else None

        # VFQ summary
        if self.vfq_history:
            avg_vfq = round(sum(self.vfq_history) / len(self.vfq_history), 1)
            max_vfq = round(max(self.vfq_history), 1)
        else:
            avg_vfq = 0
            max_vfq = 0

        summary          = self.strain_tracker.get_session_summary()
        high_strain_pct  = summary.get("high_strain_pct", 0)

        # Update profile
        self.profile["total_duration"] += duration
        self.profile["last_session"]    = self.current_session["end_time"]
        self.profile["sessions"].append({
            "session_id": self.current_session["session_id"],
            "date":       self.current_session["start_time"],
            "duration":   duration,
            "avg_ear":    avg_ear,
            "avg_blink":  avg_blink,
            "blinks":     self.current_session["total_blinks"],
            "avg_vfq":    avg_vfq,
            "max_vfq":    max_vfq,
            "high_strain_pct": high_strain_pct
        })
        self._save_profile()

        # Print summary
        print(f"\nSession ended.")
        print(f"Duration:      {duration} seconds")
        print(f"Total blinks:  {self.current_session['total_blinks']}")
        print(f"Avg EAR:       {avg_ear}")
        print(f"Avg blink rate:{avg_blink}/min")
        print(f"Profile saved: {self.profile_path}")
        print(f"Avg VFQ:       {avg_vfq}")
        print(f"Max VFQ:       {max_vfq}")
        print(f"High Strain %: {high_strain_pct}%")

        # Reward summary
        reward_summary = self.reward_system.end_session()
        print(f"Session rewards:   {reward_summary['session_points']} pts "
              f"({reward_summary['session_recoveries']} recoveries)")
        print(f"Total all-time:    {reward_summary['total_points']} pts")

        # Refit personalization with new session data
        self.personalization.fit()

        self.current_session = None
        self.break_reminder.stop()

    def get_profile_summary(self):
        return {
            "user_id":        self.profile["user_id"],
            "total_sessions": self.profile["total_sessions"],
            "total_duration": self.profile["total_duration"],
            "last_session":   self.profile["last_session"]
        }


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import cv2
    from pipeline import UnifiedPipeline

    use_dashboard = "--dashboard" in sys.argv

    manager  = SessionManager(user_id="user_001")
    pipeline = UnifiedPipeline()
    cap      = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("ERROR: Could not open webcam.")
        exit(1)

    if use_dashboard:
        # ── Dashboard mode ──
        # PyQt6 runs on main thread
        # Pipeline runs on background thread
        # OpenCV imshow is DISABLED — dashboard shows everything
        import threading
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QTimer
        from dashboard.main import Dashboard

        qt_app = QApplication(sys.argv)
        dash   = Dashboard(session_manager=manager)
        manager.dashboard = dash

        # Wire Start/Stop signals
        def on_start_requested():
            if not manager.current_session:
                manager.start_session()
                print("Session started from dashboard.")

        def on_stop_requested():
            if manager.current_session:
                manager.end_session()
                print("Session stopped from dashboard.")

        dash.session_start_requested.connect(on_start_requested)
        dash.session_stop_requested.connect(on_stop_requested)
        dash.show()

        # Pipeline runs in background thread — no cv2.imshow
        pipeline_running = threading.Event()
        pipeline_running.set()

        def pipeline_loop():
            print("\nPipeline running. Use dashboard to start/stop session.")
            print("Close dashboard window to exit.\n")
            while pipeline_running.is_set():
                try:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    frame, features = pipeline.process_frame(frame)

                    if manager.current_session is not None:
                        manager.update_session(features)

                except RuntimeError as e:
                    if "shutdown" in str(e).lower():
                        break  # MediaPipe shutting down — exit cleanly
                    print(f"[Pipeline] RuntimeError: {e}")
                    break
                except Exception as e:
                    print(f"[Pipeline] error: {e}")
                    continue

            cap.release()
            pipeline.stop()
            print("Pipeline stopped.")

        thread = threading.Thread(target=pipeline_loop, daemon=True)
        thread.start()

        # When dashboard window closes — stop pipeline
        def on_app_quit():
            pipeline_running.clear()
            if manager.current_session:
                manager.end_session()

        qt_app.aboutToQuit.connect(on_app_quit)

        sys.exit(qt_app.exec())

    else:
        # ── Standalone mode — webcam window only ──
        print("\nStarting session. Press Q to end.")
        print(f"Profile summary: {manager.get_profile_summary()}\n")
        manager.start_session()

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("WARNING: Could not read frame.")
                    break

                frame, features = pipeline.process_frame(frame)
                result          = manager.update_session(features)

                if result:
                    vfq, level = result
                    color_map  = {
                        "NORMAL":   (0, 255, 0),
                        "LOW":      (0, 255, 128),
                        "MODERATE": (0, 165, 255),
                        "HIGH":     (0, 0, 255),
                        "SEVERE":   (0, 0, 180)
                    }
                    color = color_map.get(level, (255, 255, 255))
                    cv2.putText(frame,
                                f"VFQ: {vfq:.1f} — {level}",
                                (20, 40),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.9, color, 2)
                    cv2.putText(frame,
                                f"Rows: {manager.logger.get_row_count()}",
                                (20, 75),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.65, (200, 200, 200), 1)

                cv2.imshow("EyeStrain Monitor", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

        except KeyboardInterrupt:
            pass
        finally:
            manager.end_session()
            pipeline.stop()
            cap.release()
            cv2.destroyAllWindows()