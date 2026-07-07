import json
import numpy as np
from pathlib import Path

import sys
from pathlib import Path
# Add the project root (two levels up) to sys.path so that modules can be imported directly
project_root = Path(__file__).resolve().parents[1]
sys.path.append(str(project_root))

# Project imports (now using top‑level module names)
from state_builder import build_state
from reward_function import compute_reward  # not used directly here – rewards are stored in replay data
from deep_rl_agent import DQNAgent
from config import (
    DQN_BATCH_SIZE,
    DQN_TRAIN_EPOCHS,
    DQN_TARGET_UPDATE,
    DQN_GAMMA,
    DQN_HIDDEN_DIM,
)

# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------
DATA_ROOT = Path(__file__).parents[2] / "data" / "processed"
REPLAY_JSONL = DATA_ROOT / "replay_dataset.jsonl"
LOG_DIR = Path(__file__).parents[2] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "dqn_training_log.json"
CHECKPOINT_PATH = Path(__file__).parents[2] / "models" / "dqn_checkpoint.pth"
CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------
# Helper: load replay transitions from the JSON‑lines file
# ---------------------------------------------------------------------
def load_transitions(path: Path):
    """Read the replay_dataset.jsonl and return a list of transition dicts.
    Each line has the shape:
        {"episode": "sess1", "transition": {"state": [...], "action": 0,
         "reward": 1.2, "next_state": [...], "done": false}}
    """
    transitions = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            transitions.append(obj["transition"])
    return transitions

# ---------------------------------------------------------------------
# Main training routine
# ---------------------------------------------------------------------
def train_dqn():
    # Load replay data
    print(f"[INFO] Loading replay dataset from {REPLAY_JSONL}")
    transitions = load_transitions(REPLAY_JSONL)
    if not transitions:
        raise RuntimeError("Replay dataset is empty – cannot train DQN.")

    # Initialise DQNAgent – state_dim = 128 (embedding) + 5 (probs) + 4 scalars = 137
    STATE_DIM = 128 + 5 + 4
    ACTION_DIM = 3  # 0=continue, 1=reminder, 2=break
    agent = DQNAgent(state_dim=STATE_DIM, action_dim=ACTION_DIM)

    # Populate replay buffer with the offline transitions
    for tr in transitions:
        agent.store_transition(
            tr["state"],
            tr["action"],
            tr["reward"],
            tr["next_state"],
            tr["done"],
        )
    print(f"[INFO] Replay buffer size: {len(agent.replay_buffer)} transitions")

    # Training loop
    epoch_losses = []
    for epoch in range(1, DQN_TRAIN_EPOCHS + 1):
        loss = agent.train_step()
        epoch_losses.append(loss)

        # Periodically sync target network
        if epoch % DQN_TARGET_UPDATE == 0:
            agent.update_target_network()

        # Log every few epochs
        if epoch % 5 == 0 or epoch == DQN_TRAIN_EPOCHS:
            print(f"[Epoch {epoch:03d}] loss={loss:.4f}")
            with open(LOG_FILE, "a", encoding="utf-8") as log_f:
                log_entry = {"epoch": epoch, "loss": loss}
                log_f.write(json.dumps(log_entry) + "\n")

    # Save final checkpoint
    agent.save(str(CHECKPOINT_PATH))
    print(f"[INFO] DQN checkpoint saved to {CHECKPOINT_PATH}")

    avg_loss = sum(epoch_losses) / len(epoch_losses)
    print(f"[DONE] Training completed – avg loss: {avg_loss:.4f}")


if __name__ == "__main__":
    train_dqn()
