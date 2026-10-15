# Registration

Home Assistant face of **Master Control Server**. Operators manage events and the player roster here; MCS is the only process that talks to Central Server.

**Code:** `registration`  
**Path:** `Apps/Registration/HA_Component/`  
**HA shape:** config entry + sidebar panel + services (no Proxmox companion)

---

## Dependencies

| Dependency | Why |
|---|---|
| Core Configurator | MCS URL (`master_control_server`), MCS Bearer (`extra.token`), `central_primary` / `central_secondary` |
| Shared HA Helpers | `async_request`, `mc-panel.js` |
| Master Control Server | Events + roster + create player |

Registration never stores the MCS token in its own config entry.

---

## Services

| Service | MCS call |
|---|---|
| `registration.sync_now` | Push `/config` + refresh coordinator (`GET /players`) |
| `registration.register_player` | `POST /players` (`name`, optional `email`) |
| `registration.create_event` | `POST /events` (+ optional `?set_active=true`) |
| `registration.update_event` | `PATCH /events/{event_id}` |
| `registration.set_active_event` | `PUT /events/{event_id}/active` |
| `registration.update_player` | **501** until Central ships update |
| `registration.delete_player` | **501** until Central ships delete |

Register payload: `name` + optional `email`. NeoCorp / faction / neo_id are **not** written (pending Central restore or MC deprecation).

**409** errors from Central (especially `No active event`) are raised as `HomeAssistantError` so the panel can show them.

---

## Websocket

| Type | Purpose |
|---|---|
| `registration/get_roster` | Coordinator-cached players |
| `registration/get_events` | MCS list when ready; else `{ready:false}` + session cache of created/updated events |
| `registration/get_active_event` | MCS last-known active (`source: mcs_memory` until Central get-active) |

---

## Panel

Sidebar panel (`www/registration/registration-panel.js`):

- **Events strip** — create / edit / set-active + Active indicator
- Register form: **Name** + **Email**
- Roster: **PDN**, Name, Mode, Created, Email, Poster; Edit/Delete disabled with tooltip
- Reads via websocket; writes via HA services only

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

Rebuild the panel first (from repo root / panel_kit):

```powershell
cd Libraries\Shared_HA_Helpers\panel_kit
npm run build
```

Then copy to HA:

```powershell
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Registration\HA_Component\custom_components\registration" root@<HA-IP>:/config/custom_components/
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\Registration\HA_Component\www\registration" root@<HA-IP>:/config/www/
```

Then `ha core restart` and hard-refresh the browser.
