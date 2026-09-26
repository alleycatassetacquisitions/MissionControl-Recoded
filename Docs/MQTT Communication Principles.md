# MQTT Communication Principles

Rules for MQTT communication between Mission Control and other devices.

Topics are **not** hardcoded per device at flash time. Each device builds its own ID topic, shares the same `all` topic, and subscribes to a Broadcast Group topic only after Broadcast Group Controller assigns that group.

## Ownership

- **Broker:** official Mosquitto broker add-on on Home Assistant OS. HA’s `mqtt` integration is the only Mission Control MQTT client path.
- Home Assistant is the **only** MQTT command publisher. The AlleycatTV server must not publish the same commands.
- Apps use Home Assistant’s `mqtt` integration (`async_subscribe` / `async_publish`). Do not open a second broker client inside Digital Node Nexus, AlleycatTV, or Bug Buster.
- Status and LWT create a Home Assistant device and a presence entity (`online` / `offline` / `unknown`).
- Commands target this device, `all`, or a Broadcast Group. Membership comes from Broadcast Group Controller, not from firmware flash and not from a scrape of another app.
- Digital Node Nexus owns FDN payloads (LED, haptic, page, protobuf). AlleycatTV owns playback payloads. The MQTT fabric owns presence and routing.

Bug Buster’s MQTT spy is debug-only. It does not become a second command path.

New code uses the `broadcast` topic segment. Do not add `zone` to new topics, attributes, or services.

## Fixed Data Nodes (FDNs)

FDN hardware uses the Digital Node Nexus (`dnn`) topic namespace.


| Who it is for | Topic | How it is assigned |
| --- | --- | --- |
| This device | `mc/dnn/cmd/{DEVICE_ID}/#` | Built from the node's own ID |
| Every FDN | `mc/dnn/cmd/all/#` | The same constant on every FDN, not a per-device list |
| Active alert | `mc/dnn/desired/alert` | One shared name for all nodes |
| This Broadcast Group | `mc/dnn/cmd/broadcast/{id}/#` | Not hardcoded. Broadcast Group Controller assigns the group after the node appears |


When a node is moved to a new Broadcast Group, firmware subscribes to the new `cmd/broadcast/{id}/#` topic and unsubscribes from the old one.

Command action segments under those wildcards (Phase 5 DNN):

| Action | Topic suffix | Payload |
| --- | --- | --- |
| Page | `…/page` | JSON `PageCmd` (`text`, `duration`, `scroll`, optional `player_id` / `role` / `neocorp`) |
| LED | `…/led` | JSON `LedCmd` |
| Haptic | `…/haptic` | JSON `HapticCmd` |

Schema: [`Apps/Digital_Node_Nexus/docs/dnn_commands.proto`](../Apps/Digital_Node_Nexus/docs/dnn_commands.proto). HA publishes UTF-8 JSON with those field names; firmware may later switch to binary protobuf using the same field numbers.

## AlleycatTV devices

AlleycatTV Pis use the `tv` topic namespace.


| Who it is for | Topic | How it is assigned |
| --- | --- | --- |
| This device | `mc/tv/cmd/device/{PI_ID}/#` | Built from the Pi's own ID |
| Every Pi | `mc/tv/cmd/all/#` | The same constant on every Pi |
| This Broadcast Group | `mc/tv/cmd/broadcast/{id}/#` | Assigned by Broadcast Group Controller after the Pi is placed, not flashed in |
| Broadcast Group playback | `mc/tv/desired/broadcast/{id}/playback` | Shared desired state for that Broadcast Group |


The playback topic exists so a Pi that was powered off can still start in the right state. When it comes online, it should already be playing or stopped at the Broadcast Group's current volume.
