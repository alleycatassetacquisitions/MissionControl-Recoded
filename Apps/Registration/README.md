# Registration

Home Assistant face of **Master Control Server**. Operators manage the player roster here; MCS is the only process that talks to Central Server.

**Code:** `registration`  
**Path:** `Apps/Registration/HA_Component/`  
**HA shape:** config entry + sidebar panel + services (no Proxmox companion)

---

## Dependencies

| Dependency | Why |
|---|---|
| Core Configurator | MCS URL (`master_control_server`), MCS Bearer (`extra.token`), `central_primary` / `central_secondary` |
| Shared HA Helpers | `async_request`, `mc-panel.js` |
| Master Control Server | Roster + create/update/delete |

Registration never stores the MCS token in its own config entry.

---

## Services

| Service | MCS call |
|---|---|
| `registration.sync_now` | Refresh coordinator (`GET /players`) |
| `registration.register_player` | `POST /players` |
| `registration.update_player` | `PUT /players/{player_id}` |
| `registration.delete_player` | `DELETE /players/{player_id}` |

Canonical payload fields: `name`, `role` (`hunter` \| `bounty`), `neocorp` (lowercase: `freelancer` \| `helix` \| `endline` \| `reboot`), `faction`, `neo_id`.

---

## Panel

Sidebar panel (`www/registration/registration-panel.js`):

- Labeled form (Name, Role, NeoCorp, Faction, Neo ID)
- Role / NeoCorp dropdowns (Freelancer default)
- Roster table with Edit / Delete
- Reads via websocket `registration/get_roster` (coordinator cache)
- Writes via HA services only — no direct LAN `fetch`

Load order in `configuration.yaml` `frontend.extra_module_url` (panel kit only — full shell order including custom-sidebar is in [`HomeAssist/configuration.yaml`](../../HomeAssist/configuration.yaml)):

1. `/local/shared_libraries/mc-panel.js`
2. `/local/core_configurator/core-configurator-client.js`

---

## File structure

```
HA_Component/
├── custom_components/registration/
│   ├── __init__.py        setup, services, websocket, Central URL push
│   ├── coordinator.py     polls MCS GET /players
│   ├── sensor.py          roster count + attributes
│   ├── config_flow.py     install-only
│   ├── const.py
│   ├── services.yaml
│   ├── strings.json
│   └── manifest.json
├── www/registration/
│   └── registration-panel.js
└── tests/
```

---

## Deploy (HA)

```powershell
scp -r "Apps\Registration\HA_Component\custom_components\registration" root@<HA-IP>:/config/custom_components/
scp -r "Apps\Registration\HA_Component\www\registration" root@<HA-IP>:/config/www/
```

Then `ha core restart` and hard-refresh the browser.

## Deploy (MCS — field mapping + write API)

From the **Proxmox host** (not the LXC console):

```powershell
scp "Apps\Master_Control_Server\Server_Component\player_normalize.py" root@<PROXMOX-IP>:/root/
scp "Apps\Master_Control_Server\Server_Component\central_client.py" root@<PROXMOX-IP>:/root/
scp "Apps\Master_Control_Server\Server_Component\models.py" root@<PROXMOX-IP>:/root/
scp "Apps\Master_Control_Server\Server_Component\main.py" root@<PROXMOX-IP>:/root/
```

```bash
pct push 102 /root/player_normalize.py /opt/mcs/player_normalize.py
pct push 102 /root/central_client.py /opt/mcs/central_client.py
pct push 102 /root/models.py /opt/mcs/models.py
pct push 102 /root/main.py /opt/mcs/main.py
pct exec 102 -- systemctl restart mcs
```
