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
