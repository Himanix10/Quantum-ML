import os
import json
import time
from datetime import datetime
from data_logger import DataLogger
from vfq_calculator import VFQCalculator
from break_reminder import BreakReminderSystem
from strain_tracker import StrainTracker


class SessionManager:
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

        self.logger = DataLogger(user_id=self.user_id, data_dir="../data")
        self.current_session["session_id"] = self.logger.session_id

        self.profile["total_sessions"] += 1
        print(f"Session {self.logger.session_id} started.")
        print(f"Total sessions so far: {self.profile['total_sessions']}")
        return self.logger

    def update_session(self, features):
        # Send to dashboard if wired
        if self.dashboard is not None:
            try:
                self.dashboard.update_from_pipeline(features)
            except Exception:
                pass

        if self.current_session is None:
            return None

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

        # Log
        self.logger.log(features)

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

    # ── Check if dashboard mode requested ──
    use_dashboard = "--dashboard" in sys.argv

    manager  = SessionManager(user_id="user_001")
    pipeline = UnifiedPipeline()
    cap      = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("ERROR: Could not open webcam.")
        exit(1)

    # ── Start dashboard if requested ──
    if use_dashboard:
        import threading
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from PyQt6.QtWidgets import QApplication
        from dashboard.main import Dashboard

        qt_app  = QApplication(sys.argv)
        dash    = Dashboard(session_manager=manager)
        manager.dashboard = dash
        dash.show()
        # Wire dashboard Start/Stop buttons to pipeline
        def on_start_requested():
            if not manager.current_session:
                manager.start_session()

        def on_stop_requested():
            if manager.current_session:
                manager.end_session()

        dash.session_start_requested.connect(on_start_requested)
        dash.session_stop_requested.connect(on_stop_requested)

        # Run pipeline in background thread
        def pipeline_loop():
            print("\nStarting session. Press Q in webcam window to end.")
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

            except Exception as e:
                print(f"Pipeline error: {e}")
            finally:
                manager.end_session()
                pipeline.stop()
                cap.release()
                cv2.destroyAllWindows()
                qt_app.quit()

        thread = threading.Thread(target=pipeline_loop, daemon=True)
        thread.start()
        sys.exit(qt_app.exec())

    # ── Standalone mode (no dashboard) ──
    else:
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