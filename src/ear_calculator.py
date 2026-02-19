import cv2
import mediapipe as mp
import numpy as np
import os

BaseOptions = mp.tasks.BaseOptions
FaceLandmarker = mp.tasks.vision.FaceLandmarker
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]

def compute_ear(landmarks, eye_indices, w, h):
    # Get the 6 eye points as pixel coordinates
    points = []
    for idx in eye_indices:
        x = int(landmarks[idx].x * w)
        y = int(landmarks[idx].y * h)
        points.append((x, y))

    # EAR formula:
    # Vertical distances (p2-p6 and p3-p5)
    A = np.linalg.norm(np.array(points[1]) - np.array(points[5]))
    B = np.linalg.norm(np.array(points[2]) - np.array(points[4]))
    # Horizontal distance (p1-p4)
    C = np.linalg.norm(np.array(points[0]) - np.array(points[3]))

    # EAR calculation
    ear = (A + B) / (2.0 * C)
    return ear, points

model_path = "face_landmarker.task"
options = FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=model_path),
    running_mode=VisionRunningMode.IMAGE,
    num_faces=1
)

cap = cv2.VideoCapture(0)
print("EAR calculation running. Press Q to quit.")
print("Normal open eye EAR: 0.25 - 0.35")
print("Blink EAR: below 0.20")

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

            # Draw eye points
            for pt in left_points:
                cv2.circle(frame, pt, 3, (0, 255, 0), -1)
            for pt in right_points:
                cv2.circle(frame, pt, 3, (255, 0, 0), -1)

            # Display EAR values
            cv2.putText(frame, f"Left EAR:  {left_ear:.3f}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"Right EAR: {right_ear:.3f}", (20, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
            cv2.putText(frame, f"Avg EAR:   {avg_ear:.3f}", (20, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

            # Warn if eyes closing
            if avg_ear < 0.20:
                cv2.putText(frame, "BLINK DETECTED", (20, 140),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

        cv2.imshow("EAR Calculator", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cap.release()
cv2.destroyAllWindows()