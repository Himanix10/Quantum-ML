import cv2
import mediapipe as mp
import os

BaseOptions = mp.tasks.BaseOptions
FaceLandmarker = mp.tasks.vision.FaceLandmarker
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

# Eye landmark indices for MediaPipe 478-point model
# Left eye
LEFT_EYE = [362, 385, 387, 263, 373, 380]
# Right eye
RIGHT_EYE = [33, 160, 158, 133, 153, 144]

model_path = "face_landmarker.task"
options = FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=model_path),
    running_mode=VisionRunningMode.IMAGE,
    num_faces=1
)

cap = cv2.VideoCapture(0)
print("Eye landmark detection running. Press Q to quit.")

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

            # Draw LEFT eye landmarks in GREEN
            for idx in LEFT_EYE:
                x = int(landmarks[idx].x * w)
                y = int(landmarks[idx].y * h)
                cv2.circle(frame, (x, y), 3, (0, 255, 0), -1)

            # Draw RIGHT eye landmarks in BLUE
            for idx in RIGHT_EYE:
                x = int(landmarks[idx].x * w)
                y = int(landmarks[idx].y * h)
                cv2.circle(frame, (x, y), 3, (255, 0, 0), -1)

            cv2.putText(frame, "Left Eye: GREEN | Right Eye: BLUE",
                        (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        cv2.imshow("Eye Landmarks", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cap.release()
cv2.destroyAllWindows()