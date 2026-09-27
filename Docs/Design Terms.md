# Design Terms

Shared vocabulary for Mission Control. Use these names in docs, conversations, **and code** so everyone is talking about the same thing.

In the rewrite, use the **final product name** everywhere: sidebar, docs, folders, Home Assistant `domain`, Python packages, JS globals, MQTT namespaces, and tests. Do not keep a second internal nickname.

## Canonical names

Write the product name in prose. In code, use the snake_case form in the table. Abbreviations (DNN, ATV, GBN, MCS) are allowed after the full name has been used, or in MQTT topic prefixes that are already fixed (`mc/dnn`, `mc/tv`).

| Product name | Code (`domain`, package, folder) | Do not use |
| --- | --- | --- |
| Core Configurator | `core_configurator` | Directory, `alleycat_directory`, AlleycatDirectory |
| Digital Node Nexus | `digital_node_nexus` | — |
| AlleycatTV | `alleycattv` | ATV as a folder or domain |
| Galactic Bounty Network | `gbn` | Photobooth, Bounty, `bounty`, ProjectBounty |
| Master Control Server | `master_control_server` | PPS, Player Proxy Service |
| Registration | `registration` | — |
| Bug Buster | `bug_buster` | ProjectBuggy, `bugbuster` |
| Broadcast Group | `broadcast_group` | Zone |
| Broadcast Group Controller | `broadcast_group_controller` | Zone Controller, `zone_controller`, `alleycat_zone` |
| Meru | `meru` | — |
| Shared HA Helpers | `shared_libraries` | — |

Poster capture is part of **Galactic Bounty Network**. It is not a separate Mission Control app named Photobooth. Third-party tools (for example photobooth-app) may be researched for cameras; our product is still GBN.

The endpoint catalog is **Core Configurator**. Say “Core Configurator URL” or `core_configurator` helpers, not “Directory.” Shared API tokens also live in Core Configurator.

Physical place is a Home Assistant **Area**. A content and command membership set is a **Broadcast Group**. Do not call that set a Zone — people will mix it up with Area.

## Devices and systems

### PDN — Portable Data Node

A device players carry and use to play the overall game.

- **Communication:** ESP-Now

### FDN — Fixed Data Node

A device at a fixed location. Players interact with it, and it also acts as a mesh communication hub.

FDNs talk to PDNs, the Central Server, and Home Assistant.

- **Communication:** ESP-Now, HTTP, MQTT

### Core Configurator

The Mission Control app that stores service URLs **and** shared API tokens/auth in one place. Other integrations read `get_url` / `get_extra` instead of keeping their own IPs or credentials.

- **Communication:** Home Assistant config entry + helpers
- **Code:** `core_configurator`

### DNN — Digital Node Nexus

The Mission Control dashboard for sending messages to FDNs and gathering information from them. Phase 5 focuses on **paging** (MQTT page starts an FDN state machine). LED and haptic remain secondary tools. Roster targeting (player / role / NeoCorp) is read from Master Control Server.

- **Communication:** MQTT (JSON payload contract; protobuf schema documented for firmware)
- **Used for:** paging, mini-bosses, quests, and virus
- **Code:** `digital_node_nexus`



### AlleycatTV (ATV)

The media player app used to play content across the event. Phase 6: HA integration on the `mc/tv` fabric; content files on Proxmox; Pis subscribe to HA-published commands only.

- **Communication:** MQTT (HA ↔ Pi), HTTP (HA ↔ content server)
- **Language:** Python
- **Key tools and formats:** MPV, JSON, IPC
- **Used for:** premade content, scoreboards, and RTSP streams to displays around the event
- **Code:** `alleycattv`
- **Deploy:** `Docs/AlleycatTV Config Steps.md`

### GBN — Galactic Bounty Network

The Mission Control app for creating and updating posters that players see on AlleycatTV. Capture hardware and poster intake belong here.

- **Communication:** HTTP
- **Code:** `gbn`

### MCS — Master Control Server

The Proxmox companion that is the only Central HTTP adapter. It owns Player, Role, NeoCorp, and Faction JSON on the Mission Control side of the wire, and maps Central legacy field names on read/write.

Registration is its Home Assistant face. GBN overlays Player data from MCS. Home Assistant does not talk to the Central Server itself.

- **Communication:** HTTP
- **Code:** `master_control_server`

### Registration

The Mission Control dashboard for adding, editing, and deleting player registration information. It talks to MCS (services + panel), not to the Central Server on its own.

- **Code:** `registration`

### Bug Buster

The Mission Control ops tools for monitoring Proxmox guests, health checks, MQTT debug, and SSH into sessions. It reads Proxmox URL/credentials from Core Configurator. It does not own players, Broadcast Groups, posters, or API tokens.

- **Code:** `bug_buster`

### Broadcast Group Controller

Controls Broadcast Group membership for devices across apps, including AlleycatTV endpoints, FDNs, and lighting. It also writes the Home Assistant Area for physical placement.

- **Code:** `broadcast_group_controller`

### Endpoint

An AlleycatTV Pi connected to the network. In Home Assistant it is a device, not a Player.

### Area

Physical placement in Home Assistant (`area_registry`). An FDN or AlleycatTV endpoint belongs to an Area. Lighting and “this room” automations target Areas.

Area is **not** a playlist, interrupt, or command-membership group.

### Broadcast Group

Which endpoints, FDNs, and other devices share the same interrupt, playlist, or command. Broadcast Group Controller owns that list and writes it onto Home Assistant devices (`area_id` plus a `broadcast_group_id` attribute).

Do not call this a Zone. Do not store membership as a Home Assistant Area.

### MQTT fabric

Shared presence and command routing for FDNs and AlleycatTV endpoints, using Home Assistant’s `mqtt` integration against the official **Mosquitto** broker add-on. Status and LWT become presence entities. Commands target this device, `all`, or a Broadcast Group.

Digital Node Nexus and AlleycatTV own payloads (LED, haptic, playback). They do not each open a private MQTT client.

## Players and identity

### Player

A person playing the game. A Player is a Central Server record, served locally by Master Control Server.

Players are **not** Home Assistant devices. Registration exposes connectivity and a roster summary as entities, plus services for operator workflows. Do not create one `device_tracker` (or similar) per Player.

### NeoCorp

A group a player can belong to. Possible NeoCorp values are **Freelancer**, **Helix**, **Endline**, and **Reboot**.

Canonical JSON field: `neocorp` (lowercase on the wire). Central Server historically used `allegiance`; Master Control Server maps between them so Home Assistant never sees `allegiance`.

### Faction

A named group a player can belong to. There is no limit on faction names.

### Role

A field on a Player, owned by Master Control Server / Central Server. Values: **hunter** or **bounty**. Central may send `mode`, `role`, or numeric `hunter` (`1`/`2`); MCS normalizes to `role`. GBN must not define or impersonate Role. GBN stores `player_id` as a foreign key and overlays live Player data from Master Control Server.

### ID

A unique identifier for a player, issued by the Central Server.

### Neo ID

A unique identifier for a player, issued by the NeoBand Server.

### Central Server

The server that stores player data and game data.

### NeoBand Server

The server that stores player data separately from the Central Server.

### Meru

The LLM we are building as an interactive storytelling device for players.

- **Code:** `meru`

## Naming in code

Home Assistant `domain`, Python packages, JS custom elements, websocket APIs, and test module names must match the **Code** column above.

**Example:** `custom_components/core_configurator/`, `hass.data["core_configurator"]`, `window.CoreConfigurator.getUrl`.

**Not:** `alleycat_directory`, `AlleycatDirectory`, `directory-client.js` as the product name.

**Example:** GBN integration domain is `gbn`. Poster capture code lives under GBN, not under a `photobooth` package.

Do **not** use product terms as vague, generic names.

**Example:** an AlleycatTV video player should not be named `player`. Name it something like `alleycattv_media_player`.

**Example:** instead of `ESP32_status`, use something like `FDN_{ID}_status`. That makes it obvious which device on the network is talking.