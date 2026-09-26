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
| `digital_node_nexus.page` | `cmd/{device\|all\|broadcast/{id}}/page` |
| `digital_node_nexus.set_led` | `cmd/{device\|all}/led` |
| `digital_node_nexus.trigger_haptic` | `cmd/{device\|all}/haptic` |

**Page targeting**

- `device_id` → one FDN  
- `target: all` → every FDN  
- `broadcast_group_id` → Broadcast Group topic (membership is Phase 7)  
- `player_id` / `role` / `neocorp` → stamped into the payload; routes via `cmd/all` when no device/broadcast is set  

Payload schema: [`docs/dnn_commands.proto`](docs/dnn_commands.proto) (HA publishes UTF-8 JSON with the same field names).

---

## Panel

Sidebar panel (`www/digital_node_nexus/dnn-panel.js`):

- Primary: Page composer (FDN / all / broadcast / player / role|NeoCorp filter)
- Secondary tabs: LED, Haptic
- Devices from websocket `digital_node_nexus/get_devices` (fabric presence)
- Roster from `digital_node_nexus/get_roster` (MCS)
- Writes only via `hass.callService` — no LAN `fetch`

---

## File structure

```
HA_Component/
├── custom_components/digital_node_nexus/
│   ├── __init__.py
│   ├── config_flow.py
│   ├── const.py
│   ├── mcs.py
│   ├── payloads.py
│   ├── routing.py
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
