# Home Assistant Mapping

How Mission Control uses Home Assistant. Product names follow `Design Terms.md`. The build sequence lives on the Mission Control Build Plan canvas, not here.

North star: if it is live venue state, it is a Home Assistant entity. If it is an operator workflow, it is a panel that calls that integration. If it is a file server or Central adapter, it is a Proxmox companion. Feature apps do not grow a second stack.

## What Home Assistant already is

Build on these. A custom MQTT client, a second device list, or a panel that `fetch()`es a LAN server is fighting the platform.

| Need | Home Assistant mechanism | Rule |
| --- | --- | --- |
| MQTT client | `mqtt` integration + official Mosquitto add-on | Do not open a second broker client inside an app; do not ship a custom broker or Proxmox Mosquitto LXC by default |
| HTTP session | `async_get_clientsession` | Do not create a bare `ClientSession` / httpx in integrations |
| Device + Area registry | `device_registry` / `area_registry` | FDN and AlleycatTV Pi go here; placement writes `area_id` |
| State machine | entities | Presence, LED, playback, health — not ad-hoc dicts the panel re-fetches |
| Actions | services + `services.yaml` | e.g. `registration.register_player`, `registration.update_player`, `registration.delete_player`, `registration.sync_now` |
| Operator UI | frontend + `panel_custom` | Panels are views; integrations own I/O |
| Polling | `DataUpdateCoordinator` | Master Control Server / Proxmox / content health — not a home-rolled timer per app |
| Config | config entries + config flow | YAML import is bootstrap only; live source of truth is the entry + Core Configurator |
| Tests | pytest + `hass` fixture | Assert `hass.states` / `hass.services`. Mock HTTP and MQTT. No live broker in CI. |

## What we add (and as what)

| Name | Shape | Job |
| --- | --- | --- |
| Core Configurator | Home Assistant integration `core_configurator` | Exclusive catalog for service URLs and shared API tokens. YAML seeds once; the config entry is live. Callers read `get_url` / `get_extra`. |
| Shared HA helpers | `custom_component` `shared_libraries`, no sidebar | HTTP client (auth included), MQTT fabric helpers, panel kit. Other integrations list `"shared_libraries"` in manifest `dependencies`. Not a product with its own tab. See `Libraries/Shared_HA_Helpers/README.md`. |
| Master Control Server | Proxmox companion service | Only Central HTTP adapter. Owns Player JSON; normalizes Central legacy keys (`allegiance`, `hunter`/`mode`) to canonical `neocorp` / `role`. `GET`/`POST`/`PUT`/`DELETE /players`, `POST /config`. Not a Home Assistant process. |
| Registration | Home Assistant integration `registration` | Home Assistant face of Master Control Server: coordinator, roster sensor, services (`sync_now`, `register_player`, `update_player`, `delete_player`), panel. No Central URL or MCS token of its own — both come from Core Configurator. |
| Digital Node Nexus | Home Assistant integration `digital_node_nexus` | FDN domain: page (primary), LED, haptic. Fabric owns MQTT presence. MCS supplies read-only Player/role/NeoCorp for targeting. Broadcast Group Controller owns placement and membership. |
| AlleycatTV | Home Assistant integration `alleycattv` + Proxmox content server | Playback and content files. Home Assistant is the only MQTT command publisher. Deploy: `Docs/AlleycatTV Config Steps.md`. |
| Galactic Bounty Network | Home Assistant integration `gbn` + Proxmox poster server | Posters and capture. `player_id` is a foreign key to Master Control Server. Panel goes through Home Assistant, not a raw LAN URL. |
| Broadcast Group Controller | Home Assistant integration `broadcast_group_controller` | Physical = Area. Membership = Broadcast Group (BGC Store + MQTT assign). See `Apps/Broadcast_Group_Controller/README.md`. |
| Bug Buster | Home Assistant integration `bug_buster` | Proxmox console (termproxy), MQTT spy, companion health. Reads Proxmox credentials from Core Configurator. Guest sensors/power buttons are Core `proxmoxve`. Ops only. Does not own venue types or tokens. |

Players are not devices. Home Assistant devices are hardware (FDN, Pi, Proxmox guest). A Player is a Central record. Registration must not create one device per Player.

## Platform is done when

True:

- One Core Configurator URL (and shared token where needed) per service
- One HTTP client (auth inside it)
- One MQTT fabric for FDN and AlleycatTV endpoints
- One Player type via Master Control Server
- One Broadcast Group membership list
- Panels call Home Assistant, not LAN IPs
- pytest green in CI for the slice that shipped

False:

- A new app with its own Central fetch
- A second MQTT publish path for the same command
- GBN defining Role
- Digital Node Nexus scraping AlleycatTV for Broadcast Group membership (`/api/zones` or any sibling HTTP)
- `rest.yaml` as a shadow Registration
- Proxmox guests or media files living inside Home Assistant
