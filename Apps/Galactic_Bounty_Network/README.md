# Galactic Bounty Network

Poster capture and display for Alleycat. Operators create posters in Home
Assistant; guests see animated pages served from Proxmox. AlleycatTV can play
poster URLs as content, including `/poster-cycle` to rotate **active-event**
posters every 30 seconds.

**Code:** `gbn`  
**Paths:**
- Poster server: [`Server_Component/`](Server_Component/)
- HA integration + panel: [`HA_Component/`](HA_Component/)

**HA shape:** install-only config entry + `/api/gbn/proxy` HTTP views. Panel
never `fetch()`es a LAN URL. Player roster is owned by **Master Control
Server** — GBN stores `player_id` and overlays live name/role/affiliations (plus legacy neocorp/faction).

---

## Ownership

| Piece | Owner |
|---|---|
| Player records (name, role, affiliations) | Master Control Server / Central |
| Affiliation catalog (per active event) | Central via MCS; Game Master HA event-keyed cache (`game_master/get_affiliation_catalog`); MCS `POST /config` also updates GBN MCS peer URL/token |
| Active Event (authoritative) | Central via MCS; Registration sets it |
| Active Event cache for kiosks | GBN (`data/active_event.json`; Registration `PUT` + MCS read) |
| Poster CRUD + video + flavor | GBN server (per Event) |
| Poster chrome templates (headline / labels / accent) | GBN server (`poster_templates.json`) |
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
| Neither | Operator picks a template or edits chrome and **Save as new** before Create |

Built-ins cannot be overwritten; **Save as new** always forks (Create poster does **not** auto-save templates). Chrome is **snapshotted** onto each poster at create time. Custom templates keep that snapshot; built-in hunter/bounty chrome follows live MCS role overlays on read.

Subject affiliations are **select-only** per category from the active event’s Game Master catalog (Allegiance, Faction, or any operator-defined category) — not a baked-in NeoCorp list. Create/rename choices in Game Master; intake does not create novel Central choices. Capture chrome (incl. **accent color** for titles/borders) lives under **Customize poster look** (collapsed for Hunter/Bounty).

### Event-scoped storage

Clips and poster metadata are stored **per active Event** (from MCS / Registration):

| Path | Purpose |
|---|---|
| `data/events/{event_id}/posters.json` | Poster metadata for that event |
| `data/events/{event_id}/meta.json` | Display name for Event media UI |
| `data/active_event.json` | Last-known active Event for `/poster-cycle` |
| `media/events/{event_id}/videos/{player_id}.ext` | Capture clips (filename = player id) |
| `data/poster_templates.json` | Chrome templates (global) |
| `data/posters.json` + `media/videos/` | Legacy pre-event store (`GET /api/posters?include_legacy=true` only) |

Create poster requires an active event (`409` if none). Public display URL stays `/poster/player/{id}` — GBN resolves video/metadata under the active Event folder. The panel **Event media** card shows Event **name** (UUID muted), sizes, export zip, and delete.

**Active Event resolution:** MCS `GET /events/active` when `GBN_MCS_*` is set; else disk cache. Registration pushes `PUT /api/events/active` on set-active / restore so AlleycatTV Pis do not need a desktop browser visit after GBN restart. Startup warms the cache from MCS or disk.

API:

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/poster-templates` | List built-ins + customs |
| `POST` | `/api/poster-templates` | Create custom |
| `PUT` / `DELETE` | `/api/poster-templates/{id}` | Non-builtin only |
| `GET` | `/api/posters` | Active-event posters only (`?event_id=` fallback; `?include_legacy=true` for old store) |
| `POST` | `/api/posters` | Requires active event (or form `event_id`); stores under that event |
| `GET` | `/api/events/active` | Active event id/name (MCS → cache) |
| `PUT` | `/api/events/active` | Registration push: `{active_event_id, event_name}` |
| `GET` | `/api/events/media` | Event folders: name, clip count + bytes (`?ensure_event_id=` / `ensure_event_name=`) |
| `GET` | `/api/events/{id}/clips/export` | Zip of videos only (`{player_id}.ext`) |
| `DELETE` | `/api/events/{id}/media` | Delete that event’s media + posters |

---

## Server env (`GBN_*`)

| Variable | Default | Purpose |
|---|---|---|
| `GBN_HOST` | `0.0.0.0` | Bind address |
| `GBN_PORT` | `8100` | Bind port |
| `GBN_PUBLIC_BASE` | `http://127.0.0.1:8100` | Fallback public URL only — live poster/media links use the request Host (so a new CT IP via Core Configurator is picked up without rewriting this env) |
| `GBN_MEDIA` | `./media` | Videos + NeoCorp SVG assets (`events/{id}/videos/` for new captures) |
| `GBN_DATA` | `./data` | Data directory (`events/{id}/posters.json` per event) |
| `GBN_POSTERS` | `./data/posters.json` | Legacy global poster store (read fallback) |
| `GBN_TEMPLATES` | `./data/poster_templates.json` | Poster chrome templates (hunter/bounty built-ins + customs) |
| `GBN_MCS_BASE` | _(empty)_ | MCS base URL for Player overlay + active-event backup |
| `GBN_MCS_TOKEN` | _(empty)_ | Bearer token for MCS (same as Core Configurator) |
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
| `/poster/player/{id}` | Single animated poster (active Event on disk) |
| `/poster-cycle` | Rotate **active-event** posters only (default 30s; `?interval=` 5–300). Loads `/api/events/active` then `/api/posters?event_id=…` every 15s — never the legacy global store. |
| `/active-players` | Rotate game-server curated `player_ids` only |

AlleycatTV Content **+ Poster cycle** adds `{gbn}/poster-cycle` as a webpage playlist item (**24h** slot; GBN rotates every 30s inside the page). See [`Docs/GBN Config Steps.md`](../../Docs/GBN%20Config%20Steps.md). After deploying GBN, set the active Event in Registration (or confirm `GET /api/events/active`) before expecting Pis to show posters. Re-click **+ Poster cycle** (or edit playlist duration) after upgrading the Content panel so existing groups pick up the 24h slot.

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
