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
        webui_ssl: bool = False,
        webui_ssl_verify: bool = True,
        webui_user: Optional[str] = None,
        webui_pass: Optional[str] = None,
        game_host: Optional[str] = None,
    ):
        self.host = host
        # Use game_host for the TCP port check when set (e.g. real IP behind Cloudflare)
        self._game_host = game_host or host
        self.game_port = game_port
        self.webui_port = webui_port
        self.webui_timeout = webui_timeout
        self.port_timeout = port_timeout
        self._key = hashlib.sha256(webui_secret.encode()).digest()
        self._scheme = "https" if webui_ssl else "http"
        self._ssl_verify = webui_ssl_verify
        self._auth = (webui_user, webui_pass) if webui_user and webui_pass else None

    # ------------------------------------------------------------------
    # Port check
    # ------------------------------------------------------------------

    def check_port(self) -> bool:
        try:
            with socket.create_connection(
                (self._game_host, self.game_port), timeout=self.port_timeout
            ):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

    # ------------------------------------------------------------------
    # DCS Web UI encrypted API
    # ------------------------------------------------------------------

    def _encrypt(self, payload: dict) -> bytes:
        iv = os.urandom(16)
        data = json.dumps(payload).encode("ascii")
        cipher = AES.new(self._key, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(pad(data, AES.block_size))
        return json.dumps({
            "iv": base64.b64encode(iv).decode("ascii"),
            "ct": base64.b64encode(ciphertext).decode("ascii"),
        }).encode("ascii")

    def _decrypt(self, body: bytes) -> dict:
        data = json.loads(body)
        ct = base64.b64decode(data["ct"])
        iv = base64.b64decode(data["iv"])
        cipher = AES.new(self._key, AES.MODE_CBC, iv)
        plaintext = unpad(cipher.decrypt(ct), AES.block_size)
        return json.loads(plaintext)

    def _api_call(self, uri: str) -> dict:
        url = f"{self._scheme}://{self.host}:{self.webui_port}/encryptedRequest"
        body = self._encrypt({"uri": uri})
        resp = requests.post(
            url,
            data=body,
            auth=self._auth,
            headers={"Content-Type": "application/json"},
            timeout=self.webui_timeout,
            verify=self._ssl_verify,
        )
        resp.raise_for_status()
        return self._decrypt(resp.content)

    def fetch_server_name(self) -> Optional[str]:
        try:
            result = self._api_call("getServerSettings")
            return result.get("settings", {}).get("name") or None
        except Exception as exc:
            logger.warning("Could not fetch server name: %s", exc)
            return None

    def fetch_server_info(self) -> Optional[ServerInfo]:
        try:
            mission = self._api_call("getMissionInfo")
            players_resp = self._api_call("getPlayers")

            raw_players = players_resp.get("players", {}).get("all", {}).values()
            players = [
                PlayerInfo(
                    id=p.get("id", 0),
                    name=p.get("name", ""),
                    slot=str(p.get("slot", "")),
                    side=p.get("side", 0),
                )
                for p in raw_players
            ]

            return ServerInfo(
                mission_name=mission.get("mission_name", "Unknown"),
                mission_time=float(mission.get("mission_time", 0)),
                players=players,
            )
        except requests.HTTPError as exc:
            logger.warning("Web UI API returned HTTP %s", exc.response.status_code)
            return None
        except Exception as exc:
            logger.warning("Web UI API unavailable: %s", exc)
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
