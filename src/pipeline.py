import collections
import numpy as np
import os
import time
import cv2
import sys
from pathlib import Path
# Add project root to sys.path for absolute imports when run as a script
project_root = Path(__file__).resolve().parents[0]
sys.path.append(str(project_root))
import json
# Log directory for pipeline runs
LOG_DIR = Path(__file__).parents[2] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "full_pipeline_log.json"
try:
    from eye_features import EyeFeatureExtractor
except Exception as e:
    import warnings
    warnings.warn(f"EyeFeatureExtractor could not be imported: {e}")
    class EyeFeatureExtractor:
        def __init__(self, model_path=None):
            pass
        def process_frame(self, frame):
            # Return frame unchanged and minimal feature dict to keep pipeline functional
            features = {
                "ear": None,
                "blink_count": 0,
                "blink_rate": 0,
                "gaze_x": None,
                "gaze_y": None,
                "gaze_deviation": None,
                "head_pitch": None,
                "head_yaw": None,
                "head_roll": None,
                "face_detected": False,
            }
            return frame, features
from env_features import EnvironmentFeatureExtractor
try:
    from behavioral_features import BehavioralFeatureExtractor
except Exception as e:
    import warnings
    warnings.warn(f"BehavioralFeatureExtractor could not be imported: {e}")
    class BehavioralFeatureExtractor:
        def __init__(self):
            pass
        def get_features(self):
            return {}
        def stop(self):
            pass
from quantum_feature_fusion import QuantumFeatureFusion
from tcn_model import load_model, extract_embedding, predict_proba
from state_builder import build_state
from deep_rl_agent import DQNAgent
from qaoa_optimizer import build_qubo, run_qaoa
from decision_logic import interpret_qaoa, execute_action

class UnifiedPipeline:
    def __init__(self, model_path=None, dqn_checkpoint_path=None):
        if model_path is None:
            model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'face_landmarker.task')
        print("Initializing pipeline...")
        self.eye_extractor = EyeFeatureExtractor(model_path=model_path)
        self.env_extractor = EnvironmentFeatureExtractor()
        self.beh_extractor = BehavioralFeatureExtractor()
        self.quantum_fusion = QuantumFeatureFusion()
        self.start_time = time.time()
        # Load TCN model
        self.tcn_model, self.device = load_model()
        # Load DQN
        # dummy_state = build_state(np.zeros(128), np.zeros(5), 0., 0., 0., 0.)
        dummy_state = build_state(np.zeros(128), np.zeros(5), 0., 0., 0., 0.)
        self.state_dim = dummy_state.shape[0]
        self.dqn = DQNAgent(state_dim=self.state_dim, action_dim=3)
        checkpoint = dqn_checkpoint_path or os.path.join(os.path.dirname(__file__), '..', 'models', 'dqn_checkpoint.pth')
        if os.path.exists(checkpoint):
            self.dqn.load(checkpoint)
        else:
            import warnings
            warnings.warn(f"DQN checkpoint not found at {checkpoint}; proceeding without loading.")
            # Continue with untrained DQNAgent (randomly initialized)
        # Buffer for sliding window (60 frames)
        self.feature_buffer = collections.deque(maxlen=60)
        self.frame_counter = 0
        self.window_counter = 0
        print("Pipeline ready.")

    def process_frame(self, frame):
        # Run all three extractors
        frame, eye_features = self.eye_extractor.process_frame(frame)
        env_features = self.env_extractor.process_frame(frame)
        beh_features = self.beh_extractor.get_features()

        # Merge into one unified features dictionary
        features = {}
        features.update(eye_features)
        features.update(env_features)
        features.update(beh_features)
        features["session_duration"] = round(time.time() - self.start_time, 1)

        # Quantum feature fusion on eye-strain features.
        quantum_inputs = {
            'EAR': features.get('ear', 0.0),
            'blink_rate': features.get('blink_rate', 0.0),
            'gaze_deviation': features.get('gaze_deviation', 0.0),
            'head_pose': features.get('head_pitch', 0.0),
        }
        quantum_features = self.quantum_fusion.encode(quantum_inputs)
        features.update(quantum_features)

        # Store raw feature vector (the combined numeric features) for the window
        # Build a flat vector of the same order used in data_loader (FEATURE_COLS)
        # Assume `features` already contains all required columns in correct order.
        # We'll extract values in sorted key order for consistency.
        # Build a flat vector matching the model's expected feature columns
        from data_loader import FEATURE_COLS
        # Ensure every expected column is present; use 0.0 for missing values
        raw_vec = np.array([features.get(k, 0.0) for k in FEATURE_COLS], dtype=np.float32)
        self.feature_buffer.append(raw_vec)
        self.frame_counter += 1

        # Run RL inference every 30 frames when we have a full window
        if len(self.feature_buffer) == 60 and self.frame_counter % 30 == 0:
            self.window_counter += 1
            window = np.stack(self.feature_buffer)  # shape (60, F)
            # Get embedding and class probabilities from TCN
            pred, label, probs = predict_proba(self.tcn_model, window, self.device)  # probs list
            embedding = extract_embedding(self.tcn_model, window, self.device)
            # Build RL state vector
            state_vec = build_state(
                embedding=embedding,
                probs=np.array(probs),
                vfq=features.get('vfq', 0.0),
                time_since_break=features.get('time_since_break', 0.0),
                workload=features.get('workload', 0.0),
                session_duration=features.get('session_duration', 0.0),
            )
            # DQN proposes action
            q_vals = self.dqn.q_values(state_vec)
            chosen_idx = int(np.argmax(q_vals))
            dqn_action = ['continue', 'reminder', 'break'][chosen_idx]
            # Prepare QAOA state (requires probs and workload normalized)
            qaoa_state = {"probs": np.array(probs), "workload": features.get('workload', 0.0)}
            qp = build_qubo(qaoa_state)
            bits, energy = run_qaoa(qp, p_layers=2)
            qaoa_action = interpret_qaoa(bits)
            execute_action(qaoa_action)
            # Attach decision info to features for logging
            features["rl_action"] = qaoa_action
            features["rl_qvals"] = q_vals.tolist()
            # Additional logging fields
            features["window"] = self.window_counter
            features["prediction"] = label
            features["probabilities"] = probs
            features["q_values"] = q_vals.tolist()
            features["dqn_action"] = dqn_action
            features["qaoa_action"] = qaoa_action
            features["reward"] = 0.0  # placeholder reward
            features["vfq"] = features.get('vfq', 0.0)
            features["energy"] = energy
            
        return frame, features

    def draw_env_on_frame(self, frame, features):
        frame = self.env_extractor.draw_on_frame(frame, features)
        return frame

    def stop(self):
        self.beh_extractor.stop()
        print("Pipeline stopped.")



# ── Test run (executed via run_full_pipeline) ─────────────────────────────────────
# Early test run removed – function defined later

def run_full_pipeline():
    pipeline = UnifiedPipeline()
    cap = cv2.VideoCapture(0)
    print("Unified pipeline running. Press Q to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame, features = pipeline.process_frame(frame)
        frame = pipeline.draw_env_on_frame(frame, features)

        # Log relevant inference information
        log_entry = {
            "timestamp": time.time(),
            "session_duration": features.get("session_duration"),
            "rl_action": features.get("rl_action"),
            "rl_qvals": features.get("rl_qvals"),
            # Include detailed fields if present
            "window": features.get("window"),
            "prediction": features.get("prediction"),
            "probabilities": features.get("probabilities"),
            "q_values": features.get("q_values"),
            "dqn_action": features.get("dqn_action"),
            "qaoa_action": features.get("qaoa_action"),
            "reward": features.get("reward"),
            "vfq": features.get("vfq"),
            "energy": features.get("energy"),
            "features": {k: v for k, v in features.items() if k not in ["rl_action", "rl_qvals", "window", "prediction", "probabilities", "q_values", "dqn_action", "qaoa_action", "reward", "vfq", "energy"]},
        }
        with open(LOG_FILE, "a", encoding="utf-8") as f_log:
            f_log.write(json.dumps(log_entry) + "\n")

        # Print features to terminal every 5 seconds
        if int(features["session_duration"]) % 5 == 0:
            print("\n-- Features ---------------------------")
            for key, val in features.items():
                print(f"  {key:25s}: {val}")

        cv2.imshow("Unified Pipeline", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        # Auto-exit after processing 30 frames (approx 1 s at 30 fps)
        if pipeline.frame_counter >= 300:
            print("\n[INFO] Auto-exit after 30 frames for testing.")
            cap.release()
            cv2.destroyAllWindows()
            time.sleep(0.5)
            break

    pipeline.stop()
    cap.release()
    cv2.destroyAllWindows()
    time.sleep(1)

if __name__ == "__main__":
    run_full_pipeline()