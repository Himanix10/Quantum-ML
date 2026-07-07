# src/state_builder.py
"""State Builder for the RL component.

This module constructs a single NumPy vector representing the full RL state
required by the Deep Q‑Network.  The state consists of:

1. Embedding (output of the TCN) – fixed size 128 (or whatever the model
   returns).
2. Probability vector from the classifier – 5 soft‑max probabilities.
3. Visual‑fatigue questionnaire (VFQ) score.
4. Time since the last break (seconds).
5. Workload metric (normalized between 0 and 1).
6. Session duration (seconds).

Scalar values are normalised to the range [0, 1] using simple clipping and a
maximum‑value heuristic.  Those maxima are defined in ``src.config`` so they can
be tweaked without code changes.
"""

from __future__ import annotations

import numpy as np

# Import optional configuration constants.  If they are missing we fall back to
# sensible defaults.
try:
    from .config import (
        MAX_TIME_SINCE_BREAK,
        MAX_WORKLOAD,
        MAX_SESSION_DURATION,
        MAX_VFQ,
    )
except Exception:  # pragma: no cover – defaults used when config lacks them
    MAX_TIME_SINCE_BREAK = 3600.0  # 1 hour
    MAX_WORKLOAD = 1.0
    MAX_SESSION_DURATION = 7200.0  # 2 hours
    MAX_VFQ = 100.0


def _normalize(value: float, max_val: float) -> float:
    """Clip *value* to ``[0, max_val]`` and scale to ``[0, 1]``.

    Parameters
    ----------
    value: float
        Raw scalar metric.
    max_val: float
        Maximum expected value for this metric.
    """
    if max_val <= 0:
        return 0.0
    return min(max(value, 0.0) / max_val, 1.0)


def build_state(
    embedding: np.ndarray,
    probs: np.ndarray,
    vfq: float,
    time_since_break: float,
    workload: float,
    session_duration: float,
) -> np.ndarray:
    """Construct the RL state vector.

    The function concatenates the embedding, the probability vector and the four
    normalised scalar metrics into a single 1‑D NumPy array.

    Parameters
    ----------
    embedding: np.ndarray
        Latent feature vector from the TCN (shape ``(128,)``).
    probs: np.ndarray
        Soft‑max probability vector for the five strain classes.
    vfq: float
        Visual‑fatigue questionnaire score.
    time_since_break: float
        Seconds elapsed since the user took a break.
    workload: float
        Estimated workload (already in ``[0, 1]`` but will be normalised anyway).
    session_duration: float
        Length of the current session in seconds.

    Returns
    -------
    np.ndarray
        1‑D state vector ready for the DQN.
    """
    # Ensure the inputs have the expected dimensions / types.
    embedding = np.asarray(embedding, dtype=np.float32).flatten()
    probs = np.asarray(probs, dtype=np.float32).flatten()

    # Normalise scalar metrics.
    vfq_norm = _normalize(vfq, MAX_VFQ)
    tsb_norm = _normalize(time_since_break, MAX_TIME_SINCE_BREAK)
    wl_norm = _normalize(workload, MAX_WORKLOAD)
    sd_norm = _normalize(session_duration, MAX_SESSION_DURATION)

    scalar_vec = np.array([vfq_norm, tsb_norm, wl_norm, sd_norm], dtype=np.float32)

    # Concatenate everything.
    state = np.concatenate([embedding, probs, scalar_vec])
    return state

__all__ = ["build_state"]
