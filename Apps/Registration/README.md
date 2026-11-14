# Registration

Home Assistant face of **Master Control Server** for **player roster** management. Operators register and manage players here. Event management (create / edit / set-active) lives on **Game Master** to prevent registration-desk staff from accidentally changing the active event.

**Code:** `registration`  
**Path:** `Apps/Registration/HA_Component/`  
**HA shape:** config entry + sidebar panel + services (no Proxmox companion)

---

## Dependencies

| Dependency | Why |
|---|---|
| Core Configurator | MCS URL (`master_control_server`), MCS Bearer (`extra.token`), `central_primary` / `central_secondary`, GBN URL (`gbn`) for peer snapshot |
| Shared HA Helpers | `async_request`, `mc-panel.js` |
| Master Control Server | Roster + players + teams |
| Game Master | Active-event cache (read-only); affiliation catalog ownership |

Registration never stores the MCS token in its own config entry.

---

## Services

| Service | MCS call |
|---|---|
| `registration.sync_now` | Push `/config` + refresh coordinator (`GET /players`) + affiliation catalog |
| `registration.register_player` | `POST /players` JSON (`name` ≤ 32 chars, optional `email`, optional `affiliations`) |
| `registration.update_player` | `PUT /players/{id}` → Central PATCH (`name`/`email`/`team_id`/`active`/`affiliations`) |
| `registration.delete_player` | `DELETE /players/{id}` → soft-deactivate (`active: false`) |

**Event services (create / update / set_active_event) are on Game Master**, not Registration.

Affiliation **catalog** CRUD and HA-only defaults live on **Game Master** (`game_master.create_affiliation_*`, `set_default_affiliation`). Registration reads the catalog via `game_master/get_affiliation_catalog`.

Register payload: `name` (max 32 characters for device displays) + optional `email` + optional `affiliations` map (category UUID → affiliation UUID). Catalog is **per active event**; HA keeps an event-keyed cache for panels (GBN polls the same WS).

**409** errors from Central (especially `No active event`) are raised as `HomeAssistantError` so the panel can show them.

---

## Websocket

| Type | Purpose |
|---|---|
| `registration/get_roster` | Coordinator-cached players (incl. `affiliations[]`) |
| `registration/get_active_event` | Active event from MCS — read-only; name enriched from Game Master's event cache |
| `registration/get_teams` | Teams for active (or given) event |

Affiliation catalog: `game_master/get_affiliation_catalog` (includes HA-only `default_affiliation_id` per category).

Event list: `game_master/get_events` (not Registration).

---

## Panel

Sidebar panel (`www/registration/registration-panel.js`):

- **Active Event** — read-only display; "open Game Master to manage events" hint
- **Register / Edit player** — same form switches mode; Name + Email + affiliation dropdowns (Faction creatable); edit adds Team + Active
- Create mode prefills category defaults from Game Master when set
- Roster: **PDN**, Name, **Team**, Affiliations (chips), **Status**, Created, Email, Poster; **Edit** + **Deactivate**
- Reads via websocket; writes via HA services only

Load order in `configuration.yaml` `frontend.extra_module_url` (panel kit only — full shell order including custom-sidebar is in [`HomeAssist/configuration.yaml`](../../HomeAssist/configuration.yaml)):

1. `/local/shared_libraries/mc-panel.js`
2. `/local/core_configurator/core-configurator-client.js`

---

## File structure

```
HA_Component/
├── custom_components/registration/
│   ├── __init__.py        setup, services (players only), websocket
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

---

## Syntax

Stable identity strings for Ctrl+F rename / debug. Prefer changing the named
constant, then searching for leftover literals.

When you rename an identity string, update this section and `const.py` in the same PR.

### Rename blast radius

| Change this | Also touches |
|---|---|
| Domain `registration` | HA `custom_components/` folder, `manifest.json`, WS namespace `registration/*`, `www/registration/` |
| CC key `master_control_server` | Registration `KEY_MCS`, Game Master, Bug Buster, DNN, install scripts |
| CC key `gbn` | Registration `KEY_GBN`, Game Master, GBN integration, Core Configurator catalog |
| CC keys `central_primary` / `central_secondary` | Registration `KEY_CENTRAL_PRIMARY` / `KEY_CENTRAL_SECONDARY`; MCS reads these from the peer snapshot |
| Player name max (32) | `PLAYER_NAME_MAX_LEN` — device displays truncate at this boundary; Central also enforces it |

### Identity checklist

| Kind | Exact string | Constant / source |
|---|---|---|
| HA domain | `registration` | `DOMAIN` in `const.py` |
| CC key (MCS) | `master_control_server` | `KEY_MCS` in `const.py` |
| CC key (GBN) | `gbn` | `KEY_GBN` in `const.py` |
| CC key (Central primary) | `central_primary` | `KEY_CENTRAL_PRIMARY` in `const.py` |
| CC key (Central secondary) | `central_secondary` | `KEY_CENTRAL_SECONDARY` in `const.py` |
| CC key (AlleycatTV) | `alleycattv` | `KEY_ALLEYCATTV` in `const.py` — peer snapshot only |
| CC key (Net Time) | `net_time` | `KEY_NET_TIME` in `const.py` — peer snapshot only |
| CC key (Proxmox) | `proxmox` | `KEY_PROXMOX` in `const.py` — host-clock URL derivation |
| Extra field (MCS token) | `token` | `EXTRA_MCS_TOKEN` in `const.py` |
| WS (roster) | `registration/get_roster` | `WS_GET_ROSTER` in `const.py` |
| WS (active event — read only) | `registration/get_active_event` | `WS_GET_ACTIVE_EVENT` in `const.py` |
| WS (teams) | `registration/get_teams` | `WS_GET_TEAMS` in `const.py` |
| Player name max len | `32` | `PLAYER_NAME_MAX_LEN` in `const.py` |
| Panel url_path | `registration` | bare literal in `HomeAssist/configuration.yaml` |
| **Note — no event CRUD** | Registration does **not** own events | Event create/edit/set-active → `Game Master`; event list → `game_master/get_events` |
| **Note — no ROLES** | Registration has **no** `ROLES` constant | Role values come from MCS roster (`hunter` / `bounty` defined in DNN `const.py`) |
