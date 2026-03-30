import base64
import hashlib
import json
import logging
import os
import socket
from dataclasses import dataclass, field
from typing import Optional

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

logger = logging.getLogger(__name__)


@dataclass
class PlayerInfo:
    id: int
    name: str
    slot: str
    side: int  # 0=spectator, 1=red, 2=blue


@dataclass
class ServerInfo:
    mission_name: str
    mission_time: float  # seconds elapsed
    players: list[PlayerInfo] = field(default_factory=list)

    @property
    def player_count(self) -> int:
        # slot 1 is "Server" itself, exclude it
        return sum(1 for p in self.players if p.id != 1)

    def mission_time_str(self) -> str:
        h = int(self.mission_time // 3600)
        m = int((self.mission_time % 3600) // 60)
        return f"{h:02d}:{m:02d}"


@dataclass
class CheckResult:
    port_open: bool
    webui_available: bool
    server_info: Optional[ServerInfo] = None


class DCSChecker:
    def __init__(
        self,
        host: str,
        game_port: int,
        webui_port: int,
        webui_secret: str,
        port_timeout: float,
        webui_timeout: float,
        webui_user: Optional[str] = None,
        webui_pass: Optional[str] = None,
    ):
        self.host = host
        self.game_port = game_port
        self.webui_port = webui_port
        self.webui_timeout = webui_timeout
        self.port_timeout = port_timeout
        self._key = hashlib.sha256(webui_secret.encode()).digest()
        self._auth = (webui_user, webui_pass) if webui_user and webui_pass else None

    # ------------------------------------------------------------------
    # Port check
    # ------------------------------------------------------------------

    def check_port(self) -> bool:
        try:
            with socket.create_connection(
                (self.host, self.game_port), timeout=self.port_timeout
            ):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

    # ------------------------------------------------------------------
    # DCS Web UI encrypted API
    # ------------------------------------------------------------------

    def _encrypt(self, payload: dict) -> str:
        iv = os.urandom(16)
        data = json.dumps(payload).encode()
        cipher = AES.new(self._key, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(pad(data, AES.block_size))
        return base64.b64encode(iv + ciphertext).decode()

    def _decrypt(self, encoded: str) -> dict:
        raw = base64.b64decode(encoded)
        iv, ciphertext = raw[:16], raw[16:]
        cipher = AES.new(self._key, AES.MODE_CBC, iv)
        plaintext = unpad(cipher.decrypt(ciphertext), AES.block_size)
        return json.loads(plaintext)

    def _api_call(self, method: str, params: Optional[dict] = None) -> dict:
        url = f"http://{self.host}:{self.webui_port}/encryptedRequest"
        body = self._encrypt({"method": method, "params": params or {}})
        resp = requests.post(url, data=body, auth=self._auth, timeout=self.webui_timeout)
        resp.raise_for_status()
        return self._decrypt(resp.text)

    def fetch_server_info(self) -> Optional[ServerInfo]:
        try:
            mission = self._api_call("getMissionInfo")
            players_resp = self._api_call("getPlayers")

            raw_players = players_resp.get("players", [])
            players = [
                PlayerInfo(
                    id=p.get("id", 0),
                    name=p.get("name", ""),
                    slot=p.get("slot", ""),
                    side=p.get("side", 0),
                )
                for p in raw_players
            ]

            return ServerInfo(
                mission_name=mission.get("name", "Unknown"),
                mission_time=float(mission.get("missionTime", 0)),
                players=players,
            )
        except Exception as exc:
            logger.debug("Web UI API unavailable: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Combined check
    # ------------------------------------------------------------------

    def check(self) -> CheckResult:
        port_open = self.check_port()
        server_info: Optional[ServerInfo] = None
        webui_available = False

        if port_open:
            server_info = self.fetch_server_info()
            webui_available = server_info is not None

        return CheckResult(
            port_open=port_open,
            webui_available=webui_available,
            server_info=server_info,
        )
