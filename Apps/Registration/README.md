# Registration

Home Assistant face of **Master Control Server**. Operators manage **events** (including selecting the active registration event) and the **player roster** here. Gameplay toggles (scoring live/off) live on **Game Master**.

**Code:** `registration`  
**Path:** `Apps/Registration/HA_Component/`  
**HA shape:** config entry + sidebar panel + services (no Proxmox companion)

---

## Dependencies

| Dependency | Why |
|---|---|
| Core Configurator | MCS URL (`master_control_server`), MCS Bearer (`extra.token`), `central_primary` / `central_secondary` |
| Shared HA Helpers | `async_request`, `mc-panel.js` |
| Master Control Server | Events + roster + players + teams |

Registration never stores the MCS token in its own config entry.

---

## Services

| Service | MCS call |
|---|---|
| `registration.sync_now` | Push `/config` + refresh coordinator (`GET /players`) |
| `registration.register_player` | `POST /players` JSON (`name`, optional `email`) |
| `registration.create_event` | `POST /events` (+ optional set-active) |
| `registration.update_event` | `PATCH /events/{event_id}` |
| `registration.set_active_event` | `PUT /events/{event_id}/active` |
| `registration.update_player` | `PUT /players/{id}` → Central PATCH (`name`/`email`/`team_id`/`active`) |
| `registration.delete_player` | `DELETE /players/{id}` → soft-deactivate (`active: false`) |

Register payload: `name` + optional `email`. Affiliations (NeoCorp/Faction) wait on Central’s affiliation management API.

**409** errors from Central (especially `No active event`) are raised as `HomeAssistantError` so the panel can show them.

---

## Websocket

| Type | Purpose |
|---|---|
| `registration/get_roster` | Coordinator-cached players |
| `registration/get_events` | MCS event list (`ready: true` when Central list is up) |
| `registration/get_active_event` | Active event from MCS (Central `game-state` backed) |
| `registration/get_teams` | Teams for active (or given) event |

---

## Panel

Sidebar panel (`www/registration/registration-panel.js`):

- **Events strip** — create / edit / set-active + Active indicator
- Register form: **Name** + **Email**
- Roster: **PDN**, Name, **Team**, **Status**, Created, Email, Poster; **Edit** + **Deactivate**
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

Panel TypeScript source: `Libraries/Shared_HA_Helpers/panel_kit/src/panels/registration-panel.ts` (rebuild with `npm run build` in `panel_kit`).
