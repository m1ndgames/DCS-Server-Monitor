# DCS Server Monitor — Claude Context

## What this project is

A Python monitoring service that watches one or more DCS World dedicated servers and sends alerts to Discord. It runs as a single Docker container.

## Architecture

```
monitor/
├── config.py           — GlobalConfig + ServerConfig, loaded from config.yml via PyYAML
├── dcs_checker.py      — DCSChecker: TCP port check + DCS Web UI encrypted API calls
├── discord_notifier.py — DiscordNotifier: sends embeds to a Discord webhook
├── state.py            — MonitorState: JSON-persisted per-server state
└── main.py             — Entry point: spawns one daemon thread per server
```

Each server runs independently in its own thread (`threading.Thread`). Threads share no mutable state.

## Configuration model

`config.yml` is the single source of truth. It has global defaults and a `servers:` list. Per-server keys (`discord_webhook_url`, `check_interval`, `status_interval`) override globals when set.

`GlobalConfig.webhook_for(server)` and `GlobalConfig.check_interval_for(server)` are the canonical accessors — always use these, never read server fields directly in `main.py`.

## DCS Web UI protocol

The DCS dedicated server exposes an HTTP API at `POST /encryptedRequest` on port 8088. It only responds to requests from localhost. Payloads are AES-CBC encrypted (key = SHA-256 of the secret, IV prepended to ciphertext, base64-encoded). The default secret `"DigitalCombatSimulator.com"` works when the request originates from localhost — which is always the case when a local reverse proxy (e.g. Caddy) is used.

`DCSChecker._api_call()` handles encrypt → POST → decrypt. It uses HTTPS when `webui_ssl=True` (stored as `self._scheme`), with TLS verification controlled by `webui_ssl_verify` (stored as `self._ssl_verify`). It passes HTTP basic auth credentials (`self._auth`) when `webui_user`/`webui_pass` are configured, which is required when a reverse proxy with basic auth sits in front of the Web UI. If the API call fails for any reason, `fetch_server_info()` returns `None` (Web UI unavailable).

`DCSChecker.fetch_server_name()` calls `getServerSettings` and returns `settings.name`. This is called once from `_monitor_server` when the Web UI first becomes reachable and `state.server_name` is empty; the result is cached in state and assigned to `notifier.server_name`.

## State persistence

Each server gets its own state file at `<data_dir>/<slug>/state.json`. The slug is derived from `host` + `game_port` (e.g. `116-202-232-32-10308`) by `_slugify()` in `main.py` (lowercase alphanumeric, hyphens). State tracks `server_up`, `webui_up`, `last_mission`, `last_status_ts` (Unix timestamp), and `server_name` (fetched from the Web UI and cached so it survives restarts).

## Alert logic (in `_monitor_server`)

| Condition | Alert sent |
|---|---|
| Port was down, now up | `server_up()` |
| Port was up, now down | `server_down()` |
| Port up, Web UI was up, now down (confirmed after `webui_retries` attempts) | `webui_unavailable()` |
| Mission name changed | `mission_changed()` |
| `now - last_status_ts >= status_interval` | `status_update()` |

## Docker

- Base image: `python:3.12-slim`
- The image contains only `monitor/` and installed dependencies — no config is baked in
- `.dockerignore` excludes `config.yml`, `.env`, and `data/` from the build context
- Config file mounted read-only at runtime: `./config.yml:/app/config.yml:ro`
- State directory mounted at runtime: `./data:/app/data`
- Entry point: `python -m monitor.main`
- `CONFIG_FILE` env var overrides the config path (default `/app/config.yml`)
- `LOG_LEVEL` env var can override `log_level` from the compose file without editing `config.yml`
- If the config file is missing at startup, `main.py` exits with a clear human-readable message

## CI/CD

`.github/workflows/docker.yml` builds and pushes to GHCR (`ghcr.io/<owner>/<repo>`) on pushes to `main` and on `v*` tags. PRs only build (no push). Uses `docker/build-push-action` with GHA layer cache.

## Dependencies

| Package | Purpose |
|---|---|
| `requests` | HTTP calls to DCS Web UI and Discord webhooks |
| `pycryptodome` | AES-CBC encryption for the DCS Web UI API |
| `pyyaml` | Parsing `config.yml` |

## Common tasks

**Add a new alert type** — add a method to `DiscordNotifier`, call it in `_monitor_server` in `main.py`.

**Add a new per-server config option** — add the field to `ServerConfig`, parse it in `GlobalConfig.from_yaml`, add an accessor on `GlobalConfig` if it needs a global fallback.

**Run locally**
```bash
pip install -r requirements.txt
CONFIG_FILE=./config.yml python -m monitor.main
```
