# MQTT Communication Principles

Rules for MQTT communication between Mission Control and other devices.

Topics are **not** hardcoded per device at flash time. Each device builds its own ID topic, shares the same `all` topic, and subscribes to a Broadcast Group topic only after Broadcast Group Controller assigns that group.

## Ownership

- **Broker:** official Mosquitto broker add-on on Home Assistant OS. HA’s `mqtt` integration is the only Mission Control MQTT client path.
- Home Assistant is the **only** MQTT command publisher. The AlleycatTV server must not publish the same commands.
- Apps use Home Assistant’s `mqtt` integration (`async_subscribe` / `async_publish`). Do not open a second broker client inside Data Node Nexus, AlleycatTV, or Bug Buster.
- Status and LWT create a Home Assistant device and a presence entity (`online` / `offline` / `unknown`). Status topics are retained; retiring a device requires clearing that retain (Broadcast Group Controller **Remove from fabric** / `remove_device` on offline devices only).
- Commands target this device, `all`, or a Broadcast Group. Membership comes from Broadcast Group Controller, not from firmware flash and not from a scrape of another app. Membership assign topics are also retained; remove clears them. Delivery policy (D8): (1) retain on assign, (2) republish on offline→online, (3) operator `force_republish_membership` with tv status-JSON ack — no silent periodic watchdog.
- Data Node Nexus owns FDN payloads (LED, haptic, page, protobuf). AlleycatTV owns playback payloads. The MQTT fabric owns presence and routing.

Bug Buster’s MQTT spy is debug-only. It does not become a second command path.

New code uses the `broadcast` topic segment. Do not add `zone` to new topics, attributes, or services.

## Fixed Data Nodes (FDNs)

FDN hardware uses the Data Node Nexus (`dnn`) topic namespace.


| Who it is for | Topic | How it is assigned |
| --- | --- | --- |
| This device | `mc/dnn/cmd/device/{DEVICE_ID}/#` | Built from the node's own ID (same `device` scope as TV) |
| Every FDN | `mc/dnn/cmd/all/#` | The same constant on every FDN, not a per-device list |
| Active alert | `mc/dnn/desired/alert` | One shared name for all nodes |
| This Broadcast Group | `mc/dnn/cmd/broadcast/{id}/#` | Not hardcoded. Broadcast Group Controller assigns the group after the node appears |

**Firmware:** pdn/FDN must subscribe to `mc/dnn/cmd/device/{id}/#` (not the old flat `mc/dnn/cmd/{id}/#`). HA publishers already use the unified grammar.


When a node is moved to a new Broadcast Group, firmware subscribes to the new `cmd/broadcast/{id}/#` topic and unsubscribes from the old one.

Command action segments under those wildcards (Phase 5 DNN):

| Action | Topic suffix | Payload |
| --- | --- | --- |
| Page | `…/page` | JSON `PageCmd` (`text`, `duration`, `scroll`, optional `player_id` / `role` / `neocorp`) |
| LED | `…/led` | JSON `LedCmd` |
| Haptic | `…/haptic` | JSON `HapticCmd` |

Schema SoR: [`Apps/Data_Node_Nexus/docs/dnn_commands.proto`](../Apps/Data_Node_Nexus/docs/dnn_commands.proto) and [`Apps/AlleycatTV/docs/alleycattv.proto`](../Apps/AlleycatTV/docs/alleycattv.proto). HA publishers go through `shared_libraries.mc_codec` (field numbers from those protos). **Default wire is UTF-8 JSON** so current FDN firmware keeps working. **Binary wire** is `MC\x01` + proto3 bytes; Pi (and future FDN) **dual-read** JSON or binary. Flip DNN/ATV publish to `wire="protobuf"` when the fleet is ready — do not dual-publish two payloads on one topic.

## AlleycatTV devices

AlleycatTV Pis use the `tv` topic namespace.


| Who it is for | Topic | How it is assigned |
| --- | --- | --- |
| This device | `mc/tv/cmd/device/{PI_ID}/#` | Built from the Pi's own ID |
| Every Pi | `mc/tv/cmd/all/#` | The same constant on every Pi |
| This Broadcast Group | `mc/tv/cmd/broadcast/{id}/#` | Assigned by Broadcast Group Controller after the Pi is placed, not flashed in |
| Broadcast Group playback | `mc/tv/desired/broadcast/{id}/playback` | Shared desired state for that Broadcast Group |


**Desired vs cmd (D4):** Retained `mc/tv/desired/broadcast/{id}/playback` is the authority for play/stop/volume after reconnect or membership change. `cmd/.../play|stop|volume` remain optional nudges for already-online Pis (HA still publishes both). Interrupt, reload, and cache are cmd-only nudges and do not write desired. On connect / membership resubscribe, the Pi prefers retained desired for a short window and drops duplicate play/stop/volume cmds. Volume updates merge into the retained desired body and must not force `state=playing` on a stopped group.

Command action segments under those wildcards (Phase 6 AlleycatTV):

| Action | Topic suffix | Payload |
| --- | --- | --- |
| Play | `…/play` | JSON `{}` |
| Stop | `…/stop` | JSON `{}` |
| Interrupt | `…/interrupt` | JSON `{"file_url": "…"}` |
| Reload | `…/reload` | JSON `{}` |
| Volume | `…/volume` | JSON `{"volume": 0-100}` |
| Cache | `…/cache_delete` etc. | JSON |

Presence: plain `online` / `offline` (or empty LWT) on `mc/tv/status/{PI_ID}` (**retain=True**). Optional playback telemetry on `mc/tv/status/{PI_ID}/json` (includes `broadcast_group_id` for membership ack). To reuse or drop a Pi ID that no longer publishes, remove it from the fabric while offline (clears the retained status + membership topics).
