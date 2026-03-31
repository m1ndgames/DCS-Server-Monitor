import logging
import os
import re
import threading
import time

from .config import GlobalConfig, ServerConfig
from .dcs_checker import DCSChecker
from .discord_notifier import DiscordNotifier
from .state import MonitorState


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _monitor_server(cfg: GlobalConfig, server: ServerConfig) -> None:
    slug = _slugify(f"{server.host}-{server.game_port}")
    logger = logging.getLogger(f"monitor.{slug}")
    logger.info("Starting monitor for %s:%d", server.host, server.game_port)

    checker = DCSChecker(
        host=server.host,
        game_port=server.game_port,
        webui_port=server.webui_port,
        webui_secret=server.webui_secret,
        port_timeout=cfg.port_timeout,
        webui_timeout=cfg.webui_timeout,
        webui_ssl=server.webui_ssl,
        webui_ssl_verify=server.webui_ssl_verify,
        webui_user=server.webui_user,
        webui_pass=server.webui_pass,
    )
    state_path = os.path.join(cfg.data_dir, slug, "state.json")
    state = MonitorState.load(state_path)

    notifier = DiscordNotifier(
        webhook_url=cfg.webhook_for(server),
        server_name=state.server_name or f"{server.host}:{server.game_port}",
        host=server.host,
        port=server.game_port,
    )

    check_interval = cfg.check_interval_for(server)
    status_interval = cfg.status_interval_for(server)
    webui_retries = cfg.webui_retries_for(server)
    webui_retry_interval = cfg.webui_retry_interval_for(server)

    while True:
        try:
            result = checker.check()
            now = time.time()

            logger.debug(
                "port_open=%s webui_available=%s",
                result.port_open,
                result.webui_available,
            )

            # --- Port state change ---
            if result.port_open and not state.server_up:
                logger.info("Server came online")
                notifier.server_up(result.server_info)
                state.server_up = True
                state.last_status_ts = now
            elif not result.port_open and state.server_up:
                logger.info("Server went offline")
                notifier.server_down()
                state.server_up = False
                state.webui_up = False
                state.last_mission = ""

            # --- Fetch server name from Web UI (once, then cached in state) ---
            if result.webui_available and not state.server_name:
                name = checker.fetch_server_name()
                if name:
                    state.server_name = name
                    notifier.server_name = name
                    logger.info("Server name resolved: %s", name)

            # --- Web UI state changes (only when port is open) ---
            if result.port_open:
                if not result.webui_available and state.webui_up:
                    confirmed_down = True
                    for attempt in range(1, webui_retries):
                        logger.debug(
                            "Web UI check failed, retry %d/%d in %ds",
                            attempt, webui_retries - 1, webui_retry_interval,
                        )
                        time.sleep(webui_retry_interval)
                        if checker.fetch_server_info() is not None:
                            confirmed_down = False
                            break
                    if confirmed_down:
                        logger.info("Web UI became unavailable (confirmed after %d tries)", webui_retries)
                        notifier.webui_unavailable()
                        state.webui_up = False
                elif result.webui_available and not state.webui_up:
                    logger.info("Web UI became available")
                    notifier.webui_available(result.server_info)
                    state.webui_up = True

                # --- Mission change ---
                if result.server_info and result.server_info.mission_name not in ("Unknown", ""):
                    mission = result.server_info.mission_name
                    if state.last_mission and state.last_mission != mission:
                        logger.info("Mission changed: %s -> %s", state.last_mission, mission)
                        notifier.mission_changed(
                            old_mission=state.last_mission,
                            new_mission=mission,
                            player_count=result.server_info.player_count,
                        )
                    state.last_mission = mission

            # --- Periodic status update ---
            if now - state.last_status_ts >= status_interval:
                logger.info("Sending periodic status update")
                notifier.status_update(result.server_info if result.port_open else None)
                state.last_status_ts = now

            state.save(state_path)

        except Exception as exc:
            logger.exception("Unexpected error during check: %s", exc)

        time.sleep(check_interval)


def run() -> None:
    config_file = os.environ.get("CONFIG_FILE", "/app/config.yml")

    if not os.path.isfile(config_file):
        raise SystemExit(
            f"Config file not found: {config_file}\n"
            "Mount your config into the container, e.g.:\n"
            "  docker compose up   (config.yml must exist next to docker-compose.yml)\n"
            "See config.yml.example for the required format."
        )

    cfg = GlobalConfig.from_yaml(config_file)

    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger(__name__)
    logger.info("Loaded %d server(s) from %s", len(cfg.servers), config_file)

    threads = [
        threading.Thread(
            target=_monitor_server,
            args=(cfg, server),
            name=_slugify(f"{server.host}-{server.game_port}"),
            daemon=True,
        )
        for server in cfg.servers
    ]

    for t in threads:
        t.start()

    # Block forever; daemon threads exit when the process does
    for t in threads:
        t.join()


if __name__ == "__main__":
    run()
