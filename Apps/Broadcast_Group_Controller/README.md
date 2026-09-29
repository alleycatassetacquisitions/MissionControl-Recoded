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

## Panel

Sidebar **Broadcast Groups** — pick a device, set Area and Broadcast Group.
AlleycatTV Player panel does not own placement/membership.
