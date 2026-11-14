# Game Master

Sidebar panel for **event management** and **gameplay** controls: create / edit / set-active events, live scoring, delayed scores, affiliation catalog, and (later) hours of operation / special events.

**Registration** is read-only for the active event (roster-gating only). Game Master owns event CRUD so registration-desk staff cannot accidentally change the active event.

Game Master also owns the **affiliation catalog** (create/rename categories and choices) and **HA-only default choice per category** (`game_master.set_default_affiliation`). Defaults prefill Registration's create-player form only; they are not written to Central.

## Architecture

```
Game Master panel → HA websocket/services → MCS → Alleycat Central
```

| MCS route | Central |
|---|---|
| `GET /game-state` | `GET /game-state` |
| `POST /events` | `POST /events` |
| `PATCH /events/{id}` | `PATCH /events/{id}` |
| `PUT /events/{id}/active` | `PUT /events/{id}/active` (+ GBN push) |
| `PUT /scoring` | `PUT /scoring` (active-event scoped) |
| `PUT /delayed-scores` | `PUT /delayed-scores` (active-event scoped) |

## Services

| Service | Purpose |
|---|---|
| `game_master.create_event` | `POST /events` (+ optional set-active) |
| `game_master.update_event` | `PATCH /events/{event_id}` |
| `game_master.set_active_event` | `PUT /events/{event_id}/active` on MCS, then `PUT /api/events/active` on GBN; clears/refetches affiliation catalog |
| `game_master.create_affiliation_category` | Create a new affiliation category on the active event |
| `game_master.rename_affiliation_category` | Rename a category |
| `game_master.create_affiliation` | Create a choice within a category |
| `game_master.rename_affiliation` | Rename a choice |
| `game_master.set_default_affiliation` | Set/clear HA-only default choice per category |

## Websocket

| Type | Purpose |
|---|---|
| `game_master/get_events` | MCS event list (`ready: true` when Central list is up) |
| `game_master/get_game_state` | Active event, scoring, server time from MCS |
| `game_master/set_scoring` | Toggle scoring on/off |
| `game_master/set_delayed_scores` | Toggle delayed-scores acceptance |
| `game_master/get_affiliation_catalog` | Event-keyed catalog with HA-only defaults |

## Install

1. Deploy `HA_Component/custom_components/game_master/` and `www/game_master/`.
2. Add to HA `configuration.yaml`:

```yaml
game_master: {}

panel_custom:
  - name: game-master-panel
    sidebar_title: Game Master
    sidebar_icon: mdi:crown
    url_path: game-master
    module_url: /local/game_master/game-master-panel.js
```

3. Ensure Core Configurator has MCS URL + Bearer token and GBN URL (for active-event push).
4. Restart HA; add the Game Master integration once (or rely on YAML import).

## Gated until Central ships

- Hours of operation
- Special-event triggers

---

## Syntax

Stable identity strings for Ctrl+F rename / debug. Prefer changing the named
constant, then searching for leftover literals.

When you rename an identity string, update this section and `const.py` in the same PR.

### Rename blast radius

| Change this | Also touches |
|---|---|
| Domain `game_master` | HA `custom_components/` folder, `manifest.json`, entity_id prefix, `www/game_master/`, storage key `game_master.events` |
| CC key `master_control_server` | Game Master `KEY_MCS`, plus Registration, Bug Buster, DNN, install scripts |
| CC key `gbn` | Game Master `KEY_GBN`, Registration `KEY_GBN`, Core Configurator catalog |
| Storage key `game_master.events` | HA persistent Store — clearing it loses event list + active event |
| WS `game_master/get_events` | Registration panel (read-only consumer), Game Master panel; **Event CRUD lives here, not Registration** |

### Identity checklist

| Kind | Exact string | Constant / source |
|---|---|---|
| HA domain | `game_master` | `DOMAIN` in `const.py` |
| CC key (MCS) | `master_control_server` | `KEY_MCS` in `const.py` |
| CC key (GBN) | `gbn` | `KEY_GBN` in `const.py` |
| Extra field (MCS token) | `token` | `EXTRA_MCS_TOKEN` in `const.py` |
| Storage key | `game_master.events` | `STORAGE_KEY` in `const.py` |
| WS (events list) | `game_master/get_events` | `WS_GET_EVENTS` in `const.py` — **moved from Registration** |
| WS (game state) | `game_master/get_game_state` | `WS_GET_GAME_STATE` in `const.py` |
| WS (affiliation catalog) | `game_master/get_affiliation_catalog` | `WS_GET_AFFILIATION_CATALOG` in `const.py` |
| Panel url_path | `game-master` | bare literal in `HomeAssist/configuration.yaml` |
| Event ownership | Game Master owns event CRUD | Registration is read-only for the active event |
