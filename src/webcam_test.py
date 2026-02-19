import cv2
import mediapipe as mp

BaseOptions = mp.tasks.BaseOptions
FaceLandmarker = mp.tasks.vision.FaceLandmarker
FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

import urllib.request
import os

# Download the face landmark model if not already downloaded
model_path = "face_landmarker.task"
if not os.path.exists(model_path):
    print("Downloading face landmark model...")
    url = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
    urllib.request.urlretrieve(url, model_path)
    print("Download complete.")

options = FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=model_path),
    running_mode=VisionRunningMode.IMAGE,
    num_faces=1
)

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("ERROR: Cannot open webcam")
    exit()

print("Face detection running. Press Q to quit.")

with FaceLandmarker.create_from_options(options) as landmarker:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("ERROR: Cannot read frame")
            break

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = landmarker.detect(mp_image)

        if result.face_landmarks:
            cv2.putText(frame, f"Face Detected - {len(result.face_landmarks[0])} landmarks",
                        (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            # Draw landmarks as dots
            h, w = frame.shape[:2]
            for landmark in result.face_landmarks[0]:
                x = int(landmark.x * w)
                y = int(landmark.y * h)
                cv2.circle(frame, (x, y), 1, (0, 255, 0), -1)
        else:
            cv2.putText(frame, "No Face Detected", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        cv2.imshow("EyeStrain - Face Mesh", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cap.release()
cv2.destroyAllWindows()
print("Done.")