import random
import numpy as np
# Try importing torch; fallback if unavailable
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
except Exception:
    torch = None
    nn = None
    optim = None
from collections import deque
import config

class DQN(nn.Module):
    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = config.DQN_HIDDEN_DIM):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, action_dim),
        )

    def forward(self, x):
        return self.net(x)

class DQNAgent:
    """Deep Q‑Network agent.
    Provides Q‑values, epsilon‑greedy action selection, replay buffer, and
    training utilities.
    """
    def __init__(self, state_dim: int, action_dim: int = 3):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.policy_net = DQN(state_dim, action_dim)
        self.target_net = DQN(state_dim, action_dim)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()
        self.optimizer = optim.Adam(self.policy_net.parameters(), lr=1e-3)
        self.replay_buffer = deque(maxlen=config.REPLAY_BUFFER)

    # ------------------------------------------------------------------
    # Public interface used by training / inference
    # ------------------------------------------------------------------
    def q_values(self, state: np.ndarray) -> np.ndarray:
        """Return raw Q‑values for all actions for a given state vector."""
        with torch.no_grad():
            state_t = torch.from_numpy(state).float().unsqueeze(0)  # (1, dim)
            q = self.policy_net(state_t).cpu().numpy().flatten()
            return q

    def select_action(self, state: np.ndarray, epsilon: float = 0.0) -> int:
        """Epsilon‑greedy action selection; returns the index of the chosen action."""
        if random.random() < epsilon:
            return random.randrange(self.action_dim)
        q = self.q_values(state)
        return int(np.argmax(q))

    def store_transition(self, s, a, r, s_next, done):
        self.replay_buffer.append((s, a, r, s_next, done))

    def train_step(self) -> float:
        """Sample a batch from the replay buffer and perform a gradient step.
        Returns the MSE loss value.
        """
        batch_size = min(config.DQN_BATCH_SIZE, len(self.replay_buffer))
        if batch_size == 0:
            return 0.0
        batch = random.sample(self.replay_buffer, batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)
        states_t = torch.tensor(states, dtype=torch.float32)
        actions_t = torch.tensor(actions, dtype=torch.long).unsqueeze(1)
        rewards_t = torch.tensor(rewards, dtype=torch.float32).unsqueeze(1)
        next_states_t = torch.tensor(next_states, dtype=torch.float32)
        dones_t = torch.tensor(dones, dtype=torch.float32).unsqueeze(1)

        # Compute target Q values
        with torch.no_grad():
            next_q = self.target_net(next_states_t).max(1)[0].unsqueeze(1)
            target_q = rewards_t + (1 - dones_t) * config.DQN_GAMMA * next_q

        # Current Q for taken actions
        current_q = self.policy_net(states_t).gather(1, actions_t)
        loss = nn.functional.mse_loss(current_q, target_q)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        return loss.item()

    def update_target_network(self):
        self.target_net.load_state_dict(self.policy_net.state_dict())

    def save(self, path: str):
        torch.save(self.policy_net.state_dict(), path)

    def load(self, path: str):
        self.policy_net.load_state_dict(torch.load(path, map_location='cpu'))
        self.update_target_network()
