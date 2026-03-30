import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MonitorState:
    server_up: bool = False
    webui_up: bool = False
    last_mission: str = ""
    last_status_ts: float = 0.0  # unix timestamp of last periodic status
    server_name: str = ""  # cached from DCS Web UI getServerSettings

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "w") as f:
                json.dump(asdict(self), f)
        except OSError as exc:
            logger.warning("Could not save state: %s", exc)

    @classmethod
    def load(cls, path: str) -> "MonitorState":
        try:
            with open(path) as f:
                data = json.load(f)
            return cls(**data)
        except (FileNotFoundError, KeyError, json.JSONDecodeError):
            return cls()
