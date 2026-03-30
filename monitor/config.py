import os
from dataclasses import dataclass, field
from typing import Optional

import yaml


@dataclass
class ServerConfig:
    host: str
    game_port: int = 10308
    webui_port: int = 8088
    webui_secret: str = "DigitalCombatSimulator.com"
    # Basic auth credentials for a reverse proxy sitting in front of the Web UI
    webui_user: Optional[str] = None
    webui_pass: Optional[str] = None
    # When set, overrides the global discord_webhook_url for this server
    discord_webhook_url: Optional[str] = None
    # When set, overrides global check/status intervals for this server
    check_interval: Optional[int] = None
    status_interval: Optional[int] = None
    # When set, overrides global webui retry settings for this server
    webui_retries: Optional[int] = None
    webui_retry_interval: Optional[int] = None


@dataclass
class GlobalConfig:
    servers: list[ServerConfig]
    discord_webhook_url: str = ""
    check_interval: int = 60
    status_interval: int = 21600  # 6 hours
    port_timeout: float = 5.0
    webui_timeout: float = 10.0
    webui_retries: int = 3
    webui_retry_interval: int = 10  # seconds between retries
    data_dir: str = "/app/data"
    log_level: str = "INFO"

    def webhook_for(self, server: ServerConfig) -> str:
        url = server.discord_webhook_url or self.discord_webhook_url
        if not url:
            raise ValueError(
                f"No discord_webhook_url configured for server '{server.host}:{server.game_port}' "
                "and no global discord_webhook_url set."
            )
        return url

    def check_interval_for(self, server: ServerConfig) -> int:
        return server.check_interval if server.check_interval is not None else self.check_interval

    def status_interval_for(self, server: ServerConfig) -> int:
        return server.status_interval if server.status_interval is not None else self.status_interval

    def webui_retries_for(self, server: ServerConfig) -> int:
        return server.webui_retries if server.webui_retries is not None else self.webui_retries

    def webui_retry_interval_for(self, server: ServerConfig) -> int:
        return server.webui_retry_interval if server.webui_retry_interval is not None else self.webui_retry_interval

    @classmethod
    def from_yaml(cls, path: str) -> "GlobalConfig":
        with open(path) as f:
            data = yaml.safe_load(f) or {}

        servers_raw = data.get("servers", [])
        if not servers_raw:
            raise ValueError(f"No servers defined in {path}")

        servers = [
            ServerConfig(
                host=s["host"],
                game_port=s.get("game_port", 10308),
                webui_port=s.get("webui_port", 8088),
                webui_secret=s.get("webui_secret", "DigitalCombatSimulator.com"),
                webui_user=s.get("webui_user"),
                webui_pass=s.get("webui_pass"),
                discord_webhook_url=s.get("discord_webhook_url"),
                check_interval=s.get("check_interval"),
                status_interval=s.get("status_interval"),
                webui_retries=s.get("webui_retries"),
                webui_retry_interval=s.get("webui_retry_interval"),
            )
            for s in servers_raw
        ]

        return cls(
            servers=servers,
            discord_webhook_url=data.get("discord_webhook_url", ""),
            check_interval=int(data.get("check_interval", 60)),
            status_interval=int(data.get("status_interval", 21600)),
            port_timeout=float(data.get("port_timeout", 5.0)),
            webui_timeout=float(data.get("webui_timeout", 10.0)),
            webui_retries=int(data.get("webui_retries", 3)),
            webui_retry_interval=int(data.get("webui_retry_interval", 10)),
            data_dir=data.get("data_dir", "/app/data"),
            log_level=data.get("log_level", "INFO"),
        )
