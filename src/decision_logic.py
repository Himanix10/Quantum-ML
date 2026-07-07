from qaoa_optimizer import decode_bits

import numpy as np

def interpret_qaoa(bits: np.ndarray) -> str:
    """Convert QAOA bitstring to a high‑level action identifier.
    The bits are a length‑3 binary array representing
    [continue, reminder, break]. The function returns the action with the
    highest probability (the bit set to 1)."""
    return decode_bits(bits)

def execute_action(action_id: str) -> None:
    """Execute the selected action.
    Currently this is a stub that prints a message; it can be wired to the
    existing reminder/break scheduler modules."""
    if action_id == "continue":
        print("[ACTION] Continue – no interruption.")
    elif action_id == "reminder":
        print("[ACTION] Reminder – notifying user.")
        # TODO: integrate with the project's reminder module
    elif action_id == "break":
        print("[ACTION] Break – scheduling short break.")
        # TODO: integrate with break scheduler
    else:
        raise ValueError(f"Unknown action_id: {action_id}")
