# Bug Buster Config Steps

Bug Buster is the Mission Control ops panel for **Proxmox console** (termproxy),
**MQTT spy**, **companion `/health`**, and **Central device crash logs** (via
MCS `GET /device-logs`). Node/VM/LXC sensors and power buttons come from Home
Assistant Core **Proxmox VE** — not from Bug Buster.

## 1. Proxmox API user and token

1. In Proxmox: **Datacenter → Permissions → Groups** — create `HomeAssistant` (or reuse).
2. **Permissions → Add → Group Permission** on path `/`, role:
   - Monitor only: `PVEAuditor`
   - Monitor + power + console: `PVEVMUser` (or a custom role with `VM.Console` / termproxy)
3. **Users → Add** — e.g. `hass` on realm **Proxmox VE authentication** (`pve`).
4. **API Tokens → Add** for that user (Token ID e.g. `missioncontrol`). Copy the secret once.
5. Prefer privilege separation with token-specific permissions if you tighten access later.

**Source of truth:** paste the token into **Core Configurator** (full id `hass@pve!missioncontrol`). Bug Buster reads that for console. Core Configurator **one-shots** HA Core **Proxmox VE** for monitoring when URL + token are saved (idempotent if an entry for that host already exists). Do not dual-enter on every rotate: update Core Configurator first; only reconfigure Proxmox VE if monitoring stays broken after Save.

## 2. Core Configurator (token SoR + RTSP)

In the **Core Configurator** sidebar (or YAML seed on first boot):

| Field | Value |
|---|---|
| Proxmox URL | `https://<proxmox-ip>:8006` |
| Node name | e.g. `pve` |
| API token ID | full form `hass@pve!missioncontrol` |
| API token secret | the secret from step 1 |
| Live RTSP | camera/encoder URL, label, enabled (AlleycatTV interrupt) |

Secrets example: [`HomeAssist/secrets.yaml.example`](../HomeAssist/secrets.yaml.example).

## 3. HA Core Proxmox VE (monitoring)

Saving Proxmox URL + `hass@pve!missioncontrol` + secret in **Core Configurator** creates the Core **Proxmox VE** entry once (HA 2026.3+ with API-token support). Confirm node/guest entities appear after Save.

**Manual fallback** (bootstrap skipped — Proxmox unreachable, old HA, or entry already present under another host string):

1. Settings → Devices & services → **Add Integration** → **Proxmox VE**.
2. Host: IP or hostname only (no `https://`). Port `8006`.
3. Username: `hass` (no `@pve`). Realm: **PVE**.
4. Enable API token. Token ID: short name only (`missioncontrol`).
5. Same Token Secret as Core Configurator. Disable SSL verify for LAN self-signed certs if needed.

Docs: [Proxmox VE integration](https://www.home-assistant.io/integrations/proxmoxve).

## 4. Deploy Bug Buster

```powershell
# Rebuild panel first (from panel_kit): npm run build
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Bug_Buster\HA_Component\custom_components\bug_buster" root@<HA-IP>:/config/custom_components/
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Bug_Buster\HA_Component\www\bug_buster" root@<HA-IP>:/config/www/
```

Also redeploy Core Configurator if you have not pulled Proxmox token / RTSP / MCS Bearer fields yet. Device logs need the same MCS URL + token Registration uses.

Merge from [`HomeAssist/configuration.yaml`](../HomeAssist/configuration.yaml):

- `bug_buster: {}`
- `panel_custom` entry for **Bug Buster**

Restart Home Assistant. Settings → Devices & services → Add **Bug Buster** if prompted.

## 5. Verify

1. Core Proxmox VE entities update for MCS / AlleycatTV / GBN / HAOS guests.
2. Sidebar **Bug Buster**: guest list loads; select a guest and **Connect** opens the xterm console.
3. MQTT spy defaults to `mc/#`; use AlleycatTV / FDN filter buttons to slice the live stream (debug only — not a command path).
4. Companion health row shows MCS / AlleycatTV / GBN `/health`.
5. **Device logs** pane loads (or a clear MCS token/URL error). Refresh / Prev / Next page Central crash rows. Bug Buster never POSTs logs — devices do.
6. **Pop out** on MQTT, Device logs, and Console: each opens a larger in-panel overlay; Close or Escape dismisses it. For Console, confirm the session returns to the inline pane after close.

App README: [`Apps/Bug_Buster/README.md`](../Apps/Bug_Buster/README.md)
