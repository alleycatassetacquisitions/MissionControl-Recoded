# Bug Buster

Mission Control ops panel: Proxmox guest console (termproxy), MQTT spy, and
companion `/health` checks. **Monitoring sensors and power buttons belong to
HA Core [Proxmox VE](https://www.home-assistant.io/integrations/proxmoxve)** —
not this integration.

**Code:** `bug_buster`  
**Path:** `Apps/Bug_Buster/`  
**HA shape:** config entry + sidebar panel (no Proxmox companion process)

## What it owns

| Feature | Notes |
|---|---|
| Guest list (console picker) | Thin Proxmox API poll — vmid / node / kind / status |
| Termproxy console | xterm.js via HA websocket |
| MQTT spy | Debug-only subscribe (default `#`) |
| Companion health | `GET /health` on MCS, AlleycatTV, GBN via `shared_libraries.http` |

## Credentials

Proxmox URL, node, `token_id`, and `token_secret` live in **Core Configurator**
only. Enter the same API token again when adding Core Proxmox VE for monitoring
entities.

## Deploy

```
custom_components/bug_buster/  ← HA_Component/custom_components/bug_buster/
www/bug_buster/                ← HA_Component/www/bug_buster/
```

See [`Docs/Bug Buster Config Steps.md`](../../Docs/Bug%20Buster%20Config%20Steps.md).
