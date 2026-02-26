import cv2
import mediapipe as mp
import numpy as np
import time

BaseOptions = mp.tasks.BaseOptions
FaceLandmarker = mp.tasks.vision.FaceLandmarker
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

# Eye landmark indices
LEFT_EYE  = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33,  160, 158, 133, 153, 144]

# Iris indices (center of each eye)
LEFT_IRIS  = [474, 475, 476, 477]
RIGHT_IRIS = [469, 470, 471, 472]

EAR_THRESHOLD = 0.20
CONSEC_FRAMES = 2

def compute_ear(landmarks, eye_indices, w, h):
    points = []
    for idx in eye_indices:
        x = int(landmarks[idx].x * w)
        y = int(landmarks[idx].y * h)
        points.append((x, y))
    A = np.linalg.norm(np.array(points[1]) - np.array(points[5]))
    B = np.linalg.norm(np.array(points[2]) - np.array(points[4]))
    C = np.linalg.norm(np.array(points[0]) - np.array(points[3]))
    ear = (A + B) / (2.0 * C)
    return ear, points

def compute_gaze(landmarks, w, h):
    left_iris_pts = [(int(landmarks[i].x * w), int(landmarks[i].y * h))
                     for i in LEFT_IRIS]
    left_iris_center = np.mean(left_iris_pts, axis=0)

    right_iris_pts = [(int(landmarks[i].x * w), int(landmarks[i].y * h))
                      for i in RIGHT_IRIS]
    right_iris_center = np.mean(right_iris_pts, axis=0)

    left_eye_left  = np.array([int(landmarks[362].x * w), int(landmarks[362].y * h)])
    left_eye_right = np.array([int(landmarks[263].x * w), int(landmarks[263].y * h)])
    left_eye_center = (left_eye_left + left_eye_right) / 2

    right_eye_left  = np.array([int(landmarks[33].x * w), int(landmarks[33].y * h)])
    right_eye_right = np.array([int(landmarks[133].x * w), int(landmarks[133].y * h)])
    right_eye_center = (right_eye_left + right_eye_right) / 2

    left_gaze  = left_iris_center  - left_eye_center
    right_gaze = right_iris_center - right_eye_center

    avg_gaze_x = (left_gaze[0] + right_gaze[0]) / 2
    avg_gaze_y = (left_gaze[1] + right_gaze[1]) / 2

    return avg_gaze_x, avg_gaze_y, left_iris_center, right_iris_center

def compute_gaze_deviation(gaze_x, gaze_y):
    deviation = np.sqrt(gaze_x**2 + gaze_y**2)
    normalized = min(deviation / 15.0 * 10, 10)
    return round(normalized, 2)


class EyeFeatureExtractor:
    def __init__(self, model_path="face_landmarker.task"):
        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=VisionRunningMode.IMAGE,
            num_faces=1
        )
        self.landmarker = FaceLandmarker.create_from_options(options)
        self.blink_count = 0
        self.frame_counter = 0
        self.blink_times = []
        self.start_time = time.time()
        self.gaze_x_buffer = []
        self.gaze_y_buffer = []

    def process_frame(self, frame):
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect(mp_image)

        features = {
            "ear": None,
            "blink_count": self.blink_count,
            "blink_rate": 0,
            "gaze_x": None,
            "gaze_y": None,
            "gaze_deviation": None,
            "face_detected": False
        }

        if result.face_landmarks:
            landmarks = result.face_landmarks[0]
            features["face_detected"] = True

            # EAR
            left_ear,  left_pts  = compute_ear(landmarks, LEFT_EYE,  w, h)
            right_ear, right_pts = compute_ear(landmarks, RIGHT_EYE, w, h)
            avg_ear = (left_ear + right_ear) / 2.0
            features["ear"] = avg_ear

            # Blink detection
            if avg_ear < EAR_THRESHOLD:
                self.frame_counter += 1
            else:
                if self.frame_counter >= CONSEC_FRAMES:
                    self.blink_count += 1
                    self.blink_times.append(time.time())
                self.frame_counter = 0

            # Blink rate (rolling 60 seconds)
            now = time.time()
            self.blink_times = [t for t in self.blink_times if now - t <= 60]
            features["blink_count"] = self.blink_count
            features["blink_rate"]  = len(self.blink_times)

            # Gaze
            gaze_x, gaze_y, l_iris, r_iris = compute_gaze(landmarks, w, h)

            # Smooth gaze using rolling average of last 10 frames
            self.gaze_x_buffer.append(gaze_x)
            self.gaze_y_buffer.append(gaze_y)
            if len(self.gaze_x_buffer) > 10:
                self.gaze_x_buffer.pop(0)
                self.gaze_y_buffer.pop(0)
            smooth_gaze_x = np.mean(self.gaze_x_buffer)
            smooth_gaze_y = np.mean(self.gaze_y_buffer)
            features["gaze_x"] = smooth_gaze_x
            features["gaze_y"] = smooth_gaze_y
            features["gaze_deviation"] = compute_gaze_deviation(smooth_gaze_x, smooth_gaze_y)

            # Draw on frame
            for pt in left_pts:
                cv2.circle(frame, pt, 3, (0, 255, 0), -1)
            for pt in right_pts:
                cv2.circle(frame, pt, 3, (255, 0, 0), -1)
            cv2.circle(frame, (int(l_iris[0]), int(l_iris[1])), 3, (0, 255, 255), -1)
            cv2.circle(frame, (int(r_iris[0]), int(r_iris[1])), 3, (0, 255, 255), -1)

            # Display
            dev = features["gaze_deviation"]
            cv2.putText(frame, f"EAR: {avg_ear:.3f}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            cv2.putText(frame, f"Blinks: {self.blink_count} | Rate: {features['blink_rate']}/min",
                        (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"Gaze X: {smooth_gaze_x:.1f} | Y: {smooth_gaze_y:.1f} | Dev: {dev}",
                        (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            if avg_ear < EAR_THRESHOLD:
                cv2.putText(frame, "BLINK", (20, 130),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            if features["blink_rate"] < 12 and (time.time() - self.start_time) > 60:
                cv2.putText(frame, "LOW BLINK RATE - Eye Strain Risk!", (20, 160),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        return frame, features


# ── Test run ──────────────────────────────────────────────
if __name__ == "__main__":
    extractor = EyeFeatureExtractor()
    cap = cv2.VideoCapture(0)
    print("Eye Feature Extractor running. Press Q to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame, features = extractor.process_frame(frame)
        cv2.imshow("Eye Features", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("Final features:", features)