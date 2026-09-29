# Mission Control

Venue operator console for Alleycat events. **Home Assistant** is the control plane: sidebar panels, devices, Areas, services, and automations. Companion services (Master Control Server, AlleycatTV content, GBN posters) run on Proxmox; the MQTT broker is the official **Mosquitto** Home Assistant add-on. HA connects to companions — it does not host them.

This README is the top-level map and getting-started guide. Canonical layouts and naming live in [`Docs/`](Docs/).

---

## Repository map

```text
MissionControl/
├── Apps/                  ← product integrations and companion services
├── Libraries/             ← shared HA infrastructure (not operator products)
├── HomeAssist/            ← merge fragments for HA /config (not a full install)
├── ProxmoxInstallFiles/   ← one-shot scripts run on the Proxmox node shell
├── Docs/                  ← system-wide design law and per-service config steps
├── requirements_test.txt  ← shared pytest deps (dev/CI only; never deploy to HA)
└── .github/workflows/     ← CI
```

| Path | Role |
| --- | --- |
| [`Apps/`](Apps/) | One folder per Mission Control product. Most ship an HA integration; some also ship a Proxmox server or Pi client. |
| [`Libraries/`](Libraries/) | Shared primitives other integrations depend on (HTTP/MQTT helpers, panel kit). No sidebar of their own. |
| [`HomeAssist/`](HomeAssist/) | YAML fragments, secrets example, Alleycat theme, and frontend assets to merge into HAOS `/config/`. |
| [`ProxmoxInstallFiles/`](ProxmoxInstallFiles/) | One-shot host scripts that create the HAOS VM and companion LXCs. Copy to Proxmox `/root/` and run there. |
| [`Docs/`](Docs/) | Design principles, terms, HA/MQTT mapping, file-structure SoT, and deploy config steps. |

Detailed on-disk layout (repo → HA `/config/` → MCS `/opt/mcs/`): [`Docs/File Structure.md`](Docs/File%20Structure.md).

### How an app is usually laid out

| Folder | Purpose |
| --- | --- |
| `HA_Component/` | Home Assistant integration |
| `HA_Component/custom_components/<domain>/` | Python custom component → deploys to `/config/custom_components/` |
| `HA_Component/www/<name>/` | Sidebar panel JS/CSS → deploys to `/config/www/` (served as `/local/...`) |
| `HA_Component/tests/` | pytest for the integration |
| `Server_Component/` | Proxmox companion (FastAPI, content, posters) when the app has one |
| `Client_Component/` | Device/client code (e.g. AlleycatTV Pi player) when the app has one |
| `docs/` / `README.md` | App-local documentation |

Panels talk to **Home Assistant** (services / websocket). They do not `fetch` LAN companion URLs directly. Service URLs and shared tokens live in **Core Configurator**.

---

## Apps at a glance

| App | Path | What it does |
| --- | --- | --- |
| **Core Configurator** | [`Apps/Core_Configurator/`](Apps/Core_Configurator/) | Single catalog of service URLs and API tokens. Other apps call `get_url` / `get_extra` — they do not store their own IPs. |
| **Registration** | [`Apps/Registration/`](Apps/Registration/) | HA face of player roster: add / edit / delete via Master Control Server (never opens a Central socket itself). |
| **Master Control Server** | [`Apps/Master_Control_Server/`](Apps/Master_Control_Server/) | Proxmox FastAPI companion (`/opt/mcs/`). Only Central HTTP adapter. Not an HA process. |
| **Digital Node Nexus** | [`Apps/Digital_Node_Nexus/`](Apps/Digital_Node_Nexus/) | FDN paging / LED / haptic over the MQTT fabric (`mc/dnn`). |
| **AlleycatTV** | [`Apps/AlleycatTV/`](Apps/AlleycatTV/) | Event display playback: HA MQTT commands (`mc/tv`), Proxmox content server, Pi client. |
| **Galactic Bounty Network** | [`Apps/Galactic_Bounty_Network/`](Apps/Galactic_Bounty_Network/) | Bounty posters, boards, and capture (`gbn` + Proxmox poster server). |
| **Broadcast Group Controller** | [`Apps/Broadcast_Group_Controller/`](Apps/Broadcast_Group_Controller/) | Physical placement (HA Areas) and Broadcast Group membership for fabric devices. |
| **Bug Buster** | [`Apps/Bug_Buster/`](Apps/Bug_Buster/) | Ops console: Proxmox guest console, MQTT spy, companion health. Does not own players, groups, or posters. |
| **Meru** | [`Apps/Meru/`](Apps/Meru/) | Local LLM / story agent surface. |

Code domains and forbidden aliases: [`Docs/Design Terms.md`](Docs/Design%20Terms.md).

### Libraries

| Library | Path | What it does |
| --- | --- | --- |
| **Shared HA Helpers** | [`Libraries/Shared_HA_Helpers/`](Libraries/Shared_HA_Helpers/) | Shared HTTP client helpers, MQTT fabric helpers, and Lit panel kit (`panel_kit` → `www/shared_libraries/mc-panel.js`). Other integrations list `shared_libraries` as a manifest dependency. |

### HomeAssist

| Path | Purpose |
| --- | --- |
| [`HomeAssist/configuration.yaml`](HomeAssist/configuration.yaml) | Sections to merge into HA `/config/configuration.yaml` (`frontend`, `panel_custom`, YAML seeds, …). |
| [`HomeAssist/secrets.yaml.example`](HomeAssist/secrets.yaml.example) | Template for `/config/secrets.yaml`. Never commit real secrets. |
| [`HomeAssist/themes/alleycat.yaml`](HomeAssist/themes/alleycat.yaml) | Alleycat cyberpunk theme → `/config/themes/`. |
| [`HomeAssist/www/`](HomeAssist/www/) | `alleycat-scanlines.js`, `custom-sidebar-config.yaml` → `/config/www/`. |

### ProxmoxInstallFiles

One-shot scripts for the **Proxmox node** shell (Datacenter → host → **Shell**). Copy each script to `/root/` first, then run it. Config Steps stay in `Docs/`; these scripts only create VMs/LXCs.

| Script | Creates |
| --- | --- |
| [`install-haos-proxmox.sh`](ProxmoxInstallFiles/install-haos-proxmox.sh) | Home Assistant OS VM (official KVM image) |
| [`install-mcs-proxmox.sh`](ProxmoxInstallFiles/install-mcs-proxmox.sh) | Master Control Server Ubuntu LXC; prints URL + token for Core Configurator |
| [`install-alleycattv-proxmox.sh`](ProxmoxInstallFiles/install-alleycattv-proxmox.sh) | AlleycatTV content LXC (no MQTT); prints Core Configurator URL |
| [`install-gbn-proxmox.sh`](ProxmoxInstallFiles/install-gbn-proxmox.sh) | Galactic Bounty Network poster-server LXC |

Do **not** install Mosquitto as a Proxmox LXC — use the official Mosquitto add-on on HAOS (see Phase 5a in Home Assistant Config Steps).

---

## Architecture (short)

```text
Operators  →  HA panels / services
                 ├─ MQTT  →  FDNs, AlleycatTV Pis   (fabric via Mosquitto add-on)
                 └─ HTTP  →  MCS, AlleycatTV content, GBN, Proxmox APIs

FDNs ↔ Central (HTTP)     MCS ↔ Central (HTTP)
HA never talks to Central directly.
```

- **MQTT** for venue device commands and presence (fan-out, LWT, Broadcast Groups).
- **HTTP** for companion services with a known URL + token from Core Configurator.

Rules: [`Docs/Design Principles.md`](Docs/Design%20Principles.md) · [`Docs/Home Assistant Mapping.md`](Docs/Home%20Assistant%20Mapping.md) · [`Docs/MQTT Communication Principles.md`](Docs/MQTT%20Communication%20Principles.md).

---

## Getting started

### Prerequisites

- A **Proxmox** host on the venue LAN
- This repo checked out on a workstation that can SCP/SSH to Proxmox and the HA VM
- Familiarity with Home Assistant onboarding (user, network, add-ons)

Mission Control assumes **Home Assistant OS** as a Proxmox VM — not Home Assistant Container.

### 1. Stand up Home Assistant

On the **Proxmox node shell** (not a guest console):

1. Copy [`ProxmoxInstallFiles/install-haos-proxmox.sh`](ProxmoxInstallFiles/install-haos-proxmox.sh) to `/root/install-haos-proxmox.sh` on the host.
2. Run:

```bash
bash /root/install-haos-proxmox.sh
```

3. Open `http://homeassistant.local:8123` (or the VM’s IP) and finish onboarding.

Full VM sizing, options, and later HA deploy phases: [`Docs/Home Assistant Config Steps.md`](Docs/Home%20Assistant%20Config%20Steps.md).

### 2. Seed HA config from this repo

On the HA host (SSH as `root`), merge Mission Control fragments into `/config/`:

1. Copy secrets from [`HomeAssist/secrets.yaml.example`](HomeAssist/secrets.yaml.example) → `/config/secrets.yaml` and fill real values.
2. Merge the blocks from [`HomeAssist/configuration.yaml`](HomeAssist/configuration.yaml) into `/config/configuration.yaml`. One `frontend:` block only — extend `extra_module_url` (custom-sidebar → card-mod → scanlines → mc-panel → core-configurator-client); do not paste a duplicate `frontend:` section.
3. Copy theme and www shell assets (`themes/alleycat.yaml`, `www/alleycat-scanlines.js`, `www/custom-sidebar-config.yaml`). Title rename also needs HACS custom-sidebar on `extra_module_url` (see Config Steps Phase 10b).
4. Deploy Shared HA Helpers and Core Configurator (and continue per Config Steps):

```powershell
# From the repo root on your workstation — replace <HA-IP>
scp -r "Libraries\Shared_HA_Helpers\HA_Component\custom_components\shared_libraries" root@<HA-IP>:/config/custom_components/
scp -r "Libraries\Shared_HA_Helpers\HA_Component\www\shared_libraries" root@<HA-IP>:/config/www/
scp -r "Apps\Core_Configurator\HA_Component\custom_components\core_configurator" root@<HA-IP>:/config/custom_components/
scp -r "Apps\Core_Configurator\HA_Component\www\core_configurator" root@<HA-IP>:/config/www/
```

5. Restart Home Assistant (`ha core restart`), add integrations under Devices & services as needed, then hard-refresh the browser.

Repo path → `/config/` mapping: [`Docs/File Structure.md`](Docs/File%20Structure.md).

### 3. Stand up companion LXCs (as needed)

Same pattern for each companion — copy the script to Proxmox `/root/`, run it, then follow the matching Config Steps and paste the printed URL/token into Core Configurator:

| Companion | Install script | Config steps |
| --- | --- | --- |
| Master Control Server | [`install-mcs-proxmox.sh`](ProxmoxInstallFiles/install-mcs-proxmox.sh) | [`Docs/Master Control Server Config Steps.md`](Docs/Master%20Control%20Server%20Config%20Steps.md) |
| AlleycatTV content | [`install-alleycattv-proxmox.sh`](ProxmoxInstallFiles/install-alleycattv-proxmox.sh) | [`Docs/AlleycatTV Config Steps.md`](Docs/AlleycatTV%20Config%20Steps.md) |
| GBN posters | [`install-gbn-proxmox.sh`](ProxmoxInstallFiles/install-gbn-proxmox.sh) | [`Docs/GBN Config Steps.md`](Docs/GBN%20Config%20Steps.md) |

### 4. Add the rest of the HA stack

Typical order (full phase sequence is on the Mission Control Build Plan canvas):

1. **Mosquitto** add-on + HA `mqtt` integration — before DNN / AlleycatTV fabric work
2. **Registration** (after MCS is up)
3. **Digital Node Nexus**, **Broadcast Group Controller**, **AlleycatTV**, **GBN**, **Bug Buster**

App READMEs under `Apps/` and the matching `Docs/* Config Steps.md` cover each slice.

### 5. Develop / test locally

- Integration tests live next to the code (`HA_Component/tests/`, `Server_Component/tests/`).
- From the repo root, install [`requirements_test.txt`](requirements_test.txt), then run `pytest` inside the component folder you changed.
- Lit panel sources live in `Libraries/Shared_HA_Helpers/panel_kit/` — build on the workstation (`npm run build`); HAOS never runs Node. Built assets land under `www/`.

---

## Docs index

| Doc | Use it for |
| --- | --- |
| [`Docs/Design Principles.md`](Docs/Design%20Principles.md) | Nine principles + HA-as-control-plane rules |
| [`Docs/Design Terms.md`](Docs/Design%20Terms.md) | Canonical product / code names |
| [`Docs/Home Assistant Mapping.md`](Docs/Home%20Assistant%20Mapping.md) | Which HA mechanisms we use (and what not to invent) |
| [`Docs/MQTT Communication Principles.md`](Docs/MQTT%20Communication%20Principles.md) | Topic ownership and fabric rules |
| [`Docs/File Structure.md`](Docs/File%20Structure.md) | On-disk SoT for repo, HA `/config/`, and MCS LXC |
| [`Docs/Home Assistant Config Steps.md`](Docs/Home%20Assistant%20Config%20Steps.md) | HAOS VM bootstrap + deploying Mission Control onto HA |
| [`Docs/Master Control Server Config Steps.md`](Docs/Master%20Control%20Server%20Config%20Steps.md) | MCS LXC bootstrap |
| [`Docs/AlleycatTV Config Steps.md`](Docs/AlleycatTV%20Config%20Steps.md) | Content server + HA integration + Pi SD |
| [`Docs/GBN Config Steps.md`](Docs/GBN%20Config%20Steps.md) | Poster server + HA integration |
| [`Docs/Bug Buster Config Steps.md`](Docs/Bug%20Buster%20Config%20Steps.md) | Proxmox monitoring companion on HA |
| [`Docs/Look At Decisions.md`](Docs/Look%20At%20Decisions.md) | Tools used / skipped / deferred (Lit kit + Alleycat shell) |
| [`Apps/Core_Configurator/README.md`](Apps/Core_Configurator/README.md) | First integration: URL/token catalog + panel |

If the file structure changes, update [`Docs/File Structure.md`](Docs/File%20Structure.md) so it still matches reality — that doc is the source of truth for paths.
