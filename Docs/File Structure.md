# File Structure for Mission Control

This is the **source of truth** for how Mission Control is organized on disk.

If you need to change the file structure:

1. Request the change.
2. Get team approval.
3. Make the change.
4. Update this document so it still matches reality.

**Root directory:** `Z:\CodingProjects\Alleycat\MissionControl\`

## How apps are organized

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




## Directory tree

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
│   │   └── HA_Component\
│   │       ├── www\
│   │       ├── custom_components\
│   │       └── tests\                 ← conftest.py + test_core_configurator.py (Phase 2)
│   ├── Digital_Node_Nexus\
│   │   └── HA_Component\
│   │       ├── www\
│   │       └── custom_components\
│   ├── Galactic_Bounty_Network\
│   │   ├── HA_Component\
│   │   │   ├── www\
│   │   │   └── custom_components\
│   │   └── Server_Component\
│   ├── Registration\
│   │   └── HA_Component\
│   │       ├── www\
│   │       └── custom_components\
│   ├── Master_Control_Server\
│   │   ├── Server_Component\
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
├── HomeAssist\
│   └── themes\
└── Docs\
```



## Apps



### AlleycatTV

Media distribution system for playing content on many displays during events.

**Path:** `Apps\AlleycatTV\`

### Bug Buster

Proxmox guest inventory, console, and MQTT spy. Ops only — it does not own players, Broadcast Groups, or posters. In code this is `bug_buster`.

**Path:** `Apps\Bug_Buster\`

### Core Configurator

Holds shared core configuration for Mission Control. Right now this is mainly IP information for the other apps, so addresses are entered in one place instead of copied through the codebase. In code this is `core_configurator` — not Directory.

**Path:** `Apps\Core_Configurator\`

### Digital Node Nexus

Manages communications with FDNs (Fixed Data Nodes). Mission Control talks to FDNs here first, and later to PDNs (Portable Data Nodes) as well.

**Path:** `Apps\Digital_Node_Nexus\`

### Galactic Bounty Network

Manages bounty posters, bounty boards, and poster capture. In code this is `gbn` — not Photobooth or `bounty`.

**Path:** `Apps\Galactic_Bounty_Network\`

### Registration

Talks to the Master Control Server to get current information from the Central Server. Use it to add, edit, and delete player registration information.

**Path:** `Apps\Registration\`

### Master Control Server

Proxmox companion service. Talks directly to the Central Server and is the only Central HTTP adapter. Registration is its Home Assistant UI. This is not a Home Assistant process.

**Path:** `Apps\Master_Control_Server\`

### Meru

Talks to Meru, our local LLM agent. Meru is a story component in the overall event narrative.

**Path:** `Apps\Meru\`

### Broadcast Group Controller

Controls Broadcast Group membership and writes Home Assistant Areas for physical placement. Documented, not built. In code this is `broadcast_group_controller`.

**Path:** `Apps\Broadcast_Group_Controller\`

## Other top-level folders



### HomeAssist

Home Assistant configuration for Mission Control, including themes.

**Path:** `HomeAssist\`

### Docs

Shared documentation for the Mission Control system. That is this folder.

Standing law:

- `Design Principles.md` — nine principles plus Home Assistant as control plane
- `Design Terms.md` — canonical names
- `Home Assistant Mapping.md` — how Home Assistant is used
- `MQTT Communication Principles.md` — topics and MQTT ownership
- `File Structure.md` — this file
- `Home Assistant Config Steps.md` — Proxmox VM bootstrap for Home Assistant
- `install-haos-proxmox.sh` — one-shot Proxmox host script that downloads the official HAOS KVM image and creates the Home Assistant VM

The build-phase sequence stays on the Mission Control Build Plan canvas, not in these files.

**Path:** `Docs\`