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
from strain_predictor import StrainPredictor


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

    def __init__(self, user_id="user_001", profile_dir=None):
        # ── Resolve all paths relative to this file — never relative to cwd ──
        _base = os.path.dirname(os.path.abspath(__file__))
        _root = os.path.join(_base, '..')

        self.user_id  = user_id
        self.dashboard = None

        # ── Multi-user paths ─────────────────────────────────────────────────
        # New: data/users/{user_id}/
        # Legacy fallback: data/profiles/ (for user_001 before migration)
        _users_dir  = os.path.join(_root, 'data', 'users', user_id)
        _legacy_dir = os.path.join(_root, 'data', 'profiles')

        # Use new user-scoped dir if it exists, else legacy
        if os.path.isdir(_users_dir):
            self.profile_dir      = _users_dir
            self._sessions_dir    = os.path.join(_users_dir, 'sessions')
            self._rewards_path    = os.path.join(_users_dir, 'rewards.json')
            self._pers_path       = os.path.join(_users_dir, 'personalization.json')
            self._user_scoped     = True
        else:
            # Legacy layout — still works for user_001 before migration
            self.profile_dir      = profile_dir or _legacy_dir
            self._sessions_dir    = os.path.join(_root, 'data')
            self._rewards_path    = os.path.join(_legacy_dir, 'rewards.json')
            self._pers_path       = os.path.join(
                _legacy_dir, f'{user_id}_personalization.json')
            self._user_scoped     = False
            print(f"[SessionManager] Using legacy paths for {user_id}")

        self.profile_path = os.path.join(
            self.profile_dir, 'profile.json'
            if self._user_scoped else f'{user_id}_profile.json')

        os.makedirs(self.profile_dir,   exist_ok=True)
        os.makedirs(self._sessions_dir, exist_ok=True)

        self.profile         = self._load_profile()
        self.current_session = None
        self.logger          = None
        self.vfq_calculator  = VFQCalculator(user_id=user_id)
        self.vfq_history     = []
        self.break_reminder  = BreakReminderSystem()
        self.strain_tracker  = StrainTracker()

        # RewardSystem — pass user-scoped rewards path
        self.reward_system   = RewardSystem(
            user_id=user_id,
            rewards_path=self._rewards_path
        )
        if self.profile.get('baseline'):
            self.reward_system.set_baseline(self.profile['baseline'])
            # Note: _apply_personal_threshold() called AFTER strain_predictor is created below

        # Wire behavioral extractor for keyboard reset on verification start
        # Pipeline is created in __main__ — wired via set_behavioral_extractor
        # after pipeline.process_frame first call exposes the extractor

        # PersonalizationEngine — pass user-scoped paths
        self.personalization  = PersonalizationEngine(
            user_id=user_id,
            sessions_dir=self._sessions_dir,
            output_path=self._pers_path,
        )
        self.personalization.fit()
        self._context_check_interval = 0

        # Strain Predictor
        self.strain_predictor    = StrainPredictor(
            vfq_threshold=self.break_reminder.config.vfq_threshold
        )
        self._predictor_tick     = 0
        self._predictor_interval = 30

        # Now safe to apply personal threshold — strain_predictor exists
        if self.profile.get('baseline'):
            self._apply_personal_threshold()

        # TCN model
        self.tcn_model       = None
        self.tcn_device      = None
        self._feature_buffer = []
        self._load_tcn_model()

    # ── Personal threshold ────────────────────────────────────────────────────

    def _apply_personal_threshold(self):
        """
        Set break reminder threshold from the user's personal VFQ baseline.
        Uses 25th-percentile VFQ + 20, computed by baseline_profiler.
        Falls back to default 40 if not yet calibrated.

        Runs at init and at each session start so the threshold updates
        as more sessions accumulate. After 3 sessions, personalization
        clustering also adjusts it dynamically every 5 minutes.
        """
        baseline  = self.profile.get('baseline', {})
        threshold = baseline.get('personal_vfq_threshold')

        if threshold is not None:
            old_t = self.break_reminder.config.vfq_threshold
            self.break_reminder.config.vfq_threshold = float(threshold)
            self.strain_predictor.update_threshold(float(threshold))
            print(f"[SessionManager] Personal VFQ threshold: "
                  f"{old_t} → {threshold} "
                  f"(baseline p25={baseline.get('vfq_p25','?')} + 20)")
        else:
            print(f"[SessionManager] No personal threshold yet — "
                  f"using default {self.break_reminder.config.vfq_threshold}")

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
        try:
            import sys
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from tcn_model import load_model
            model_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                '..', 'models', 'tcn_model.pt'
            )
            if os.path.exists(model_path):
                self.tcn_model, self.tcn_device = load_model()
                print("TCN model loaded for live inference.")
            else:
                print("TCN model not found — running VFQ only.")
        except Exception as e:
            print(f"TCN load failed: {e} — running VFQ only.")

    def _run_tcn_inference(self, features):
        if self.tcn_model is None:
            return None
        try:
            from tcn_model import predict
            row = []
            for col in self.TCN_FEATURES:
                val = features.get(col, 0)
                if val is None or val != val:
                    val = 0.0
                row.append(float(val))
            self._feature_buffer.append(row)
            if len(self._feature_buffer) > 60:
                self._feature_buffer.pop(0)
            if len(self._feature_buffer) < 60:
                return None
            window = np.array(self._feature_buffer, dtype=np.float32)
            return predict(self.tcn_model, window, self.tcn_device)
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
        # Force production defaults — break_reminder.py may have testing values
        self.break_reminder.config.vfq_threshold          = 40.0
        self.break_reminder.config.sustained_duration_sec = 300.0
        self.break_reminder.config.cooldown_sec           = 600.0
        self.break_reminder.config.check_interval_sec     = 5.0
        self.break_reminder.start()

        # Re-apply personal threshold each session (overrides the 40 above if baseline exists)
        self._apply_personal_threshold()
        # Update personal gauge in LiveScreen
        if self.dashboard is not None:
            pt = self.profile.get('baseline', {}).get('personal_vfq_threshold')
            if pt and hasattr(self.dashboard, 'screen_live'):
                try:
                    self.dashboard.screen_live.set_personal_threshold(pt)
                except Exception:
                    pass

        self.strain_predictor.update_threshold(
            self.break_reminder.config.vfq_threshold)
        self.strain_predictor.reset()
        self._predictor_tick = 0

        if self.dashboard is not None:
            def _break_callback(vfq):
                if self.reward_system._verifying:
                    print("[BreakReminder] Skipped — verification in progress")
                    return
                self.dashboard.trigger_break_reminder(vfq)
            self.break_reminder.set_dashboard_callback(_break_callback)
            print("[SessionManager] Break reminder wired to dashboard.")
        else:
            print("[SessionManager] WARNING — dashboard is None.")

        # DataLogger — write to user-scoped sessions folder
        self.logger = DataLogger(
            user_id=self.user_id,
            data_dir=self._sessions_dir
        )
        self.current_session["session_id"] = self.logger.session_id

        # Show baseline clinical warning once if needed
        if (not self.profile.get('baseline_warning_shown', True) and
                self.profile.get('baseline_clinical_warnings')):
            if self.dashboard is not None:
                try:
                    self.dashboard.show_baseline_warning(
                        self.profile['baseline_clinical_warnings']
                    )
                    self.profile['baseline_warning_shown'] = True
                    self._save_profile()
                except Exception as e:
                    print(f"[Baseline Warning] {e}")

        self.profile["total_sessions"] += 1
        print(f"Session {self.logger.session_id} started.")
        print(f"Data dir: {os.path.abspath(self._sessions_dir)}")
        print(f"Total sessions so far: {self.profile['total_sessions']}")
        return self.logger

    def update_session(self, features):
        if self.current_session is None:
            return None

        if self.dashboard is not None:
            try:
                self.dashboard.update_from_pipeline(features)
            except Exception:
                pass

        if not features.get('face_detected', True):
            self.reward_system.update(0, features)
            return None

        vfq, components  = self.vfq_calculator.compute(features)
        level, color     = self.vfq_calculator.get_strain_level(vfq)

        features["vfq_score"]    = vfq
        features["strain_label"] = level

        self.vfq_history.append(vfq)
        self.break_reminder.update(vfq)
        self.strain_tracker.update(vfq)
        trend                    = self.strain_tracker.get_trend()
        features["strain_trend"] = trend

        # Strain predictor
        self.strain_predictor.add_vfq(vfq)
        self._predictor_tick += 1
        if self._predictor_tick >= self._predictor_interval:
            self._predictor_tick = 0
            prediction = self.strain_predictor.predict()
            print(f"[Predictor] {prediction.message} "
                  f"(slope={prediction.current_slope:+.2f} VFQ/min, "
                  f"conf={prediction.confidence:.2f})")
            if self.dashboard is not None:
                try:
                    self.dashboard.update_strain_forecast(
                        level=prediction.warning_level,
                        message=prediction.message,
                        minutes=prediction.minutes_to_threshold,
                    )
                except Exception as e:
                    print(f"[Predictor] Dashboard error: {e}")

        reward_status = self.reward_system.update(vfq, features)

        if reward_status.get('reward_just_earned'):
            if self.dashboard is not None:
                try:
                    tier = self.reward_system.last_tier
                    self.dashboard.show_reward(
                        points=tier['points'] if tier else 10,
                        total=self.reward_system.total_points,
                        drop=reward_status.get('drop', 0),
                        tier_name=tier['name'] if tier else 'Bronze'
                    )
                except Exception:
                    pass
        elif reward_status.get('expired'):
            if self.dashboard is not None:
                try:
                    self.dashboard.show_verification_failed()
                except Exception:
                    pass

        self.logger.log(features)

        tcn_result = self._run_tcn_inference(features)
        if tcn_result:
            tcn_class, tcn_label, tcn_probs = tcn_result
            features['tcn_prediction'] = tcn_label
            if self.dashboard is not None:
                try:
                    self.dashboard.update_tcn_prediction(tcn_label, tcn_probs)
                except Exception:
                    pass

        ear = features.get("ear")
        if ear is not None and ear == ear and ear != float('inf'):
            self.current_session["avg_ear"].append(ear)

        blink_rate = features.get("blink_rate")
        if blink_rate is not None:
            self.current_session["avg_blink_rate"].append(blink_rate)

        blink_count = features.get("blink_count")
        if blink_count is not None:
            self.current_session["total_blinks"] = blink_count

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
            self.break_reminder.config.vfq_threshold          = thresholds['break_trigger_vfq']
            self.break_reminder.config.sustained_duration_sec = thresholds['break_trigger_duration']
            self.strain_predictor.update_threshold(thresholds['break_trigger_vfq'])

        return vfq, level

    def end_session(self):
        if self.current_session is None:
            return

        self.current_session["end_time"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S")
        duration  = self.logger.get_row_count()
        self.current_session["duration"] = duration

        valid_ear = [e for e in self.current_session["avg_ear"]
                     if e is not None and e == e and e != float('inf')]
        avg_ear   = round(sum(valid_ear)/len(valid_ear), 3) if valid_ear else None
        br_list   = self.current_session["avg_blink_rate"]
        avg_blink = round(sum(br_list)/len(br_list), 1) if br_list else None

        if self.vfq_history:
            avg_vfq = round(sum(self.vfq_history)/len(self.vfq_history), 1)
            max_vfq = round(max(self.vfq_history), 1)
        else:
            avg_vfq = 0; max_vfq = 0

        summary         = self.strain_tracker.get_session_summary()
        high_strain_pct = summary.get("high_strain_pct", 0)

        self.profile["total_duration"] += duration
        self.profile["last_session"]    = self.current_session["end_time"]
        self.profile["sessions"].append({
            "session_id":      self.current_session["session_id"],
            "date":            self.current_session["start_time"],
            "duration":        duration,
            "avg_ear":         avg_ear,
            "avg_blink":       avg_blink,
            "blinks":          self.current_session["total_blinks"],
            "avg_vfq":         avg_vfq,
            "max_vfq":         max_vfq,
            "high_strain_pct": high_strain_pct
        })
        self._save_profile()

        print(f"\nSession ended.")
        print(f"Duration:      {duration} seconds")
        print(f"Avg VFQ:       {avg_vfq}  |  Max VFQ: {max_vfq}")
        print(f"High Strain %: {high_strain_pct}%")

        reward_summary = self.reward_system.end_session()
        print(f"Session rewards: {reward_summary['session_points']} pts "
              f"({reward_summary['session_recoveries']} recoveries)")
        print(f"Total all-time:  {reward_summary['total_points']} pts")

        self.strain_predictor.reset()
        self.personalization.fit()

        # Auto-recompute personal VFQ threshold after every session
        # so it improves as more data accumulates
        total = self.profile.get('total_sessions', 0)
        if total >= 1:   # run after every session (more data = better threshold)
            try:
                from baseline_profiler import BaselineProfiler
                profiler = BaselineProfiler(
                    user_id=self.user_id,
                    data_dir=self._sessions_dir,
                    profile_dir=self.profile_dir
                )
                baseline = profiler.run()
                if baseline:
                    # Reload profile so next session picks up new threshold
                    self.profile = self._load_profile()
                    print(f"[SessionManager] Baseline updated. "
                          f"New threshold: "
                          f"{self.profile.get('baseline',{}).get('personal_vfq_threshold','?')}")
            except Exception as e:
                print(f"[SessionManager] Baseline update skipped: {e}")

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
    user_id       = next(
        (a.split('=')[1] for a in sys.argv if a.startswith('--user=')),
        'user_001'
    )

    # ── Pipeline and camera init — no SessionManager yet ────────────────────
    # SessionManager is only created AFTER login so no user data loads before
    # the user has authenticated. The pipeline and camera start early so
    # MediaPipe has time to warm up while the login screen is showing.
    pipeline = UnifiedPipeline()
    cap      = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("ERROR: Could not open webcam.")
        exit(1)

    if use_dashboard:
        import threading
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from PyQt6.QtWidgets import QApplication
        from dashboard.login import LoginWindow
        from dashboard.main  import Dashboard

        qt_app = QApplication(sys.argv)

        login_win = LoginWindow()
        login_win.show()

        def on_login(username: str):
            """Called after successful login — create manager for this user."""
            login_win.hide()
            mgr  = SessionManager(user_id=username)
            active_mgr[0] = mgr   # pipeline_loop will now call this manager
            dash = Dashboard(session_manager=mgr, user_id=username)
            mgr.dashboard = dash
            # Propagate user_id to all user-scoped screens
            dash.screen_reports.set_user(username)
            dash.screen_analytics.set_user(username)
            dash._current_user_id = username
            if hasattr(dash, 'screen_profile'):
                dash.screen_profile.set_user(username)
            if hasattr(dash, '_header_user_lbl'):
                dash._header_user_lbl.setText(f"Signed in as {username}")
            # Propagate personal threshold to LiveScreen personal gauge
            personal_threshold = (mgr.profile.get('baseline', {})
                                  .get('personal_vfq_threshold'))
            if personal_threshold and hasattr(dash, 'screen_live'):
                try:
                    dash.screen_live.set_personal_threshold(personal_threshold)
                except Exception:
                    pass

            def on_start():
                if not mgr.current_session:
                    mgr.start_session()

            def on_stop():
                if mgr.current_session:
                    mgr.end_session()

            def on_logout():
                """Logout — stop session, return to profile selection screen."""
                if mgr.current_session:
                    mgr.end_session()
                active_mgr[0] = None   # stop pipeline from calling old manager
                dash.hide()
                # Refresh profiles and go to profile selection (index 1)
                try:
                    login_win._prof_screen.refresh()
                except Exception:
                    pass
                login_win._stack.setCurrentIndex(1)
                login_win.show()
                login_win.raise_()
                login_win.activateWindow()

            dash.session_start_requested.connect(on_start)
            dash.session_stop_requested.connect(on_stop)
            # Logout button lives in sidebar — connect its clicked signal
            # Wire logout — connect both the button and the signal
            try:
                dash.logout_btn.clicked.disconnect()
            except Exception:
                pass
            if hasattr(dash, 'logout_btn'):
                dash.logout_btn.clicked.connect(on_logout)
            # Also connect logout_requested signal (emitted by _on_logout in main.py)
            try:
                dash.logout_requested.connect(on_logout)
            except Exception:
                pass
            dash.show()

        login_win.login_complete.connect(on_login)

        pipeline_running = threading.Event()
        pipeline_running.set()

        # Use a list so pipeline_loop always references the current manager
        active_mgr = [None]   # set to mgr inside on_login

        _extractor_wired = [False]

        def pipeline_loop():
            print("\nPipeline running.")
            while pipeline_running.is_set():
                try:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    frame, features = pipeline.process_frame(frame)
                    # Wire behavioral extractor once after first frame
                    if not _extractor_wired[0]:
                        current = active_mgr[0]
                        if current is not None:
                            extractor = (
                                getattr(pipeline, 'behavioral', None) or
                                getattr(pipeline, 'behavioral_extractor', None) or
                                getattr(pipeline, 'behavior', None)
                            )
                            if extractor is not None:
                                current.reward_system.set_behavioral_extractor(
                                    extractor)
                                _extractor_wired[0] = True
                                print("[SessionManager] Behavioral extractor "
                                      "wired to RewardSystem")
                    current = active_mgr[0]
                    if current is not None and current.current_session is not None:
                        current.update_session(features)
                except RuntimeError as e:
                    if "shutdown" in str(e).lower():
                        break
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

        def on_app_quit():
            pipeline_running.clear()
            mgr = active_mgr[0]
            active_mgr[0] = None
            if mgr is not None and mgr.current_session:
                mgr.end_session()

        qt_app.aboutToQuit.connect(on_app_quit)
        sys.exit(qt_app.exec())

    else:
        print(f"\nStarting session for {user_id}. Press Q to end.")
        manager.start_session()
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frame, features = pipeline.process_frame(frame)
                result          = manager.update_session(features)
                if result:
                    vfq, level = result
                    color_map  = {
                        "NORMAL": (0,255,0), "LOW": (0,255,128),
                        "MODERATE": (0,165,255), "HIGH": (0,0,255),
                        "SEVERE": (0,0,180)
                    }
                    cv2.putText(frame, f"VFQ: {vfq:.1f} — {level}",
                                (20,40), cv2.FONT_HERSHEY_SIMPLEX,
                                0.9, color_map.get(level,(255,255,255)), 2)
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