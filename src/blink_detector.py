import cv2
import mediapipe as mp
import numpy as np
import time

BaseOptions = mp.tasks.BaseOptions
FaceLandmarker = mp.tasks.vision.FaceLandmarker
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]

EAR_THRESHOLD = 0.20      # Below this = eye closing
CONSEC_FRAMES = 2         # Must be below threshold for 2 frames to count as blink

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

model_path = "face_landmarker.task"
options = FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=model_path),
    running_mode=VisionRunningMode.IMAGE,
    num_faces=1
)

cap = cv2.VideoCapture(0)
print("Blink detection running. Press Q to quit.")

# Blink tracking variables
blink_count = 0
frame_counter = 0         # Counts consecutive frames below threshold
blink_times = []          # Stores timestamp of each blink

start_time = time.time()

with FaceLandmarker.create_from_options(options) as landmarker:
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        h, w = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = landmarker.detect(mp_image)

        if result.face_landmarks:
            landmarks = result.face_landmarks[0]

            left_ear, left_points = compute_ear(landmarks, LEFT_EYE, w, h)
            right_ear, right_points = compute_ear(landmarks, RIGHT_EYE, w, h)
            avg_ear = (left_ear + right_ear) / 2.0

            # Blink detection logic
            if avg_ear < EAR_THRESHOLD:
                frame_counter += 1
            else:
                if frame_counter >= CONSEC_FRAMES:
                    blink_count += 1
                    blink_times.append(time.time())
                frame_counter = 0

            # Calculate blink rate (blinks per minute)
            # Only count blinks in the last 60 seconds
            current_time = time.time()
            blink_times = [t for t in blink_times if current_time - t <= 60]
            blink_rate = len(blink_times)

            # Elapsed time
            elapsed = int(current_time - start_time)
            minutes = elapsed // 60
            seconds = elapsed % 60

            # Draw eye points
            for pt in left_points:
                cv2.circle(frame, pt, 3, (0, 255, 0), -1)
            for pt in right_points:
                cv2.circle(frame, pt, 3, (255, 0, 0), -1)

            # Display info
            cv2.putText(frame, f"Avg EAR: {avg_ear:.3f}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            cv2.putText(frame, f"Blink Count: {blink_count}", (20, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"Blink Rate: {blink_rate}/min", (20, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(frame, f"Time: {minutes:02d}:{seconds:02d}", (20, 130),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            # Warning if blink rate is low
            if blink_rate < 12 and elapsed > 60:
                cv2.putText(frame, "LOW BLINK RATE - Eye Strain Risk!", (20, 170),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        cv2.imshow("Blink Detector", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cap.release()
cv2.destroyAllWindows()
print(f"Session ended. Total blinks: {blink_count}")