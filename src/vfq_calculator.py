import json
import numpy as np
import os


class VFQCalculator:
    def __init__(self, user_id="user_001",
                 profile_dir="../data/profiles"):
        self.user_id = user_id
        self.profile_path = os.path.join(
            profile_dir, f"{user_id}_profile.json")
        self.baseline = self._load_baseline()

    def _load_baseline(self):
        if not os.path.exists(self.profile_path):
            print("No baseline found. Using generic thresholds.")
            return None
        with open(self.profile_path, "r") as f:
            profile = json.load(f)
        return profile.get("baseline", None)

    def _normalize(self, value, mean, std, direction="high"):
        """
        Normalize a value to 0-1 strain score.
        direction='high'  means high value = more strain (e.g. gaze deviation)
        direction='low'   means low value  = more strain (e.g. EAR, blink rate)
        """
        if std == 0:
            return 0.0
        z = (value - mean) / std
        if direction == "high":
    # Positive z = above normal = more strain
            score = max(0.0, min(1.0, z / 1.5))
        else:
    # Negative z = below normal = more strain
            score = max(0.0, min(1.0, -z / 1.5))
        return score

    def compute(self, features):
        """
        Compute VFQ score from current features.
        Returns score 0-100 and component breakdown.
        """
        components = {}

        if self.baseline:
            # ── Personalized scoring ──────────────────────────────

            # EAR component (low EAR = strain)
            ear = features.get("ear")
            if ear is not None and self.baseline.get("ear_mean"):
                components["ear"] = self._normalize(
                    ear,
                    self.baseline["ear_mean"],
                    self.baseline["ear_std"],
                    direction="low"
                )

            # Blink rate component (low blink = strain)
            blink = features.get("blink_rate")
            if blink is not None and self.baseline.get("blink_mean"):
                components["blink"] = self._normalize(
                    blink,
                    self.baseline["blink_mean"],
                    self.baseline["blink_std"],
                    direction="low"
                )

            # Gaze deviation component (high gaze = strain)
            gaze = features.get("gaze_deviation")
            if gaze is not None and self.baseline.get("gaze_mean"):
                components["gaze"] = self._normalize(
                    gaze,
                    self.baseline["gaze_mean"],
                    self.baseline["gaze_std"],
                    direction="high"
                )

            # Head pitch component (high pitch = strain)
            pitch = features.get("head_pitch")
            if pitch is not None and self.baseline.get("pitch_mean"):
                components["pitch"] = self._normalize(
                    abs(pitch),
                    self.baseline["pitch_mean"],
                    self.baseline["pitch_std"],
                    direction="high"
                )

            # Luminance component (too dark or too bright = strain)
            lum = features.get("luminance")
            if lum is not None and self.baseline.get("lum_mean"):
                lum_deviation = abs(lum - self.baseline["lum_mean"])
                components["luminance"] = self._normalize(
                    lum_deviation,
                    0,
                    max(self.baseline["lum_std"], 1),
                    direction="high"
                )

            # Keystroke component (very high or very low = strain)
            keys = features.get("keystrokes_per_min")
            if keys is not None and self.baseline.get("keys_mean"):
                keys_deviation = abs(keys - self.baseline["keys_mean"])
                components["keystrokes"] = self._normalize(
                    keys_deviation,
                    0,
                    max(self.baseline["keys_std"], 1),
                    direction="high"
                )

        else:
            # ── Generic fallback scoring ──────────────────────────
            ear = features.get("ear")
            if ear is not None:
                components["ear"] = max(0.0, min(1.0,
                    (0.25 - ear) / 0.10)) if ear < 0.25 else 0.0

            blink = features.get("blink_rate")
            if blink is not None:
                components["blink"] = max(0.0, min(1.0,
                    (12 - blink) / 12.0)) if blink < 12 else 0.0

            gaze = features.get("gaze_deviation")
            if gaze is not None:
                components["gaze"] = max(0.0, min(1.0, gaze / 5.0))

            pitch = features.get("head_pitch")
            if pitch is not None:
                components["pitch"] = max(0.0, min(1.0,
                    abs(pitch) / 15.0))

            lum = features.get("luminance")
            if lum is not None:
                dev = abs(lum - 128) / 128.0
                components["luminance"] = max(0.0, min(1.0, dev))

        # ── Weighted combination ──────────────────────────────────
        # Weights reflect clinical importance of each signal
        weights = {
    "ear":        0.35,
    "blink":      0.30,
    "gaze":       0.20,
    "pitch":      0.10,
    "luminance":  0.03,
    "keystrokes": 0.02
}

        total_weight = 0.0
        weighted_sum = 0.0
        for key, score in components.items():
            w = weights.get(key, 0.0)
            weighted_sum += score * w
            total_weight  += w

        if total_weight == 0:
            vfq = 0.0
        else:
            vfq = (weighted_sum / total_weight) * 100

        vfq = round(vfq, 1)

        return vfq, components

    def get_strain_level(self, vfq):
        """Convert VFQ score to human readable strain level."""
        if vfq < 20:
            return "NORMAL",   (0, 255, 0)      # Green
        elif vfq < 40:
            return "LOW",      (0, 255, 128)     # Light green
        elif vfq < 60:
            return "MODERATE", (0, 165, 255)     # Orange
        elif vfq < 80:
            return "HIGH",     (0, 0, 255)       # Red
        else:
            return "SEVERE",   (0, 0, 180)       # Dark red


# ── Test run ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import cv2
    from pipeline import UnifiedPipeline

    calculator = VFQCalculator(user_id="user_001")
    pipeline   = UnifiedPipeline()
    cap        = cv2.VideoCapture(0)

    print("VFQ Calculator running. Press Q to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame, features = pipeline.process_frame(frame)
        vfq, components = calculator.compute(features)
        level, color    = calculator.get_strain_level(vfq)

        # Display VFQ on frame
        cv2.putText(frame, f"VFQ: {vfq:.1f} - {level}",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX,
                    0.9, color, 2)

        # Display components
        y = 80
        for key, val in components.items():
            cv2.putText(frame,
                        f"{key}: {val:.2f}",
                        (20, y), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (200, 200, 200), 1)
            y += 25

        cv2.imshow("VFQ Calculator", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    pipeline.stop()
    cap.release()
    cv2.destroyAllWindows()