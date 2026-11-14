# Bug Buster

Mission Control ops panel: Proxmox guest console (termproxy), MQTT spy,
companion `/health` checks, and Central device crash logs (via MCS).
**Monitoring sensors and power buttons belong to HA Core
[Proxmox VE](https://www.home-assistant.io/integrations/proxmoxve)** — not this
integration.

**Code:** `bug_buster`  
**Path:** `Apps/Bug_Buster/`  
**HA shape:** config entry + sidebar panel (no Proxmox companion process)

## What it owns

| Feature | Notes |
|---|---|
| Guest list (console picker) | Thin Proxmox API poll — vmid / node / kind / status |
| Termproxy console | xterm.js via HA websocket; inline preview + **Pop out** overlay (reparents the live session) |
| MQTT spy | Debug-only subscribe (default `#`); inline preview + **Pop out** for a larger live stream |
| Companion health | `GET /health` on MCS, AlleycatTV, GBN via `shared_libraries.http` |
| Device logs | WS `bug_buster/device_logs` → MCS `GET /device-logs` (Central crash logs; read-only); inline preview + **Pop out** |

## Credentials

Proxmox URL, node, `token_id`, and `token_secret` live in **Core Configurator**
only. Enter the same API token again when adding Core Proxmox VE for monitoring
entities. Device logs use the **MCS Bearer** (`master_control_server` → API
token) — same token Registration uses. Bug Buster never talks to Central
directly and does not POST logs (devices do that themselves).

## Deploy

```
custom_components/bug_buster/  ← HA_Component/custom_components/bug_buster/
www/bug_buster/                ← HA_Component/www/bug_buster/
```

See [`Docs/Bug Buster Config Steps.md`](../../Docs/Bug%20Buster%20Config%20Steps.md).

---

## Syntax

Stable identity strings for Ctrl+F rename / debug. Prefer changing the named
constant, then searching for leftover literals.

When you rename an identity string, update this section and `const.py` in the same PR.

### Rename blast radius

| Change this | Also touches |
|---|---|
| Domain `bug_buster` | HA `custom_components/` folder, `manifest.json`, entity_id prefix, `www/bug_buster/` |
| CC key `master_control_server` | Bug Buster `KEY_MCS`, Registration `KEY_MCS`, Game Master `KEY_MCS`, DNN `KEY_MCS`, install scripts, secrets |
| MQTT spy default topic `#` | Only `DEFAULT_MQTT_TOPIC` in `const.py` — operator can override at config time |

### Identity checklist

| Kind | Exact string | Constant / source |
|---|---|---|
| HA domain | `bug_buster` | `DOMAIN` in `const.py` |
| CC key (MCS) | `master_control_server` | `KEY_MCS` in `const.py` |
| MQTT spy default | `#` (all topics) | `DEFAULT_MQTT_TOPIC` in `const.py` |
| MQTT buffer size | 200 messages | `MQTT_BUFFER_SIZE` in `const.py` |
| WS (device logs) | `bug_buster/device_logs` | `WS_DEVICE_LOGS` in `const.py` |
| Health probe keys | `master_control_server`, `alleycattv`, `gbn`, `net_time` | `HEALTH_KEYS` tuple in `const.py` |
| Panel url_path | `bug-buster` | bare literal in `HomeAssist/configuration.yaml` |
| Poll interval | 30 s | `POLL_INTERVAL` in `const.py` |
