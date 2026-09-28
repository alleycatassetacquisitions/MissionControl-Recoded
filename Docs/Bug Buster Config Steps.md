# Bug Buster Config Steps

Bug Buster is the Mission Control ops panel for **Proxmox console** (termproxy),
**MQTT spy**, and **companion `/health`**. Node/VM/LXC sensors and power buttons
come from Home Assistant Core **Proxmox VE** — not from Bug Buster.

## 1. Proxmox API user and token

1. In Proxmox: **Datacenter → Permissions → Groups** — create `HomeAssistant` (or reuse).
2. **Permissions → Add → Group Permission** on path `/`, role:
   - Monitor only: `PVEAuditor`
   - Monitor + power + console: `PVEVMUser` (or a custom role with `VM.Console` / termproxy)
3. **Users → Add** — e.g. `hass` on realm **Proxmox VE authentication** (`pve`).
4. **API Tokens → Add** for that user (Token ID e.g. `missioncontrol`). Copy the secret once.
5. Prefer privilege separation with token-specific permissions if you tighten access later.

You will enter this token **twice**: once in HA Core Proxmox VE, once in Core Configurator.

## 2. HA Core Proxmox VE (monitoring)

1. Settings → Devices & services → **Add Integration** → **Proxmox VE**.
2. Host: IP or hostname only (no `https://`). Port `8006`.
3. Username: `hass` (no `@pve`). Realm: **PVE**.
4. Enable API token. Token ID: the short name only (`missioncontrol`, not `hass@pve!missioncontrol`).
5. Paste Token Secret. Disable SSL verification for LAN self-signed certs if needed.
6. Confirm node and guest entities appear (CPU, memory, status, start/stop buttons).

Docs: [Proxmox VE integration](https://www.home-assistant.io/integrations/proxmoxve).

## 3. Core Configurator (Bug Buster credentials + RTSP)

In the **Core Configurator** sidebar (or YAML seed on first boot):

| Field | Value |
|---|---|
| Proxmox URL | `https://<proxmox-ip>:8006` |
| Node name | e.g. `pve` |
| API token ID | full form `hass@pve!missioncontrol` |
| API token secret | same secret as Proxmox VE |
| Live RTSP | camera/encoder URL, label, enabled (AlleycatTV interrupt) |

Secrets example: [`HomeAssist/secrets.yaml.example`](../HomeAssist/secrets.yaml.example).

## 4. Deploy Bug Buster

```powershell
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Bug_Buster\HA_Component\custom_components\bug_buster" root@<HA-IP>:/config/custom_components/
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Bug_Buster\HA_Component\www\bug_buster" root@<HA-IP>:/config/www/
```

Also redeploy Core Configurator if you have not pulled Proxmox token / RTSP fields yet.

Merge from [`HomeAssist/configuration.yaml`](../HomeAssist/configuration.yaml):

- `bug_buster: {}`
- `panel_custom` entry for **Bug Buster**

Restart Home Assistant. Settings → Devices & services → Add **Bug Buster** if prompted.

## 5. Verify

1. Core Proxmox VE entities update for MCS / AlleycatTV / GBN / HAOS guests.
2. Sidebar **Bug Buster**: guest list loads; double-click opens xterm console.
3. MQTT spy shows broker traffic (debug only — not a command path).
4. Companion health row shows MCS / AlleycatTV / GBN `/health`.

App README: [`Apps/Bug_Buster/README.md`](../Apps/Bug_Buster/README.md)
