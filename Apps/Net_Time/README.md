# Net Time

LAN time authority for Mission Control venues. Runs on Proxmox as:

1. A privileged **LXC** with **chrony** (NTP/SNTP UDP 123) and a FastAPI management API (TCP 8720)
2. A **host clock agent** on the Proxmox node (TCP 8721) so **Offline Sync** can set the shared host clock when the LXC cannot

Core Configurator holds the URL + token and exposes **Attempt Online Sync**, a **timezone dropdown**, and **Offline Sync** (manual date/time). The status line shows wall time in the configured timezone (NTP itself remains UTC).

PDN/FDN client sync is owned by those firmware teams. This app ships the server and operator controls only. Point devices at the Net Time LXC IP on **UDP 123** (SNTP); time is always **UTC**.

## PDN / FDN — grab time (SNTP)

Replace `<NET_TIME_IP>` with the printed LXC IP from install (or Core Configurator Net Time URL host).

| Item | Value |
| --- | --- |
| Protocol | SNTP / NTP |
| Host | `<NET_TIME_IP>` |
| Port | **UDP 123** |
| Auth | none (LAN NTP; management API token is **not** used) |
| Timebase | UTC |

### One-shot checks (from a laptop / Pi on the venue LAN)

```bash
# Preferred (chrony client)
chronyd -Q "server <NET_TIME_IP> iburst"

# sntp (ntpsec / ntp package)
sntp <NET_TIME_IP>

# Query without setting the local clock (older ntpdate)
ntpdate -q <NET_TIME_IP>
```

### Point a systemd NTP client at Net Time

```bash
# /etc/systemd/timesyncd.conf (or drop-in)
[Time]
NTP=<NET_TIME_IP>
FallbackNTP=

sudo systemctl restart systemd-timesyncd
timedatectl timesync-status
```

### ESP / firmware (PDN & FDN)

Configure the SNTP server to `<NET_TIME_IP>` (port 123). Examples:

```c
// Arduino / ESP8266WiFi or ESP32 WiFi
configTime(0, 0, "<NET_TIME_IP>");   // GMT offset 0 — Net Time serves UTC
```

```c
// ESP-IDF
esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
esp_sntp_setservername(0, "<NET_TIME_IP>");
esp_sntp_init();
```

Do **not** use the management API (`:8720`) or host clock agent (`:8721`) from PDN/FDN — those are for Core Configurator / Offline Sync only.

## Layout

| Path | Role |
| --- | --- |
| `Server_Component/` | FastAPI API, chrony helpers, `host_clock_agent.py`, `chrony.conf` |
| `HA_Component/` | Home Assistant bridge (`net_time/*` websocket → management API) |
| `ProxmoxInstallFiles/install-net-time-proxmox.sh` | Creates LXC + host clock agent |
| `ProxmoxInstallFiles/upgrade-net-time-host-clock.sh` | Retrofit host agent onto an existing CT |

## Management API (LXC)

Bearer token: `NET_TIME_API_TOKEN` (same value as Core Configurator `net_time` token).

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health` | no | Liveness |
| `GET` | `/status` | yes | UTC clock, timezone, stratum, public NTP `reachable` / `unavailable` |
| `POST` | `/sync` | yes | Set clock from `{ "iso8601": "..." }` (LXC, then host agent) |
| `POST` | `/timezone` | yes | `{ "timezone": "America/Chicago" }` via `timedatectl` |

Default bind: `0.0.0.0:8720`. Env: `/etc/net-time.env` (`NET_TIME_API_TOKEN`, `NET_TIME_HOST_CLOCK_URL`).

## Host clock agent

| Item | Value |
| --- | --- |
| Script | `Server_Component/host_clock_agent.py` → `/usr/local/sbin/net-time-host-clock` |
| Unit | `net-time-host-clock.service` |
| Port | **8721** |
| Auth | Same Bearer token as the LXC API |
| Endpoints | `GET /health`, `POST /sync` |

Required because Proxmox LXCs share the host clock and usually cannot `date -s`. Do not use `lxc.cap.keep: sys_time` (breaks CT start when `lxc.cap.drop` is present).

## Core Configurator UI

- **Attempt Online Sync** — succeeds when MC can reach Net Time and public NTP is reachable; otherwise prompts **Please set via Offline Sync**
- **Timezone** — dropdown of common venue IANA zones → **Set timezone**
- **Offline Sync** — expands date/time fields; **Apply Offline Sync** pushes that wall time (may use host clock agent under the hood)

## Deploy

See [`Docs/Net Time Config Steps.md`](../../Docs/Net%20Time%20Config%20Steps.md).

```bash
# On Proxmox host
NET_TIME_SRC=/root/net-time-src bash /root/install-net-time-proxmox.sh
```

Paste printed `cc_net_time` / `cc_net_time_token` into Core Configurator.

## Local tests

```bash
cd Apps/Net_Time/Server_Component
pip install -e ".[test]"
pytest

cd ../HA_Component
pytest
```
