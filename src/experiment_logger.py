import json
from datetime import datetime
from pathlib import Path

class Logger:
    """Simple JSON line logger used by training and inference scripts.
    Each call writes a JSON object suffixed with a newline; the file can be
    consumed directly by pandas or plotted with standard tools.
    """
    def __init__(self, log_file: str):
        self.path = Path(__file__).parents[2] / log_file
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(self.path, "a", encoding="utf-8")

    def log(self, record: dict):
        record["timestamp"] = datetime.utcnow().isoformat()
        self.file.write(json.dumps(record) + "\n")
        self.file.flush()

    def __del__(self):
        if not self.file.closed:
            self.file.close()
