# DCS Server Monitor

An external monitoring service for DCS World dedicated servers. Polls game port availability and fetches live mission data from the DCS Web UI, then posts alerts and periodic status updates to Discord.

Supports monitoring **multiple servers** from a single container, each with independent configuration and optional per-server Discord channels.

---

## Features

- **Port check** — TCP connect to the DCS game port (default 10308) to detect server up/down
- **Web UI integration** — fetches mission name, mission time, and player list via the DCS encrypted Web UI API (port 8088)
- **Discord alerts** for:
  - Server going offline / coming back online
  - Web UI becoming unreachable while the port is still open
  - Mission changes
  - Configurable periodic status updates (default every 6 hours)
- **Multi-server** — monitors any number of DCS servers in parallel, each in its own thread
- **State persistence** — survives container restarts without firing duplicate alerts

---

## Requirements

- Docker and Docker Compose
- A Discord webhook URL (one globally, or one per server)
- Network access from the monitoring host to each DCS server's game port and Web UI port

---

## How to Run

### 1. Clone the repository

```bash
git clone https://github.com/your-org/dcs-server-monitor.git
cd dcs-server-monitor
```

### 2. Create your config file

```bash
cp config.yml.example config.yml
```

Open `config.yml` and fill in your servers and Discord webhook(s):

```yaml
# Global Discord webhook — used for any server that doesn't set its own
discord_webhook_url: "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"

servers:
  - name: "My DCS Server"
    host: "your-server-ip-or-hostname"
    game_port: 10308
    webui_port: 8088
```

See [Configuration](#configuration) below for all available options.

### 3. Pull and start the container

```bash
docker compose pull
docker compose up -d
```

### 4. Check the logs

```bash
docker compose logs -f
```

### 5. Stop the service

```bash
docker compose down
```

---

## Configuration

All configuration lives in `config.yml`. The file has two sections: global defaults and a list of servers.

### Global options

| Key | Default | Description |
|---|---|---|
| `discord_webhook_url` | _(required if not set per-server)_ | Fallback Discord webhook for all servers |
| `check_interval` | `60` | Seconds between checks |
| `status_interval` | `21600` | Seconds between periodic status posts (6 h) |
| `port_timeout` | `5` | TCP connect timeout in seconds |
| `webui_timeout` | `10` | HTTP request timeout in seconds |
| `log_level` | `INFO` | `DEBUG` · `INFO` · `WARNING` · `ERROR` |

### Per-server options

| Key | Default | Description |
|---|---|---|
| `name` | **required** | Display name used in Discord messages |
| `host` | **required** | IP address or hostname of the DCS server |
| `game_port` | `10308` | DCS game port (TCP) |
| `webui_port` | `8088` | DCS Web UI port |
| `webui_secret` | `DigitalCombatSimulator.com` | Encryption key for the Web UI API. The default works for servers accessible on the local network; remote servers require a negotiated secret |
| `discord_webhook_url` | _(inherits global)_ | Override the webhook for this server only |
| `check_interval` | _(inherits global)_ | Override the check frequency for this server |
| `status_interval` | _(inherits global)_ | Override the status post interval for this server |

### Example: multiple servers with separate channels

```yaml
discord_webhook_url: "https://discord.com/api/webhooks/GLOBAL"

check_interval: 60
status_interval: 21600

servers:
  - name: "Caucasus 24/7"
    host: "10.0.0.1"

  - name: "Persian Gulf Server"
    host: "10.0.0.2"
    discord_webhook_url: "https://discord.com/api/webhooks/PG_CHANNEL"
    check_interval: 30        # check more frequently

  - name: "Syria Night Ops"
    host: "syria.example.com"
    game_port: 10309
    webui_port: 8089
    discord_webhook_url: "https://discord.com/api/webhooks/SYRIA_CHANNEL"
    status_interval: 3600     # hourly status updates
```

---

## Docker image

Images are built automatically via GitHub Actions and pushed to the GitHub Container Registry on every push to `main` and on version tags.

```
ghcr.io/<owner>/<repo>:main       # latest from main branch
ghcr.io/<owner>/<repo>:v1.0.0     # specific release
ghcr.io/<owner>/<repo>:sha-abc123 # specific commit
```

To use a pinned release, edit `docker-compose.yml` and replace `:latest` with a specific tag.

---

## Development

```bash
pip install -r requirements.txt
cp config.yml.example config.yml
# edit config.yml
python -m monitor.main
```

To override the config file path:

```bash
CONFIG_FILE=./my-config.yml python -m monitor.main
```

---

## Data persistence

State is written to `./data/<server-slug>/state.json` on the host (mounted into the container at `/app/data`). This file tracks whether each server was last seen up or down, which mission was loaded, and when the last status post was sent — so the service doesn't spam Discord after a restart.

The `data/` directory is created automatically on first run.
