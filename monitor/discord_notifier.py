import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import requests

from .dcs_checker import ServerInfo

logger = logging.getLogger(__name__)

COLOR_GREEN = 0x2ECC71
COLOR_RED = 0xE74C3C
COLOR_YELLOW = 0xF1C40F
COLOR_BLUE = 0x3498DB


@dataclass
class Embed:
    title: str
    description: str
    color: int
    fields: list[dict]

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "description": self.description,
            "color": self.color,
            "fields": self.fields,
        }


class DiscordNotifier:
    def __init__(self, webhook_url: str, server_name: str, host: str, port: int):
        self.webhook_url = webhook_url
        self.server_name = server_name
        self._address = f"{host}:{port}"

    def _send(self, embed: Embed) -> None:
        d = embed.to_dict()
        d["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        d["footer"] = {
            "text": f"{self._address} • DCS-Server-Monitor",
            "icon_url": "https://github.com/favicon.ico",
        }
        d["url"] = "https://github.com/m1ndgames/DCS-Server-Monitor"
        payload = {"embeds": [d]}
        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to send Discord notification: %s", exc)

    def server_down(self) -> None:
        self._send(
            Embed(
                title=f":red_circle: {self.server_name} — OFFLINE",
                description="The DCS game port is unreachable.",
                color=COLOR_RED,
                fields=[],
            )
        )

    def server_up(self, info: Optional[ServerInfo]) -> None:
        fields = []
        if info and info.mission_name != "Unknown":
            fields.append({"name": "Mission", "value": info.mission_name, "inline": True})
            fields.append(
                {"name": "Players", "value": str(info.player_count), "inline": True}
            )
        self._send(
            Embed(
                title=f":green_circle: {self.server_name} — ONLINE",
                description="The DCS server is back online.",
                color=COLOR_GREEN,
                fields=fields,
            )
        )

    def webui_available(self, info: ServerInfo) -> None:
        fields = [
            {"name": "Mission", "value": info.mission_name, "inline": True},
            {"name": "Mission Time", "value": info.mission_time_str(), "inline": True},
            {"name": "Players Online", "value": str(info.player_count), "inline": True},
        ]
        if info.player_count > 0:
            names = "\n".join(p.name for p in info.players if p.id != 1) or "—"
            fields.append({"name": "Player List", "value": names, "inline": False})
        self._send(
            Embed(
                title=f":green_circle: {self.server_name} — Web UI Online",
                description="Mission details are now available.",
                color=COLOR_GREEN,
                fields=fields,
            )
        )

    def webui_unavailable(self) -> None:
        self._send(
            Embed(
                title=f":yellow_circle: {self.server_name} — Web UI Unavailable",
                description=(
                    "The game port is open but the Web UI is not responding. "
                    "Mission details are unavailable."
                ),
                color=COLOR_YELLOW,
                fields=[],
            )
        )

    def mission_changed(self, old_mission: str, new_mission: str, player_count: int) -> None:
        self._send(
            Embed(
                title=f":blue_circle: {self.server_name} — New Mission",
                description=f"**{new_mission}**",
                color=COLOR_BLUE,
                fields=[
                    {"name": "Previous Mission", "value": old_mission or "—", "inline": True},
                    {"name": "Players Online", "value": str(player_count), "inline": True},
                ],
            )
        )

    def status_update(self, info: Optional[ServerInfo]) -> None:
        if info:
            fields = [
                {"name": "Mission", "value": info.mission_name, "inline": True},
                {"name": "Mission Time", "value": info.mission_time_str(), "inline": True},
                {"name": "Players Online", "value": str(info.player_count), "inline": True},
            ]
            if info.player_count > 0:
                names = "\n".join(
                    p.name for p in info.players if p.id != 1
                ) or "—"
                fields.append({"name": "Player List", "value": names, "inline": False})
            self._send(
                Embed(
                    title=f":green_circle: {self.server_name} — Status Update",
                    description="Periodic server status report.",
                    color=COLOR_GREEN,
                    fields=fields,
                )
            )
        else:
            self._send(
                Embed(
                    title=f":red_circle: {self.server_name} — Status Update",
                    description="Server is currently **offline**.",
                    color=COLOR_RED,
                    fields=[],
                )
            )
