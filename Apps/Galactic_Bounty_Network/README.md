# Galactic Bounty Network

Poster capture and display for Alleycat. Operators create posters in Home
Assistant; guests see animated pages served from Proxmox. AlleycatTV can play
poster URLs as content.

**Code:** `gbn`  
**Paths:**
- Poster server: [`Server_Component/`](Server_Component/)
- HA integration + panel: [`HA_Component/`](HA_Component/)

**HA shape:** install-only config entry + `/api/gbn/proxy` HTTP views. Panel
never `fetch()`es a LAN URL. Player roster is owned by **Master Control
Server** — GBN stores `player_id` and overlays live name/role/neocorp/faction.

---

## Ownership

| Piece | Owner |
|---|---|
| Player records (name, role, neocorp, faction) | Master Control Server |
| Poster CRUD + video + flavor | GBN server |
| Poster HTML / active-players kiosk | GBN server |
| Capture UI panel | GBN HA panel via proxy |
| Registration Poster column | Registration panel → GBN proxy |

GBN does **not** expose `/api/players`. Use MCS / Registration.

---

## Server env (`GBN_*`)

| Variable | Default | Purpose |
|---|---|---|
| `GBN_HOST` | `0.0.0.0` | Bind address |
| `GBN_PORT` | `8100` | Bind port |
| `GBN_PUBLIC_BASE` | `http://127.0.0.1:8100` | Public URL in poster links |
| `GBN_MEDIA` | `./media` | Videos + NeoCorp SVG assets |
| `GBN_DATA` | `./data` | Data directory |
| `GBN_POSTERS` | `./data/posters.json` | Poster store |
| `GBN_MCS_BASE` | _(empty)_ | MCS base URL for overlay |
| `GBN_MCS_TOKEN` | _(empty)_ | Bearer token for MCS |
| `GBN_ACTIVE_PLAYERS_SECRET` | _(empty)_ | Optional auth for POST active-players |
| `GBN_MAX_UPLOAD_MB` | `100` | Video upload cap |

---

## Quick run (dev)

```powershell
cd Apps\Galactic_Bounty_Network\Server_Component
py -3 -m pip install -r requirements.txt
py -3 -m uvicorn app.main:app --host 127.0.0.1 --port 8100 --reload
```

Health: `GET /health` → `{"status":"ok","service":"gbn"}`

---

## Tests

```powershell
cd Apps\Galactic_Bounty_Network\Server_Component
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
py -3 -m pytest tests -q

cd ..\HA_Component
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
py -3 -m pytest tests -q
```

---

## Deploy

Proxmox: [`ProxmoxInstallFiles/install-gbn-proxmox.sh`](../../ProxmoxInstallFiles/install-gbn-proxmox.sh) ·  
Config steps: [`Docs/GBN Config Steps.md`](../../Docs/GBN%20Config%20Steps.md) ·  
HA Phase 8: [`Docs/Home Assistant Config Steps.md`](../../Docs/Home%20Assistant%20Config%20Steps.md)

Guest install (inside LXC): `sudo bash setup/install-server.sh`  
Installs under `/opt/gbn/`, systemd unit `gbn`. Set Core Configurator key `gbn`
to the public base URL.
