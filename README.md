# DCS Server Monitor

An external monitoring service for DCS World dedicated servers. Polls game port availability and fetches live mission data from the DCS Web UI, then posts alerts and periodic status updates to Discord.

Supports monitoring **multiple servers** from a single container, each with independent configuration and optional per-server Discord channels.

---

## Features

- **Port check** — TCP connect to the DCS game port (default 10308) to detect server up/down
- **Web UI integration** — fetches server name, mission name, mission time, and player list via the DCS encrypted Web UI API (port 8088). The server name is resolved automatically on first contact and cached — no need to configure it manually.
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
  - host: "your-server-ip-or-hostname"
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
| `webui_retries` | `3` | Consecutive failed Web UI checks before sending an alert (to survive mission reloads) |
| `webui_retry_interval` | `10` | Seconds between Web UI retry attempts |
| `log_level` | `INFO` | `DEBUG` · `INFO` · `WARNING` · `ERROR` |

### Per-server options

| Key | Default | Description |
|---|---|---|
| `host` | **required** | IP address or hostname of the DCS server (used for Web UI API calls and Discord display) |
| `game_host` | _(same as host)_ | Real IP/hostname used for the TCP port check. Set this when `host` points to a proxy (e.g. Cloudflare) so the port check hits the actual DCS server directly |
| `game_port` | `10308` | DCS game port (TCP) |
| `webui_port` | `8088` | DCS Web UI port |
| `webui_secret` | `DigitalCombatSimulator.com` | Encryption key for the Web UI API. The default works when the Web UI is accessed via a local reverse proxy (see below) |
| `webui_ssl` | `false` | Set `true` when the Web UI is behind an SSL-terminating reverse proxy (uses HTTPS instead of HTTP) |
| `webui_ssl_verify` | `true` | Set `false` to skip TLS certificate verification (useful for self-signed certs) |
| `webui_user` | _(none)_ | Basic auth username for a reverse proxy in front of the Web UI |
| `webui_pass` | _(none)_ | Basic auth password for a reverse proxy in front of the Web UI |
| `discord_webhook_url` | _(inherits global)_ | Override the webhook for this server only |
| `check_interval` | _(inherits global)_ | Override the check frequency for this server |
| `status_interval` | _(inherits global)_ | Override the status post interval for this server |
| `webui_retries` | _(inherits global)_ | Override the Web UI retry count for this server |
| `webui_retry_interval` | _(inherits global)_ | Override the Web UI retry interval for this server |

### Example: multiple servers with separate channels

```yaml
discord_webhook_url: "https://discord.com/api/webhooks/GLOBAL"

check_interval: 60
status_interval: 21600

servers:
  - host: "10.0.0.1"

  - host: "10.0.0.2"
    discord_webhook_url: "https://discord.com/api/webhooks/PG_CHANNEL"
    check_interval: 30        # check more frequently

  - host: "syria.example.com"
    game_port: 10309
    webui_port: 8089
    discord_webhook_url: "https://discord.com/api/webhooks/SYRIA_CHANNEL"
    status_interval: 3600     # hourly status updates
```

### Example: server behind Cloudflare

When the DCS server's public hostname is proxied through Cloudflare (or any other TCP proxy), the game port check must bypass the proxy and connect directly to the real server IP. Set `game_host` to the real IP while keeping `host` as the public hostname:

```yaml
servers:
  - host: "dcs.yourdomain.com"   # public hostname — used for Web UI API calls and Discord
    game_host: "1.2.3.4"         # real server IP — used only for the TCP port check
    game_port: 10308
    webui_port: 443
    webui_ssl: true
    webui_user: monitor
    webui_pass: your-strong-password
```

---

## Exposing the DCS Web UI via a reverse proxy

The DCS dedicated server Web UI only responds to requests originating from **localhost**. To let the monitor reach it from an external machine you need a reverse proxy running on the **same host as DCS** that forwards requests to `localhost:8088`.

Because the proxy runs locally, DCS still sees all requests as coming from localhost — so the default `webui_secret` (`DigitalCombatSimulator.com`) continues to work. The basic auth is purely to protect the proxy endpoint from unauthorized access.

### Using Caddy (recommended)

[Caddy](https://caddyserver.com/) is a single binary with no runtime dependencies and automatic HTTPS support.

**1. Install Caddy on the DCS server**

Follow the [official install guide](https://caddyserver.com/docs/install) for your OS (Linux/Windows packages available).

**2. Create a Caddyfile**

Copy `Caddyfile.example` from this repo and generate a real password hash:

```bash
caddy hash-password --plaintext 'your-strong-password'
```

Paste the output hash into the `basicauth` block:

```
:8089 {
    basicauth {
        monitor <paste-hash-here>
    }

    reverse_proxy localhost:8088 {
        # Required: DCS checks the Host header to decide if a request is local.
        # Without this, Caddy forwards your external domain as the Host and DCS
        # rejects the request with HTTP 422.
        header_up Host localhost
    }
}
```

> **HTTPS with a domain:** replace `:8089` with your domain name (`dcs.yourdomain.com`) and Caddy will obtain a Let's Encrypt certificate automatically. No other changes needed.

**3. Run Caddy**

```bash
caddy run --config /path/to/Caddyfile
```

Or install it as a service so it starts with the machine:

```bash
# Linux (systemd)
sudo caddy start --config /path/to/Caddyfile

# Windows — see https://caddyserver.com/docs/running#windows-service
```

**4. Update `config.yml` in the monitor**

Point the server entry at the Caddy port and supply the credentials:

```yaml
servers:
  - host: "your-dcs-server-ip"
    game_port: 10308
    webui_port: 443         # Caddy's external port (8089 for plain HTTP, 443 for HTTPS)
    # webui_secret stays as the default — Caddy forwards to localhost
    webui_ssl: true         # enable when Caddy is doing SSL termination
    # webui_ssl_verify: false  # uncomment if using a self-signed certificate
    webui_user: monitor
    webui_pass: your-strong-password
```

**5. Open the port in your firewall**

Allow inbound TCP on port `8089` (or `443` for HTTPS) from the monitoring host only. Keep port `8088` closed externally. When using port `443`, set `webui_ssl: true` in the monitor config.

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
