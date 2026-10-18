# Net Time

LAN time authority for Mission Control venues. Runs on Proxmox as a companion LXC: **chrony** serves NTP/SNTP on UDP 123, and a small management API lets Core Configurator confirm reachability, report public-pool status, and **Sync Now** from an operator PC when the venue has no internet.

PDN/FDN client sync is owned by those firmware teams. This app only ships the server.

## Layout

| Path | Role |
| --- | --- |
| `Server_Component/` | FastAPI management API + chrony helpers |
| `HA_Component/` | Home Assistant bridge (`net_time/*` websocket → management API) |
| `ProxmoxInstallFiles/install-net-time-proxmox.sh` | Creates the privileged LXC |

## Management API

Bearer token: `NET_TIME_API_TOKEN` (same value as Core Configurator `net_time` token).

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health` | no | Liveness |
| `GET` | `/status` | yes | Clock, stratum, public NTP reachable/unavailable |
| `POST` | `/sync` | yes | Set clock from `{ "iso8601": "..." }` (operator PC time) |

Default bind: `0.0.0.0:8720`.

## Deploy

See `Docs/Net Time Config Steps.md`. On the Proxmox host:

```bash
bash install-net-time-proxmox.sh
```

Paste the printed `cc_net_time` URL and token into Core Configurator.

## Local tests

```bash
cd Apps/Net_Time/Server_Component
pip install -e ".[test]"
pytest
```
