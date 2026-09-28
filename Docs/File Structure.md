# File Structure for Mission Control

This is the **source of truth** for how Mission Control is organized on disk.

If you need to change the file structure:

1. Request the change.
2. Get team approval.
3. Make the change.
4. Update this document so it still matches reality.

**Root directory:** `Z:\CodingProjects\Alleycat\MissionControl\`

Mission Control has **three** on-disk layouts you must keep straight:

| Layout | Where | Purpose |
| --- | --- | --- |
| **Repo (GitHub / hard drive)** | This tree under `MissionControl\` | Source of truth for development |
| **Home Assistant runtime** | HAOS `/config/` (see [On Home Assistant](#on-home-assistant)) | What operators actually run |
| **MCS runtime** | Proxmox LXC `/opt/mcs/` | Companion FastAPI service (not HA) |

Copying from repo → HA flattens `HA_Component\custom_components\<domain>\` and `HA_Component\www\<name>\` into `/config/custom_components/` and `/config/www/`. Tests and READMEs stay in the repo only.

## How apps are organized (repo)

Most apps live under `Apps\` and follow the same layout:


| Folder                            | What it is for                               |
| --------------------------------- | -------------------------------------------- |
| `HA_Component\`                   | Home Assistant files for the app             |
| `HA_Component\www\`               | Web files served by Home Assistant           |
| `HA_Component\custom_components\` | Custom Home Assistant components             |
| `HA_Component\tests\`             | pytest tests for the HA component            |
| `Server_Component\`               | Backend or server code, when the app has one |
| `Server_Component\tests\`         | pytest / TestClient tests for the server     |
| `Client_Component\`               | Client code, when the app has one            |
| `docs\`                           | Documentation that belongs only to that app  |

Tests live next to the code they cover. A `tests\` folder is added to the relevant component when that phase ships tests. Do not keep a second copy of URLs, Player types, or MQTT clients outside these folders.

`requirements_test.txt` lives at repo root and is shared by all HA integration test suites. It is developer and CI tooling — it is never deployed to the HA machine.




## Directory tree (repo)

```text
MissionControl\
├── requirements_test.txt              ← dev/CI only; never deployed to the HA machine
├── .github\
│   └── workflows\
│       └── test.yml
├── Apps\
│   ├── AlleycatTV\
│   │   ├── HA_Component\
│   │   │   ├── www\
│   │   │   └── custom_components\
│   │   ├── Server_Component\
│   │   ├── Client_Component\
│   │   └── docs\
│   ├── Bug_Buster\
│   │   └── HA_Component\
│   │       ├── www\
│   │       └── custom_components\
│   ├── Core_Configurator\
│   │   ├── README.md
│   │   └── HA_Component\
│   │       ├── www\
│   │       ├── custom_components\
│   │       └── tests\
│   ├── Digital_Node_Nexus\
│   │   ├── README.md
│   │   ├── docs\
│   │   │   └── dnn_commands.proto
│   │   └── HA_Component\
│   │       ├── www\
│   │       ├── custom_components\
│   │       └── tests\
│   ├── Galactic_Bounty_Network\
│   │   ├── HA_Component\
│   │   │   ├── www\
│   │   │   └── custom_components\
│   │   └── Server_Component\
│   ├── Registration\
│   │   ├── README.md
│   │   └── HA_Component\
│   │       ├── www\registration\
│   │       ├── custom_components\registration\
│   │       └── tests\
│   ├── Master_Control_Server\
│   │   ├── Server_Component\          ← deploys to LXC /opt/mcs/ (not HA)
│   │   │   ├── main.py
│   │   │   ├── models.py
│   │   │   ├── player_normalize.py  ← Central allegiance/hunter → neocorp/role
│   │   │   ├── central_client.py
│   │   │   └── tests\
│   │   └── docs\
│   ├── Meru\
│   │   ├── HA_Component\
│   │   │   ├── www\
│   │   │   └── custom_components\
│   │   └── Server_Component\
│   └── Broadcast_Group_Controller\
│       └── HA_Component\
│           ├── www\
│           └── custom_components\
├── Libraries\
│   └── Shared_HA_Helpers\
│       ├── README.md
│       └── HA_Component\
│           ├── custom_components\
│           │   └── shared_libraries\
│           ├── www\
│           │   └── shared_libraries\
│           └── tests\
├── HomeAssist\                        ← merge fragments for /config (not a full HA install)
│   ├── configuration.yaml
│   ├── secrets.yaml.example
│   └── themes\
└── Docs\
```

## On Home Assistant

After deploy, Mission Control lives under HAOS **`/config/`** (SSH as `root` to the HA host). Repo paths map as follows:

| Repo path | On HA |
| --- | --- |
| `Apps\Core_Configurator\HA_Component\custom_components\core_configurator\` | `/config/custom_components/core_configurator/` |
| `Apps\Core_Configurator\HA_Component\www\core_configurator\` | `/config/www/core_configurator/` |
| `Apps\Registration\HA_Component\custom_components\registration\` | `/config/custom_components/registration/` |
| `Apps\Registration\HA_Component\www\registration\` | `/config/www/registration/` |
| `Apps\Digital_Node_Nexus\HA_Component\custom_components\digital_node_nexus\` | `/config/custom_components/digital_node_nexus/` |
| `Apps\Digital_Node_Nexus\HA_Component\www\digital_node_nexus\` | `/config/www/digital_node_nexus/` |
| `Libraries\Shared_HA_Helpers\HA_Component\custom_components\shared_libraries\` | `/config/custom_components/shared_libraries/` |
| `Libraries\Shared_HA_Helpers\HA_Component\www\shared_libraries\` | `/config/www/shared_libraries/` |
| `HomeAssist\configuration.yaml` (merge sections) | `/config/configuration.yaml` |
| `HomeAssist\secrets.yaml.example` → real secrets | `/config/secrets.yaml` |
| `HomeAssist\themes\` | `/config/themes/` |

Runtime tree (Phase 5 Mission Control slice):

```text
/config/
├── configuration.yaml          ← default_config + frontend.extra_module_url + panel_custom + core_configurator seed
├── secrets.yaml                ← cc_master_control_server, token, central_*, etc.
├── automations.yaml            ← HA defaults (keep)
├── scripts.yaml
├── scenes.yaml
├── themes/
├── custom_components/
│   ├── core_configurator/
│   ├── shared_libraries/
│   ├── registration/
│   └── digital_node_nexus/
└── www/                        ← served as /local/...
    ├── core_configurator/
    │   ├── core-configurator-client.js
    │   └── core-configurator-panel.js
    ├── shared_libraries/
    │   └── mc-panel.js
    ├── registration/
    │   └── registration-panel.js
    └── digital_node_nexus/
        └── dnn-panel.js
```

`frontend.extra_module_url` load order (required):

1. `/local/shared_libraries/mc-panel.js`
2. `/local/core_configurator/core-configurator-client.js`

Master Control Server is **not** under `/config/`. It runs on Proxmox LXC as `/opt/mcs/` (see [`Master Control Server Config Steps.md`](Master%20Control%20Server%20Config%20Steps.md)). HA talks to it over HTTP using the URL + token from Core Configurator.

## Apps



### AlleycatTV

Media distribution system for playing content on many displays during events.
Phase 6: HA integration on the MQTT fabric (`mc/tv`), Proxmox content server
(no MQTT), Pi client, and PC SD distro tool.

**Path:** `Apps\AlleycatTV\`  
**On HA:** `/config/custom_components/alleycattv/` + `/config/www/alleycattv/`  
**App README:** [`Apps/AlleycatTV/README.md`](../Apps/AlleycatTV/README.md)  
**Deploy:** [`Docs/AlleycatTV Config Steps.md`](AlleycatTV%20Config%20Steps.md) · [`Docs/install-alleycattv-proxmox.sh`](install-alleycattv-proxmox.sh)

### Bug Buster

Proxmox guest console (termproxy), MQTT spy, and companion health. Ops only — it does not own players, Broadcast Groups, or posters. Monitoring sensors/power buttons are HA Core Proxmox VE. In code this is `bug_buster`.

**Path:** `Apps\Bug_Buster\`  
**On HA:** `/config/custom_components/bug_buster/` + `/config/www/bug_buster/`  
**App README:** [`Apps/Bug_Buster/README.md`](../Apps/Bug_Buster/README.md)  
**Deploy:** [`Docs/Bug Buster Config Steps.md`](Bug%20Buster%20Config%20Steps.md)

### Core Configurator

Single source of truth for Alleycat service **URLs and API tokens** (MCS URL + Bearer, Central primary/secondary, AlleycatTV, GBN, Proxmox URL/node/token, Live RTSP). Other apps call `get_url` / `get_extra`. In code this is `core_configurator` — not Directory.

**Path:** `Apps\Core_Configurator\`  
**On HA:** `/config/custom_components/core_configurator/` + `/config/www/core_configurator/`

### Digital Node Nexus

Manages communications with FDNs (Fixed Data Nodes). Mission Control talks to FDNs here first, and later to PDNs (Portable Data Nodes) as well. Phase 5 ships a paging-first HA integration on the MQTT fabric; MCS supplies read-only roster for player/role/NeoCorp targeting.

**Path:** `Apps\Digital_Node_Nexus\`  
**On HA:** `/config/custom_components/digital_node_nexus/` + `/config/www/digital_node_nexus/`  
**App README:** [`Apps/Digital_Node_Nexus/README.md`](../Apps/Digital_Node_Nexus/README.md)

### Galactic Bounty Network

Manages bounty posters, bounty boards, and poster capture. In code this is `gbn` — not Photobooth or `bounty`.

**Path:** `Apps\Galactic_Bounty_Network\`  
**On HA:** `/config/custom_components/gbn/` + `/config/www/gbn/`  
**App README:** [`Apps/Galactic_Bounty_Network/README.md`](../Apps/Galactic_Bounty_Network/README.md)  
**Deploy:** [`Docs/GBN Config Steps.md`](GBN%20Config%20Steps.md) · [`Docs/install-gbn-proxmox.sh`](install-gbn-proxmox.sh)

### Registration

Home Assistant face of Master Control Server: roster sensor, services (`sync_now`, `register_player`, `update_player`, `delete_player`), and sidebar panel. Talks only to MCS — never opens a Central socket. MCS URL and token come from Core Configurator.

**Path:** `Apps\Registration\`  
**On HA:** `/config/custom_components/registration/` + `/config/www/registration/`  
**App README:** [`Apps/Registration/README.md`](../Apps/Registration/README.md)

### Master Control Server

Proxmox companion FastAPI service. The only Central HTTP adapter. Normalizes Central legacy fields (`allegiance`, `hunter`/`mode`) to canonical `neocorp` / `role`. Exposes `GET`/`POST`/`PUT`/`DELETE /players` and `POST /config`. Not a Home Assistant process.

**Path:** `Apps\Master_Control_Server\`  
**On LXC:** `/opt/mcs/` (uvicorn via systemd `mcs`)  
**App docs:** [`Apps/Master_Control_Server/docs/README.md`](../Apps/Master_Control_Server/docs/README.md)

### Meru

Talks to Meru, our local LLM agent. Meru is a story component in the overall event narrative.

**Path:** `Apps\Meru\`

### Broadcast Group Controller

Controls Broadcast Group membership and writes Home Assistant Areas for physical placement. In code this is `broadcast_group_controller`. Membership SoR is BGC Store (not HA Labels); devices learn group over MQTT.

**Path:** `Apps\Broadcast_Group_Controller\`
**On HA:** `/config/custom_components/broadcast_group_controller/` + `/config/www/broadcast_group_controller/`

## Other top-level folders



### Libraries

Shared infrastructure that is not an operator-facing product. These are `custom_component` integrations other apps list in their manifest `dependencies`. They have no sidebar, no config flow, and no operator UI.

The same `HA_Component\` layout applies. Tests live in `HA_Component\tests\`.

**Path:** `Libraries\`

#### Shared HA Helpers

Bearer-auth HTTP helper, MQTT fabric helpers (topic builder, subscribe/publish/presence wrappers, status/# → device + presence entity), and a panel CSS/JS kit loaded via `extra_module_url`. Other integrations import helpers directly after declaring `"shared_libraries"` as a manifest dependency.

- **Code:** `shared_libraries`
- **Path:** `Libraries\Shared_HA_Helpers\`
- **On HA:** `/config/custom_components/shared_libraries/` + `/config/www/shared_libraries/`

### HomeAssist

Merge fragments for Mission Control’s HA config (not a complete Home Assistant install). Copy/merge into `/config/` on the appliance.

**Path:** `HomeAssist\`  
**On HA:** see [On Home Assistant](#on-home-assistant)

### Docs

Shared documentation for the Mission Control system. That is this folder.

Standing law:

- `Design Principles.md` — nine principles plus Home Assistant as control plane
- `Design Terms.md` — canonical names
- `Home Assistant Mapping.md` — how Home Assistant is used
- `MQTT Communication Principles.md` — topics and MQTT ownership
- `File Structure.md` — this file (repo **and** HA/LXC layouts)
- `Home Assistant Config Steps.md` — Proxmox VM bootstrap + deploying files onto HA
- `install-haos-proxmox.sh` — one-shot Proxmox host script that downloads the official HAOS KVM image and creates the Home Assistant VM
- `Master Control Server Config Steps.md` — Proxmox LXC bootstrap for Master Control Server
- `install-mcs-proxmox.sh` — one-shot Proxmox host script that creates an Ubuntu 24.04 LXC, installs MCS, and prints URL + token for Core Configurator
- `AlleycatTV Config Steps.md` — Proxmox content server + HA integration + Pi SD flash (Phase 6)
- `install-alleycattv-proxmox.sh` — one-shot Proxmox host script that creates the AlleycatTV content LXC (no MQTT) and prints the Core Configurator URL

Companion services on Proxmox follow the same pattern going forward: `install-<app>-proxmox.sh` plus a matching `* Config Steps.md`. The MQTT broker is an exception — use the official **Mosquitto** Home Assistant add-on (see Phase 5a in `Home Assistant Config Steps.md`), not a Proxmox Mosquitto LXC.

The build-phase sequence stays on the Mission Control Build Plan canvas, not in these files.

**Path:** `Docs\`
