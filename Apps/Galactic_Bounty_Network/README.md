# Galactic Bounty Network

Poster capture and display for Alleycat. Operators create posters in Home
Assistant; guests see animated pages served from Proxmox. AlleycatTV can play
poster URLs as content, including `/poster-cycle` to rotate every made poster
every 30 seconds.

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
| Poster chrome templates (headline / labels) | GBN server (`poster_templates.json`) |
| Poster HTML / poster-cycle / active-players kiosk | GBN server |
| Capture UI panel | GBN HA panel via proxy |
| Registration Poster column | Registration panel → GBN proxy |

GBN does **not** expose `/api/players`. Use MCS / Registration.

---

## Poster templates

Chrome (headline, optional subtitle, amount label, list label) is selected at intake:

| Roster role | Template behavior |
|---|---|
| Hunter | Auto-select built-in `hunter` (`GUN FOR HIRE` / `RATE` / `REASONS TO HIRE`) |
| Bounty | Auto-select built-in `bounty` (`WANTED` / `DEAD OR ALIVE` / `REWARD` / `WANTED FOR`) |
| Neither | Operator picks a template or edits chrome and **Save as new** (Create poster also persists a custom template) |

Built-ins cannot be overwritten; **Save as new** always forks. Chrome is **snapshotted** onto each poster at create time. Custom templates keep that snapshot; built-in hunter/bounty chrome follows live MCS role overlays on read.

Panel field **Allegiance/NeoCorp** is the affiliation dropdown (values still `reboot` / `helix` / `endline` / `freelancer`).

API:

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/poster-templates` | List built-ins + customs |
| `POST` | `/api/poster-templates` | Create custom |
| `PUT` / `DELETE` | `/api/poster-templates/{id}` | Non-builtin only |
| `POST` | `/api/posters` | Accepts `template_id` + chrome fields; stores snapshot |

---

## Server env (`GBN_*`)

| Variable | Default | Purpose |
|---|---|---|
| `GBN_HOST` | `0.0.0.0` | Bind address |
| `GBN_PORT` | `8100` | Bind port |
| `GBN_PUBLIC_BASE` | `http://127.0.0.1:8100` | Fallback public URL only — live poster/media links use the request Host (so a new CT IP via Core Configurator is picked up without rewriting this env) |
| `GBN_MEDIA` | `./media` | Videos + NeoCorp SVG assets |
| `GBN_DATA` | `./data` | Data directory |
| `GBN_POSTERS` | `./data/posters.json` | Poster store |
| `GBN_TEMPLATES` | `./data/poster_templates.json` | Poster chrome templates (hunter/bounty built-ins + customs) |
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

### Display URLs

| Path | Purpose |
|---|---|
| `/poster/player/{id}` | Single animated poster |
| `/poster-cycle` | Rotate every made poster (default 30s; `?interval=` 5–300) |
| `/active-players` | Rotate game-server curated `player_ids` only |

AlleycatTV Content **+ Poster cycle** adds `{gbn}/poster-cycle` as a webpage playlist item (1 hour slot). See [`Docs/GBN Config Steps.md`](../../Docs/GBN%20Config%20Steps.md).

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

### Upgrade existing CT (app code only)

Push `Server_Component/app/` (must include `template_store.py` and `routers/templates.py`) into `/opt/gbn/app/`, then `systemctl restart gbn`. Confirm:

```bash
curl -s http://127.0.0.1:8100/api/poster-templates
# JSON array with hunter + bounty — not {"detail":"Not Found"}
curl -s http://127.0.0.1:8100/poster-cycle | head -c 80
# HTML title GBN — Poster Cycle
```

Redeploy `HA_Component/www/gbn/` to Home Assistant and hard-refresh the browser. For AlleycatTV **+ Poster cycle**, also redeploy `Apps/AlleycatTV/HA_Component/www/alleycattv/` to HA `www/`.
