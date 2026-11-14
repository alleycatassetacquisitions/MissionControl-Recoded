# Digital Node Nexus

Home Assistant face of the FDN MQTT fabric. Operators **page** players and
devices here; LED and haptic are secondary skeleton tools.

**Code:** `digital_node_nexus`  
**Path:** `Apps/Digital_Node_Nexus/HA_Component/`  
**HA shape:** config entry + sidebar panel + MQTT services (`local_push`)

---

## Dependencies

| Dependency | Why |
|---|---|
| Official **Mosquitto broker** add-on | Venue MQTT broker on HAOS — install before DNN |
| HA `mqtt` integration | Client path for subscribe/publish (auto-wire to Mosquitto add-on) |
| Shared HA Helpers | MQTT publish, fabric presence (`mc/dnn/status/#`) |
| Core Configurator | MCS URL + Bearer for roster targeting |
| Master Control Server | Read-only `GET /players` for player / role / NeoCorp pickers |

DNN never talks to Central Server. Registration owns player writes. DNN never opens a private MQTT socket — only HA’s `mqtt` integration against Mosquitto.

---

## Services

| Service | MQTT topic (under `mc/dnn/`) |
|---|---|
| `digital_node_nexus.page` | `cmd/device/{id}/page` · `cmd/all/page` · `cmd/broadcast/{id}/page` |
| `digital_node_nexus.set_led` | `cmd/device/{id}/led` · `cmd/all/led` |
| `digital_node_nexus.trigger_haptic` | `cmd/device/{id}/haptic` · `cmd/all/haptic` |

**Page targeting**

- `device_id` → one FDN  
- `target: all` → every FDN  
- `broadcast_group_id` → Broadcast Group topic (membership owned by **Broadcast Group Controller**)

**Membership assign (Phase 7):** BGC publishes

```
mc/dnn/cmd/device/{device_id}/membership
{"broadcast_group_id": "lobby" | null}
```

FDN firmware must subscribe to `mc/dnn/cmd/device/{id}/#` (same `device` scope as AlleycatTV) and resubscribe to `mc/dnn/cmd/broadcast/{id}/#` when membership arrives.
Placement and membership are set in the Broadcast Groups sidebar — not in DNN.

- `player_id` / `role` / `neocorp` → stamped into the payload; routes via `cmd/all` when no device/broadcast is set  

Payload schema: [`docs/dnn_commands.proto`](docs/dnn_commands.proto) (HA publishes UTF-8 JSON with the same field names).

---

## Panel

Sidebar panel (`www/digital_node_nexus/dnn-panel.js`):

- Primary: Page composer (FDN / all / broadcast / player / role|NeoCorp filter)
- Secondary tabs: LED, Haptic
- Devices from websocket `digital_node_nexus/get_devices` (fabric presence)
- Roster from `registration/get_roster` (Registration SoR)
- Writes only via `hass.callService` — no LAN `fetch`

---

## File structure

```
HA_Component/
├── custom_components/digital_node_nexus/
│   ├── __init__.py
│   ├── config_flow.py
│   ├── const.py
│   ├── payloads.py
│   ├── services.yaml
│   ├── strings.json
│   └── manifest.json
├── www/digital_node_nexus/
│   └── dnn-panel.js
└── tests/
docs/
└── dnn_commands.proto
```

---

## Deploy (HA)

1. Install **Mosquitto broker** add-on + **MQTT** integration — see Phase 5a in [`Docs/Home Assistant Config Steps.md`](../../Docs/Home%20Assistant%20Config%20Steps.md).
2. Copy the integration and panel:

```powershell
scp -r "Apps\Digital_Node_Nexus\HA_Component\custom_components\digital_node_nexus" root@<HA-IP>:/config/custom_components/
scp -r "Apps\Digital_Node_Nexus\HA_Component\www\digital_node_nexus" root@<HA-IP>:/config/www/
```

Also redeploy Shared HA Helpers if `fabric.py` / `mqtt.py` changed. Merge the `panel_custom` block from `HomeAssist/configuration.yaml`, then `ha core restart`, add **Digital Node Nexus** from Devices & services, and hard-refresh the browser.

---

## Syntax

Stable identity strings for Ctrl+F rename / debug. Prefer changing the named
constant, then searching for leftover literals.

When you rename an identity string, update this section and `const.py` in the same PR.

### Rename blast radius

| Change this | Also touches |
|---|---|
| MQTT kind `dnn` | BGC `KIND_DNN` + `KIND_DOMAIN` map, fabric `mc/dnn/status/#` subscriptions, FDN firmware MQTT topics, all DNN MQTT command topics |
| Roster WS `registration/get_roster` | DNN panel page targets (Registration owns MCS roster poll) |
| Domain `digital_node_nexus` | HA `custom_components/` folder, `manifest.json`, entity_id prefix, `www/digital_node_nexus/` |
| Role strings (`hunter`, `bounty`) | DNN `ROLES` tuple — DNN only; Registration has **no** `ROLES` constant |

### Identity checklist

| Kind | Exact string | Constant / source |
|---|---|---|
| HA domain | `digital_node_nexus` | `DOMAIN` in `const.py` |
| MQTT fabric kind | `dnn` | `MQTT_KIND` in `const.py` |
| Roster (panel) | `registration/get_roster` | Registration WS — DNN does not own an MCS client |
| Extra field (MCS token) | `token` | `EXTRA_MCS_TOKEN` in `const.py` |
| Role values | `hunter`, `bounty` | `ROLES` tuple in `const.py` — DNN only |
| NeoCorp values | `freelancer`, `helix`, `endline`, `reboot` | `NEOCORPS` tuple in `const.py` |
| WS namespace | `digital_node_nexus/get_devices` | `WS_GET_DEVICES` in `const.py` |
| Panel url_path | `digital-node-nexus` | bare literal in `HomeAssist/configuration.yaml` |
| MQTT topic root | `mc/dnn/cmd/device/…`, `mc/dnn/status/…` | `mc_topic` + `resolve_cmd_segments` in `Shared_HA_Helpers` |
| Device cmd grammar | `mc/{kind}/cmd/device/{id}/…` | shared with AlleycatTV / BGC — FDN firmware must match |
