import os
import cv2
import time
from eye_features      import EyeFeatureExtractor
from env_features      import EnvironmentFeatureExtractor
from behavioral_features import BehavioralFeatureExtractor


class UnifiedPipeline:
    def __init__(self, model_path=None):
        if model_path is None:
            model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'face_landmarker.task')
        print("Initializing pipeline...")
        self.eye_extractor  = EyeFeatureExtractor(model_path=model_path)
        self.env_extractor  = EnvironmentFeatureExtractor()
        self.beh_extractor  = BehavioralFeatureExtractor()
        self.start_time     = time.time()
        print("Pipeline ready.")

    def process_frame(self, frame):
        # Run all three extractors
        frame, eye_features = self.eye_extractor.process_frame(frame)
        env_features        = self.env_extractor.process_frame(frame)
        beh_features        = self.beh_extractor.get_features()

        # Merge into one unified features dictionary
        features = {}
        features.update(eye_features)
        features.update(env_features)
        features.update(beh_features)
        features["session_duration"] = round(time.time() - self.start_time, 1)

        return frame, features

    def draw_env_on_frame(self, frame, features):
        frame = self.env_extractor.draw_on_frame(frame, features)
        return frame

    def stop(self):
        self.beh_extractor.stop()
        print("Pipeline stopped.")


# ── Test run ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    pipeline = UnifiedPipeline()
    cap      = cv2.VideoCapture(0)
    print("Unified pipeline running. Press Q to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame, features = pipeline.process_frame(frame)
        frame           = pipeline.draw_env_on_frame(frame, features)

        # Print features to terminal every 5 seconds
        if int(features["session_duration"]) % 5 == 0:
            print("\n── Features ──────────────────────────────")
            for key, val in features.items():
                print(f"  {key:25s}: {val}")

        cv2.imshow("Unified Pipeline", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    pipeline.stop()
    cap.release()
    cv2.destroyAllWindows()