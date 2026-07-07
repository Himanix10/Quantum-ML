# src/reward_function.py
"""Reward function utilities for the EyeStrain DQN.

The reward is composed of several modular terms:

* **strain_reduction** – positive reward proportional to decrease in VFQ score.
* **reminder_compliance** – reward when a reminder was given and the user
  complied (e.g., took a break).  In the offline setting this is inferred from
  the logged action.
* **unnecessary_reminder** – penalty for sending a reminder when the strain
  level is low.
* **missed_fatigue** – penalty when the system fails to remind during a high‑
  fatigue situation.
* **living_reward** – small constant reward to encourage longer episodes.

Each term can be weighted via constants defined in ``src.config``.  The function
``compute_reward`` aggregates the terms and returns a single float.
"""

from __future__ import annotations

import numpy as np

# Default weight values – they can be overridden in ``src.config``.
try:
    from .config import (
        REWARD_WEIGHT_STRAIN_REDUCTION,
        REWARD_WEIGHT_REMINDER_COMPLIANCE,
        REWARD_WEIGHT_UNNECESSARY_REMINDER,
        REWARD_WEIGHT_MISSED_FATIGUE,
        REWARD_LIVING,
    )
except Exception:  # pragma: no cover – fall back to sensible defaults
    REWARD_WEIGHT_STRAIN_REDUCTION = 1.0
    REWARD_WEIGHT_REMINDER_COMPLIANCE = 0.5
    REWARD_WEIGHT_UNNECESSARY_REMINDER = -0.3
    REWARD_WEIGHT_MISSED_FATIGUE = -1.0
    REWARD_LIVING = 0.01


def strain_reduction(prev_vfq: float, new_vfq: float) -> float:
    """Reward proportional to the decrease in visual‑fatigue score.

    ``prev_vfq`` and ``new_vfq`` are assumed to be normalised to ``[0, 1]``.
    A reduction yields a positive reward; an increase yields a negative one.
    """
    return prev_vfq - new_vfq


def reminder_compliance(reminder_given: bool, reminder_complied: bool) -> float:
    """Reward when a reminder was issued *and* the user complied.

    If no reminder was given, the term is zero.  If a reminder was given and the
    user complied (e.g. took a break), a positive reward is returned.
    """
    if not reminder_given:
        return 0.0
    return 1.0 if reminder_complied else 0.0


def unnecessary_reminder(reminder_given: bool, vfq: float, threshold: float = 0.2) -> float:
    """Penalty for reminding when the VFQ indicates low fatigue.

    ``threshold`` is the VFQ value above which a reminder makes sense.
    """
    if reminder_given and vfq < threshold:
        return -1.0
    return 0.0


def missed_fatigue(reminder_given: bool, vfq: float, threshold: float = 0.7) -> float:
    """Penalty when the user is highly fatigued but no reminder was given.
    """
    if not reminder_given and vfq > threshold:
        return -1.0
    return 0.0


def compute_reward(
    prev_vfq: float,
    new_vfq: float,
    reminder_given: bool,
    reminder_complied: bool,
    unnecessary_reminder_flag: bool,
    missed_fatigue_flag: bool,
    living_reward: float = REWARD_LIVING,
) -> float:
    """Aggregate the modular reward components.

    Parameters are deliberately low‑level so that the offline replay‑generation
    script can decide how to populate them from logged data.
    """
    reward = (
        REWARD_WEIGHT_STRAIN_REDUCTION * strain_reduction(prev_vfq, new_vfq)
        + REWARD_WEIGHT_REMINDER_COMPLIANCE * reminder_compliance(reminder_given, reminder_complied)
        + REWARD_WEIGHT_UNNECESSARY_REMINDER * unnecessary_reminder(reminder_given, new_vfq)
        + REWARD_WEIGHT_MISSED_FATIGUE * missed_fatigue(reminder_given, new_vfq)
        + living_reward
    )
    return float(reward)

__all__ = [
    "compute_reward",
    "strain_reduction",
    "reminder_compliance",
    "unnecessary_reminder",
    "missed_fatigue",
]
