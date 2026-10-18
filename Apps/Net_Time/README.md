# Net Time

LAN time authority for Mission Control venues. Runs on Proxmox as:

1. A privileged **LXC** with **chrony** (NTP/SNTP UDP 123) and a FastAPI management API (TCP 8720)
2. A **host clock agent** on the Proxmox node (TCP 8721) so **Offline Sync** can set the shared host clock when the LXC cannot

Core Configurator holds the URL + token and exposes **Attempt Online Sync**, a **timezone dropdown**, and **Offline Sync** (manual date/time). The status line shows wall time in the configured timezone (NTP itself remains UTC).

PDN/FDN client sync is owned by those firmware teams. This app ships the server and operator controls only.

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
