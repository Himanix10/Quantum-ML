import cv2
import numpy as np
from collections import deque


class EnvironmentFeatureExtractor:
    def __init__(self, variance_window=30):
        # Store last 30 luminance values to compute variance
        self.luminance_buffer = deque(maxlen=variance_window)

    def process_frame(self, frame):
        features = {
            "luminance":      None,
            "light_variance": None,
            "glare_detected": False
        }

        # ── Luminance ─────────────────────────────────────────────
        # Convert frame to grayscale and take mean pixel brightness
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        luminance = float(np.mean(gray))
        features["luminance"] = round(luminance, 2)

        # ── Light variance (flicker detection) ────────────────────
        self.luminance_buffer.append(luminance)
        if len(self.luminance_buffer) >= 10:
            variance = float(np.var(self.luminance_buffer))
            features["light_variance"] = round(variance, 2)

            # High variance = flickering light = eye strain risk
            if variance > 50:
                features["glare_detected"] = True

        return features

    def draw_on_frame(self, frame, features):
        lum  = features["luminance"]
        var  = features["light_variance"]
        glare= features["glare_detected"]

        # Luminance color coding
        if lum is not None:
            if lum < 50:
                lum_color = (0, 0, 255)    # Red = too dark
                lum_label = "TOO DARK"
            elif lum > 200:
                lum_color = (0, 165, 255)  # Orange = too bright
                lum_label = "TOO BRIGHT"
            else:
                lum_color = (0, 255, 0)    # Green = good
                lum_label = "GOOD"

            cv2.putText(frame, f"Luminance: {lum:.1f} ({lum_label})",
                        (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, lum_color, 2)

        if var is not None:
            cv2.putText(frame, f"Light Variance: {var:.2f}",
                        (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        if glare:
            cv2.putText(frame, "FLICKERING LIGHT DETECTED - Eye Strain Risk!",
                        (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        return frame


# ── Test run ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import cv2
    extractor = EnvironmentFeatureExtractor()
    cap = cv2.VideoCapture(0)
    print("Environment Feature Extractor running. Press Q to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        features = extractor.process_frame(frame)
        frame    = extractor.draw_on_frame(frame, features)

        cv2.imshow("Environment Features", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("Final features:", features)