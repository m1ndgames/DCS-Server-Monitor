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

The DCS dedicated server exposes an HTTP API at `POST /encryptedRequest` on port 8088. Payloads are AES-CBC encrypted (key = SHA-256 of the secret, IV prepended to ciphertext, base64-encoded). For servers accessible on the local network the secret is `"DigitalCombatSimulator.com"`. Remote servers use a separately negotiated key.

`DCSChecker._api_call()` handles encrypt → POST → decrypt. If the encrypted API fails, `fetch_server_info()` falls back to a plain HTTP GET to detect whether the web server is at least reachable.

## State persistence

Each server gets its own state file at `<data_dir>/<slugified-name>/state.json`. The slug is produced by `_slugify()` in `main.py` (lowercase alphanumeric, hyphens). State tracks `server_up`, `webui_up`, `last_mission`, and `last_status_ts` (Unix timestamp).

## Alert logic (in `_monitor_server`)

| Condition | Alert sent |
|---|---|
| Port was down, now up | `server_up()` |
| Port was up, now down | `server_down()` |
| Port up, Web UI was up, now down | `webui_unavailable()` |
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
