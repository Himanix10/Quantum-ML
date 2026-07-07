import json
import pandas as pd
from pathlib import Path

def load_profile(path: Path):
    """Load a JSON profile containing user‑level defaults.
    Returns a dict.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_session_csvs(folder: Path):
    """Load all session CSV files from *folder*.
    Expected filename pattern: ``session_<id>.csv``.
    Returns a dict mapping session IDs to pandas DataFrames.
    Each CSV must contain at least the columns:
        vfq, time_since_break, workload, session_duration,
        action_id, reminder_followed
    """
    sessions = {}
    for csv_path in folder.glob("session_*.csv"):
        sess_id = csv_path.stem.split("_", 1)[1]
        df = pd.read_csv(csv_path)
        sessions[sess_id] = df
    return sessions

def load_reward_system(path: Path):
    """Dynamically import the reward_system module located at *path*.
    Returns the imported module object.
    """
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location("reward_system", str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["reward_system"] = mod
    spec.loader.exec_module(mod)
    return mod
