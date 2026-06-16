import csv
import os
import time
import uuid
from datetime import datetime


class DataLogger:
    def __init__(self, user_id="user_001", data_dir="../data"):
        self.user_id  = user_id
        self.data_dir = data_dir
        self.session_id = str(uuid.uuid4())[:8]

        # Create data directory if not exists
        os.makedirs(data_dir, exist_ok=True)

        # ── Session CSV filename ─────────────────────────────────────────────
        # Always uses {user_id}_session_{timestamp}.csv regardless of path.
        # This ensures personalization.py glob pattern finds the files.
        timestamp     = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filepath = os.path.join(
            data_dir, f"{user_id}_session_{timestamp}.csv"
        )

        # Define columns
        self.columns = [
            "timestamp",
            "session_id",
            "user_id",
            "session_duration",
            "ear",
            "blink_count",
            "blink_rate",
            "gaze_x",
            "gaze_y",
            "gaze_deviation",
            "head_pitch",
            "head_yaw",
            "head_roll",
            "face_detected",
            "luminance",
            "light_variance",
            "glare_detected",
            "keystrokes_per_min",
            "backspace_per_min",
            "mouse_dist_per_min",
            "clicks_per_min",
            "vfq_score",
            "strain_label",
            "strain_trend"
        ]

        # Write header
        with open(self.filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.columns)
            writer.writeheader()

        self.last_log_time = time.time()
        self.row_count     = 0
        print(f"Logging to: {self.filepath}")

    def log(self, features):
        # Only log once per second
        now = time.time()
        if now - self.last_log_time < 1.0:
            return

        self.last_log_time = now

        row = {
            "timestamp":          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "session_id":         self.session_id,
            "user_id":            self.user_id,
            "session_duration":   features.get("session_duration", 0),
            "ear":                features.get("ear", ""),
            "blink_count":        features.get("blink_count", ""),
            "blink_rate":         features.get("blink_rate", ""),
            "gaze_x":             features.get("gaze_x", ""),
            "gaze_y":             features.get("gaze_y", ""),
            "gaze_deviation":     features.get("gaze_deviation", ""),
            "head_pitch":         features.get("head_pitch", ""),
            "head_yaw":           features.get("head_yaw", ""),
            "head_roll":          features.get("head_roll", ""),
            "face_detected":      features.get("face_detected", ""),
            "luminance":          features.get("luminance", ""),
            "light_variance":     features.get("light_variance", ""),
            "glare_detected":     features.get("glare_detected", ""),
            "keystrokes_per_min": features.get("keystrokes_per_min", ""),
            "backspace_per_min":  features.get("backspace_per_min", ""),
            "mouse_dist_per_min": features.get("mouse_dist_per_min", ""),
            "clicks_per_min":     features.get("clicks_per_min", ""),
            "vfq_score":          features.get("vfq_score", ""),
            "strain_label":       features.get("strain_label", ""),
            "strain_trend":       features.get("strain_trend", "")
        }

        with open(self.filepath, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.columns)
            writer.writerow(row)

        self.row_count += 1

        if self.row_count % 10 == 0:
            print(f"Logged {self.row_count} rows → {self.filepath}")

    def get_row_count(self):
        return self.row_count

    def get_filepath(self):
        return self.filepath


# ── Test run ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import cv2
    from pipeline import UnifiedPipeline

    pipeline = UnifiedPipeline()
    logger   = DataLogger(user_id="user_001")
    cap      = cv2.VideoCapture(0)

    print("Data logger running. Press Q to quit.")
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame, features = pipeline.process_frame(frame)
        logger.log(features)
        cv2.putText(frame, f"Logged: {logger.get_row_count()} rows",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow("Data Logger", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    pipeline.stop(); cap.release(); cv2.destroyAllWindows()
    print(f"\nFile saved: {logger.get_filepath()}")