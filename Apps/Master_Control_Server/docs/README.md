# Master Control Server

Proxmox companion service. The **only** Central HTTP adapter for Mission Control.

**Code:** `master_control_server`  
**Path:** `Apps/Master_Control_Server/`  
**Shape:** Standalone FastAPI service — **not** a Home Assistant process.

---

## Role in the architecture

```
Operator (CC panel)
    │  saves MCS URL + token, central_primary / central_secondary
    ▼
Core Configurator (HA)
    │  fires core_configurator_updated
    ▼
Registration integration (HA)
    │  POST /config  (Bearer from CC get_extra)
    ▼
Master Control Server  ←──── /players /events /device-logs  ──── Registration / Bug Buster
    │
    │  tries primary, falls back to secondary
    ▼
Central Server (online or LAN)
```

- **Home Assistant does not talk to the Central Server directly.** MCS is the gateway.
- `Registration` is MCS's HA face for players + events.
- `Bug Buster` reads device crash logs via MCS.
- `GBN` calls MCS for Player data (Phase 8 — live overlay on poster reads).

---

## Environment variables (first-boot defaults)

| Variable | Default | Purpose |
|---|---|---|
| `MCS_API_TOKEN` | _(required)_ | Bearer token — **same value** as Core Configurator `master_control_server` → API token |
| `CENTRAL_PRIMARY_URL` | `""` | Online / cloud Central Server (overwritten by HA via `/config`) |
| `CENTRAL_SECONDARY_URL` | `""` | LAN / local Central Server fallback (overwritten by HA via `/config`) |

**Production deploy:** use [`ProxmoxInstallFiles/install-mcs-proxmox.sh`](../../../ProxmoxInstallFiles/install-mcs-proxmox.sh) — see [`Docs/Master Control Server Config Steps.md`](../../../Docs/Master%20Control%20Server%20Config%20Steps.md). The installer generates the token and prints it for Core Configurator / secrets.

`CENTRAL_PRIMARY_URL` and `CENTRAL_SECONDARY_URL` are **first-boot defaults only** — Registration overwrites them on every HA start via `POST /config`. After that, operators change Central URLs from the Core Configurator sidebar.

---

## Endpoints

### `GET /health` — unauthenticated

Liveness check polled by the Registration `DataUpdateCoordinator`.

```json
{ "status": "ok", "central_primary": "https://...", "central_secondary": "http://..." }
```

### `GET /players` — Bearer required

Player roster from Central (active event), normalized to MCS fields. Optional `page` / `per_page` query params; when omitted, MCS fetches all pages (Central max `per_page=100`).

```json
{
  "count": 2,
  "pagination": { "page": 1, "per_page": 100 },
  "players": [
    {
      "id": "…",
      "name": "Alice",
      "pdn_code": "1234",
      "mode": "hunter",
      "role": "hunter",
      "created_at": "2026-01-01T00:00:00Z",
      "email": "a@example.com",
      "neocorp": "",
      "faction": "",
      "neo_id": "",
      "team_id": null
    }
  ]
}
```

`role` is the HA-facing alias of Central `mode` (`unassigned` \| `hunter` \| `bounty`). NeoCorp / faction / neo_id are empty unless Central restores them.

### `GET /players/{player_id}` — Bearer required

Single player record. Returns `404` if not found.

### `POST /players` — Bearer required

Create a player. MCS body: `{ "name", "email?" }`. Forwards to Central as **`application/x-www-form-urlencoded`**. Central currently returns empty **200**; MCS responds **201** with echoed name/email (`mode=unassigned`) so Registration can refresh the roster for `pdn_code`.

**409 passthrough:** Central text such as `No active event`, duplicate name, or codes exhausted is returned as HTTP 409 with that detail (not a generic 502).

### `PUT /players/{player_id}` / `DELETE /players/{player_id}` — Bearer required

**501 Not Implemented** until Central ships player update/delete. Stable details:

- update: `Player update not available; waiting on Central PATCH/PUT /players/{id}`
- delete: `Player delete not available; waiting on Central DELETE /players/{id}`

### `POST /events` — Bearer required

Create event → Central `POST /events` JSON `{ name, venue_name? }`. Query `?set_active=true` also calls `PUT /events/{id}/active` and stores the event in MCS active memory.

### `PATCH /events/{event_id}` — Bearer required

Update event → Central `PATCH` (at least one of `name` / `venue_name`).

### `PUT /events/{event_id}/active` — Bearer required

Select active event → Central `PUT` (204). Remembers `active_event_id` in MCS memory.

### `GET /events` — Bearer required

**501** until Central ships list. Detail: `Event list not available; waiting on Central GET /events`.

### `GET /events/active` — Bearer required

Returns MCS last-known active event (not a local event DB):

```json
{
  "ready": false,
  "active_event_id": "…",
  "event": { "id": "…", "name": "…", "venue_name": null, "created_at": "" },
  "source": "mcs_memory"
}
```

`ready` flips when Central `GET /events/active` is enabled.

### `GET /device-logs` — Bearer required

Proxy Central device crash logs. Query: `page`, `per_page`.

```json
{
  "device_logs": [
    {
      "id": "…",
      "device_mac": "aa:bb:cc:dd:ee:ff",
      "crash_number": 1,
      "uptime_ms": 1000,
      "received_at": "…",
      "reset_reason": 3,
      "software_version": "1.0.0",
      "task_name": "main"
    }
  ],
  "pagination": { "page": 1, "per_page": 20 }
}
```

### `POST /config` — Bearer required

Pushed by the Registration integration on every HA start and whenever `core_configurator_updated` fires for `central_primary` or `central_secondary`.

```json
{ "central_primary": "https://...", "central_secondary": "http://..." }
```

Returns `204 No Content`. Empty strings are ignored (existing value preserved).

---

## Auth contract

MCS uses a single static Bearer token (`MCS_API_TOKEN` on the LXC). The **same** token is stored in Core Configurator (`master_control_server` → API token). Registration and Bug Buster read it via `get_extra` and send `Authorization: Bearer {token}` on protected calls (`/players`, `/events`, `/device-logs`, `/config`). Neither keeps its own copy of the token.

`/health` is intentionally unauthenticated so the `DataUpdateCoordinator` can detect availability without needing the token in every health probe.

---

## Primary / secondary failover

`central_client` tries `central_primary` first. If the URL is empty or the request fails (transport / 5xx), it tries `central_secondary`. Client errors (4xx, including 409) are returned immediately without failover. No retry loop — design principle 6 (remove root causes, not symptoms).

---

## Running locally

```bash
cd Apps/Master_Control_Server/Server_Component
MCS_API_TOKEN=my-token uvicorn main:app --reload --port 8700
```

## Running tests

```bash
cd Apps/Master_Control_Server/Server_Component
pip install -e ".[test]"
pytest
```

---

## File structure

```
Apps/Master_Control_Server/
├── Server_Component/
│   ├── pyproject.toml
│   ├── __init__.py
│   ├── main.py              FastAPI app, auth, endpoints, runtime config + active event memory
│   ├── models.py            Player, Event, DeviceLog, Roster, ConfigUpdate, HealthResponse
│   ├── player_normalize.py  Central player fields → MCS Player (mode→role)
│   ├── central_client.py    async httpx — players/events/device-logs + failover
│   └── tests/
│       ├── conftest.py
│       ├── test_health.py
│       ├── test_players.py
│       ├── test_events.py
│       ├── test_device_logs.py
│       ├── test_player_normalize.py
│       ├── test_config.py
│       └── test_central_client.py
└── docs/
    └── README.md            ← this file
```
