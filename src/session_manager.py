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
        self.user_id     = user_id
        self.profile_dir = profile_dir
        self.profile_path = os.path.join(profile_dir, f"{user_id}_profile.json")

        os.makedirs(profile_dir, exist_ok=True)

        # Load or create user profile
        self.profile = self._load_profile()
        self.current_session = None
        self.logger = None
        self.vfq_calculator = VFQCalculator(user_id=user_id)
        self.vfq_history = []
        self.break_reminder = BreakReminderSystem()
        self.strain_tracker = StrainTracker()
    def _load_profile(self):
        if os.path.exists(self.profile_path):
            with open(self.profile_path, "r") as f:
                return json.load(f)
        else:
            # First time user — create fresh profile
            profile = {
                "user_id":          self.user_id,
                "created_at":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_sessions":   0,
                "total_duration":   0,
                "baseline_ear":     None,
                "baseline_blink":   None,
                "last_session":     None,
                "sessions":         []
            }
            self._save_profile(profile)
            print(f"New user profile created for {self.user_id}")
            return profile

    def _save_profile(self, profile=None):
        if profile is None:
            profile = self.profile
        with open(self.profile_path, "w") as f:
            json.dump(profile, f, indent=2)

    def start_session(self):
        self.current_session = {
            "session_id":   None,
            "start_time":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "end_time":     None,
            "duration":     0,
            "total_blinks": 0,
            "avg_ear":      [],
            "avg_blink_rate": [],
            "strain_events":  0
        }
        self.break_reminder = BreakReminderSystem()
        self.break_reminder.start()
        self.logger = DataLogger(
            user_id=self.user_id,
            data_dir="../data"
        )
        self.current_session["session_id"] = self.logger.session_id

        self.profile["total_sessions"] += 1
        print(f"Session {self.logger.session_id} started.")
        print(f"Total sessions so far: {self.profile['total_sessions']}")
        return self.logger
        
    def update_session(self, features):
        if self.current_session is None:
            return

    # Compute VFQ score
        vfq, components = self.vfq_calculator.compute(features)
        level, color    = self.vfq_calculator.get_strain_level(vfq)

    # Add VFQ to features before logging
        features["vfq_score"]    = vfq
        features["strain_label"] = level

    # Track VFQ history
        self.vfq_history.append(vfq)
        self.break_reminder.update(vfq)
        self.strain_tracker.update(vfq)
        trend = self.strain_tracker.get_trend()
        features["strain_trend"] = trend  # adds trend to CSV too
    # Log to CSV
        self.logger.log(features)

    # Track running stats
        if features.get("ear") is not None:
            self.current_session["avg_ear"].append(features["ear"])
        if features.get("blink_rate") is not None:
            self.current_session["avg_blink_rate"].append(
            features["blink_rate"])
        if features.get("blink_count") is not None:
            self.current_session["total_blinks"] = features["blink_count"]

        return vfq, level
    def end_session(self, features=None):
        if self.current_session is None:
            return

        end_time = datetime.now()
        self.current_session["end_time"] = end_time.strftime("%Y-%m-%d %H:%M:%S")

        # Calculate session duration
        duration = self.logger.get_row_count()
        self.current_session["duration"] = duration

        # Calculate averages
        if self.current_session["avg_ear"]:
            valid_ear = [e for e in self.current_session["avg_ear"] 
                if e is not None and e != float('inf') and e == e]  # filters inf and NaN
            self.current_session["avg_ear"] = round(
                sum(valid_ear) / len(valid_ear), 3) if valid_ear else None
        else:
            self.current_session["avg_ear"] = None

        if self.current_session["avg_blink_rate"]:
            self.current_session["avg_blink_rate"] = round(
                sum(self.current_session["avg_blink_rate"]) /
                len(self.current_session["avg_blink_rate"]), 1)
        else:
            self.current_session["avg_blink_rate"] = None

        # Update profile
        self.profile["total_duration"]  += duration
        self.profile["last_session"]     = self.current_session["end_time"]
        self.profile["sessions"].append({
            "session_id":  self.current_session["session_id"],
            "date":        self.current_session["start_time"],
            "duration":    duration,
            "avg_ear":     self.current_session["avg_ear"],
            "avg_blink":   self.current_session["avg_blink_rate"],
            "blinks":      self.current_session["total_blinks"]
        })
        # Add VFQ summary to session record
        if self.vfq_history:
            self.current_session["avg_vfq"] = round(sum(self.vfq_history) / len(self.vfq_history), 1)
            self.current_session["max_vfq"] = round(max(self.vfq_history), 1)
        else:
            self.current_session["avg_vfq"] = 0
            self.current_session["max_vfq"] = 0
        
        summary = self.strain_tracker.get_session_summary()
        self.current_session["high_strain_pct"] = summary.get("high_strain_pct", 0)
        self._save_profile()
        print(f"\nSession ended.")
        print(f"Duration:      {duration} seconds")
        print(f"Total blinks:  {self.current_session['total_blinks']}")
        print(f"Avg EAR:       {self.current_session['avg_ear']}")
        print(f"Avg blink rate:{self.current_session['avg_blink_rate']}/min")
        print(f"Profile saved: {self.profile_path}")
        print(f"Avg VFQ:       {self.current_session['avg_vfq']}")
        print(f"Max VFQ:       {self.current_session['max_vfq']}")
        print(f"High Strain %: {self.current_session['high_strain_pct']}%")  # ADD HERE

        self.current_session = None
        self.break_reminder.stop()


    def get_profile_summary(self):
        return {
            "user_id":        self.profile["user_id"],
            "total_sessions": self.profile["total_sessions"],
            "total_duration": self.profile["total_duration"],
            "last_session":   self.profile["last_session"]
        }


# ── Test run ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import cv2
    from pipeline import UnifiedPipeline

    manager  = SessionManager(user_id="user_001")
    pipeline = UnifiedPipeline()
    cap      = cv2.VideoCapture(0)

    print("\nStarting session. Press Q to end.")
    print(f"Profile summary: {manager.get_profile_summary()}\n")

    manager.start_session()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame, features = pipeline.process_frame(frame)
            result = manager.update_session(features)

            if result:
                vfq, level = result
                color_map = {
                    "NORMAL":   (0, 255, 0),
                    "LOW":      (0, 255, 128),
                    "MODERATE": (0, 165, 255),
                    "HIGH":     (0, 0, 255),
                    "SEVERE":   (0, 0, 180)
                }
                color = color_map.get(level, (255, 255, 255))

                cv2.putText(frame,
                            f"VFQ: {vfq:.1f} — {level}",
                            (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                            0.9, color, 2)
                cv2.putText(frame,
                            f"Session {manager.profile['total_sessions']} | "
                            f"Rows: {manager.logger.get_row_count()}",
                            (20, 75), cv2.FONT_HERSHEY_SIMPLEX,
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