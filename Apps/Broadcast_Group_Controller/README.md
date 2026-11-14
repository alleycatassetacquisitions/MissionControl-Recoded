# Broadcast Group Controller

Home Assistant integration that owns **physical placement** (HA Area) and
**Broadcast Group membership** for fabric devices (AlleycatTV Pis and FDNs).

**Code:** `broadcast_group_controller`  
**Path:** `Apps/Broadcast_Group_Controller/`

## Membership storage decision (Phase 7 spike)

**Choice: BGC Store + device registry `area_id` — not HA Labels.**

| Candidate | Why rejected / accepted |
|---|---|
| **HA Labels** | A device can hold many labels; membership must be exclusive (one Broadcast Group). Label ids are opaque UUIDs, not the operator-facing `broadcast_group_id` used in `mc/{kind}/cmd/broadcast/{id}/#`. Labels are not scoped by fabric kind (`tv` / `dnn`). |
| **BGC Store** | Single map `(kind, device_id) → {area_id, broadcast_group_id}`. Writes HA `area_id` on the fabric device. Publishes membership over MQTT so Pis/FDNs resubscribe. |

Playlist *buckets* (content for id `lobby`) stay on the AlleycatTV content server.
BGC only assigns devices *to* those ids.

## MQTT membership assign

```
mc/{kind}/cmd/device/{device_id}/membership
{"broadcast_group_id": "lobby"}   # or null / "" to clear
```

Messages are published with **retain=True** so a rebooting device re-learns its
group from the broker. BGC also watches `mc/{kind}/status/#` and **republishes**
stored membership when a device transitions to online (covers clients that miss
retain or still have a stale env bootstrap).

- **tv:** Pi client updates `BROADCAST_GROUP_ID`, resubscribes `cmd/broadcast/{id}/#` + desired playback, reflects group in status JSON.
- **dnn:** FDN firmware should honor the same topic when present; HA stores membership for operator UI regardless.

## Services

| Service | Purpose |
|---|---|
| `set_area` | Write HA Area on a fabric device |
| `set_broadcast_group` | Assign membership + MQTT notify |
| `clear_broadcast_group` | Clear membership + MQTT notify |
| `remove_device` | Delete an **offline** fabric device (HA device + retained MQTT status/membership) so the id can be reused or retired |

Online devices cannot be removed — stop the Pi/FDN (or wait for LWT) first.

## Panel

Sidebar **Broadcast Groups** — pick a device, set Area and Broadcast Group.
Broadcast Group ID is a dropdown of AlleycatTV Content playlist buckets
(plus any ids already assigned in BGC). Create buckets in **AlleycatTV Content**,
then Refresh this panel.
Use **Remove from fabric** on offline chips to drop unused names.
AlleycatTV Player panel does not own placement/membership.

## Websocket commands

| Type | Returns |
|---|---|
| `broadcast_group_controller/list_devices` | Fabric devices + presence + membership |
| `broadcast_group_controller/list_areas` | HA areas |
| `broadcast_group_controller/list_broadcast_groups` | Content-server buckets + assigned ids (for the dropdown) |
| `broadcast_group_controller/get_membership` | Raw BGC Store map |

## Deploy note

Copy **both** `custom_components/broadcast_group_controller` and `www/broadcast_group_controller`, then `ha core restart`. A www-only refresh leaves the new websocket unregistered (`Unknown command` / empty group dropdown). When `fabric.py` changed for forget/remove, also redeploy Shared HA Helpers.

---

## Syntax

Stable identity strings for Ctrl+F rename / debug. Prefer changing the named
constant, then searching for leftover literals.

When you rename an identity string, update this section and `const.py` in the same PR.

### Rename blast radius

| Change this | Also touches |
|---|---|
| Domain `broadcast_group_controller` | HA `custom_components/` folder, `manifest.json`, entity_id prefix, `www/broadcast_group_controller/`, storage key |
| Fabric kind `tv` | Shared here as `KIND_TV`; also `MQTT_KIND` in AlleycatTV, all `mc/tv/…` MQTT topics |
| Fabric kind `dnn` | Shared here as `KIND_DNN`; also `MQTT_KIND` in DNN, all `mc/dnn/…` MQTT topics |
| Storage key `broadcast_group_controller.membership` | HA Store — clearing it loses all area/group assignments |

### Identity checklist

| Kind | Exact string | Constant / source |
|---|---|---|
| HA domain | `broadcast_group_controller` | `DOMAIN` in `const.py` |
| TV fabric kind | `tv` | `KIND_TV` in `const.py` |
| DNN fabric kind | `dnn` | `KIND_DNN` in `const.py` |
| Storage key | `broadcast_group_controller.membership` | `STORAGE_KEY` in `const.py` |
| MQTT membership topic | `mc/{kind}/cmd/device/{id}/membership` | built via `mc_topic` in `Shared_HA_Helpers` — uses retained=True |
| WS namespace | `broadcast_group_controller/list_devices`, `.../list_areas`, `.../list_broadcast_groups`, `.../get_membership` | `WS_*` in `const.py` |
| Panel url_path | `broadcast-groups` | bare literal in `HomeAssist/configuration.yaml` |
