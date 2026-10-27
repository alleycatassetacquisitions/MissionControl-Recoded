# Master Control Server

Proxmox companion service. The **only** Central HTTP adapter for Mission Control.

**Code:** `master_control_server`  
**Path:** `Apps/Master_Control_Server/`  
**Shape:** Standalone FastAPI service — **not** a Home Assistant process.

---

## Role in the architecture

```
Operator (CC panel)
    │  saves MCS URL + token, Central URLs, companion URLs
    ▼
Core Configurator (HA)
    │  fires core_configurator_updated (peer keys) / registration.sync_now
    ▼
Registration integration (HA)
    │  POST /config  peer snapshot (Bearer from CC get_extra)
    ▼
Master Control Server  ←──── /players /events /device-logs  ──── Registration / Bug Buster
    │                 └── soft-fail fan-out POST /config → GBN, Net Time
    │  tries primary, falls back to secondary (game-state also on 404)
    ▼
Central Server (online or LAN)
```

- **Home Assistant does not talk to the Central Server directly.** MCS is the gateway.
- MCS is also the **venue peer-config hub**: Registration pushes Central + companion URLs; MCS fans out to GBN and Net Time. Inspect with `GET /config/status`.
- `Registration` is MCS's HA face for players + events.
- `Bug Buster` reads device crash logs via MCS.
- `GBN` calls MCS for Player data (live overlay on poster reads).

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

`role` / `mode` are HA-facing aliases derived from Central `team_name` (hunter/bounty) when present. Roster also includes `team_id`, `team_name`, `active`, `event_id`. NeoCorp / faction / neo_id stay empty until Central’s affiliation API ships.

### `GET /players/{player_id}` — Bearer required

Single player record. Returns `404` if not found.

### `POST /players` — Bearer required

Create a player. MCS body: `{ "name", "email?" }`. Forwards to Central as **`application/json`**. Central returns **`PlayerResponse`** (incl. `pdn_code`); MCS responds **201** with the normalized player.

**409 passthrough:** Central text such as `No active event`, duplicate name, or codes exhausted is returned as HTTP 409 with that detail (not a generic 502).

### `PUT /players/{player_id}` — Bearer required

Proxies to Central **`PATCH /players/{id}`**. Body may include `name`, `email` / `clear_email`, `team_id` / `clear_team`, `active`.

### `DELETE /players/{player_id}` — Bearer required

**Soft-deactivate:** Central `PATCH { "active": false }` (no hard DELETE on Central). Returns **204**.

### `POST /events` — Bearer required

Create event → Central `POST /events` JSON `{ name, venue_name? }`. Query `?set_active=true` also calls `PUT /events/{id}/active` and stores the event in MCS active memory.

### `PATCH /events/{event_id}` — Bearer required

Update event → Central `PATCH` (at least one of `name` / `venue_name`).

### `PUT /events/{event_id}/active` — Bearer required

Select active event → Central `PUT` (204). Remembers `active_event_id` in MCS memory.

### `GET /events` — Bearer required

Lists events from Central (`{ events, ready: true }`).

### `GET /events/active` — Bearer required

Derived from Central **`GET /game-state`** (`active_event`). Falls back to MCS memory if Central is unreachable:

```json
{
  "ready": true,
  "active_event_id": "…",
  "event": { "id": "…", "name": "…", "venue_name": null, "created_at": "" },
  "source": "central"
}
```

### `GET /game-state` — Bearer required

Full Central game-state snapshot (`active_event`, `scoring`, `accepting_delayed_scores`, `server_time_utc`). Used by Game Master.

### `PUT /scoring` / `PUT /events/{event_id}/scoring` — Bearer required

Toggle scoring (`{ "enabled": true|false }`). Convenience `/scoring` uses the active event.

### `PUT /delayed-scores` / `PUT /events/{event_id}/delayed-scores` — Bearer required

Toggle delayed-score acceptance for an event.

### `GET /events/{event_id}/teams` — Bearer required

List teams for an event (Registration team assign). Also `POST` create / `PATCH` rename.

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

Pushed by Registration on setup, on `registration.sync_now`, and when Core Configurator Save touches peer keys (MCS / Central / GBN / Net Time / AlleycatTV / Proxmox). Body is a **peer snapshot**:

```json
{
  "central_primary": "https://...",
  "central_secondary": "",
  "mcs_url": "http://…:8700",
  "gbn_url": "http://…:8100",
  "net_time_url": "http://…:8720",
  "net_time_token": "…",
  "alleycattv_url": "http://…",
  "host_clock_url": "http://…:8721",
  "mqtt_host": "…",
  "mqtt_port": "1883"
}
```

Returns `204 No Content` even if companion fan-out soft-fails.

| Field | Empty / omitted |
| --- | --- |
| `central_primary` | Empty leaves current |
| `central_secondary` | Omitted leaves current; `""` **clears** (no dead mirror) |
| Peer fields | Empty leaves current; non-empty overwrites |

After store, MCS soft-fails `POST {gbn_url}/config` (`mcs_base` / `mcs_token` / `public_base`) and `POST {net_time_url}/config` (`host_clock_url`, Bearer = Net Time token).

### `GET /config/status` — Bearer required

Diagnostics for the running process (no attach/`import main` needed):

```json
{
  "central_primary": "…",
  "central_secondary": "",
  "peers": {
    "mcs_url": "…",
    "gbn_url": "…",
    "net_time_url": "…",
    "net_time_token": "set",
    "alleycattv_url": "…",
    "host_clock_url": "…",
    "mqtt_host": "…",
    "mqtt_port": "…"
  },
  "last_fanout": {
    "gbn": { "ok": true, "status": 204 },
    "net_time": { "ok": true, "status": 204 }
  }
}
```

`net_time_token` is redacted (`"set"` or `""`).

---

## Auth contract

MCS uses a single static Bearer token (`MCS_API_TOKEN` on the LXC). The **same** token is stored in Core Configurator (`master_control_server` → API token) and used as GBN’s MCS peer token. Registration and Bug Buster read it via `get_extra` and send `Authorization: Bearer {token}` on protected calls (`/players`, `/events`, `/device-logs`, `/config`, `/config/status`). Neither keeps its own copy of the token.

`/health` is intentionally unauthenticated so the `DataUpdateCoordinator` can detect availability without needing the token in every health probe.

---

## Primary / secondary failover

`central_client` tries `central_primary` first. Transport failure (`status` 0) and **5xx** fall through to `central_secondary`. For **`GET /game-state` only**, **404** also falls through so a bad/missing primary does not brick the venue when secondary is healthy. Other 4xx (including 409) return immediately without failover.

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
