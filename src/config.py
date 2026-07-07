# Configuration flags for the EyeStrain project
# Set to True to enable quantum feature fusion. Keep False for the classical baseline.
USE_QUANTUM = True

# --- Reinforcement Learning flags ---
USE_DRL = True
USE_QAOA = True

# --- DQN hyper‑parameters ---
DQN_HIDDEN_DIM = 128
DQN_BATCH_SIZE = 64
DQN_GAMMA = 0.99
REPLAY_BUFFER = 10000
# Number of steps between target‑net sync (used by training scripts)
DQN_TARGET_UPDATE = 100
# Number of training epochs/iterations for offline DQN training
DQN_TRAIN_EPOCHS = 500
EPSILON_START = 1.0
EPSILON_END = 0.05
EPSILON_DECAY = 0.995

# --- QAOA hyper‑parameters ---
QAOA_LAYERS = 2

# --- Training termination criteria ---
MAX_EPISODES = 500
MAX_STEPS_PER_EP = 1000
CONVERGENCE_WINDOW = 100
REWARD_THRESHOLD = 4.5

# --- Normalisation helpers (max observed values) ---
VFQ_MAX = 1.0
WORKLOAD_MAX = 100.0
BREAK_INTERVAL_MAX = 60.0  # minutes
SESSION_LIMIT_MAX = 180.0  # minutes
