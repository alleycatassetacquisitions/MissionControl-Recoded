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
Master Control Server  ←──── GET/POST/PUT/DELETE /players  ──── Registration
    │
    │  tries primary, falls back to secondary
    ▼
Central Server (online or LAN)
```

- **Home Assistant does not talk to the Central Server directly.** MCS is the gateway.
- `Registration` is MCS's HA face: coordinator, sensor, services, panel.
- `GBN` calls MCS for Player data (Phase 8 — live overlay on poster reads).

---

## Environment variables (first-boot defaults)

| Variable | Default | Purpose |
|---|---|---|
| `MCS_API_TOKEN` | _(required)_ | Bearer token — **same value** as Core Configurator `master_control_server` → API token |
| `CENTRAL_PRIMARY_URL` | `""` | Online / cloud Central Server (overwritten by HA via `/config`) |
| `CENTRAL_SECONDARY_URL` | `""` | LAN / local Central Server fallback (overwritten by HA via `/config`) |

**Production deploy:** use [`Docs/install-mcs-proxmox.sh`](../../../Docs/install-mcs-proxmox.sh) — see [`Docs/Master Control Server Config Steps.md`](../../../Docs/Master%20Control%20Server%20Config%20Steps.md). The installer generates the token and prints it for Core Configurator / secrets.

`CENTRAL_PRIMARY_URL` and `CENTRAL_SECONDARY_URL` are **first-boot defaults only** — Registration overwrites them on every HA start via `POST /config`. After that, operators change Central URLs from the Core Configurator sidebar.

---

## Endpoints

### `GET /health` — unauthenticated

Liveness check polled by the Registration `DataUpdateCoordinator`.

```json
{ "status": "ok", "central_primary": "https://...", "central_secondary": "http://..." }
```

### `GET /players` — Bearer required

Full player roster fetched from Central Server, **normalized to canonical fields**.

```json
{
  "count": 42,
  "players": [
    { "id": "abc123", "name": "Alice", "role": "hunter",
      "neocorp": "helix", "faction": "Phoenix", "neo_id": "neo-001" }
  ]
}
```

### `GET /players/{player_id}` — Bearer required

Single player record. Returns `404` if not found.

### `POST /players` — Bearer required

Create a player. Body uses canonical fields; MCS writes Central legacy keys.

### `PUT /players/{player_id}` — Bearer required

Update a player (canonical in, legacy out to Central).

### `DELETE /players/{player_id}` — Bearer required

Delete a player on Central. Returns `204`.

### Central alias → canonical mapping

| Concept | Canonical (HA / MCS API) | Central legacy |
|---|---|---|
| NeoCorp | `neocorp` (lowercase: `freelancer`, `helix`, `endline`, `reboot`) | `allegiance` |
| Role | `role` (`hunter` \| `bounty`) | `mode` / `role` / `hunter` int (`1`/`2`) |
| Faction | `faction` | `faction` |
| Neo ID | `neo_id` | `neo_id` |

Reads coalesce aliases in `player_normalize.normalize_player`. Writes emit `allegiance` + `hunter` via `to_central_write_body`.

### `POST /config` — Bearer required

Pushed by the Registration integration on every HA start and whenever `core_configurator_updated` fires for `central_primary` or `central_secondary`.

```json
{ "central_primary": "https://...", "central_secondary": "http://..." }
```

Returns `204 No Content`. Empty strings are ignored (existing value preserved).

---

## Auth contract

MCS uses a single static Bearer token (`MCS_API_TOKEN` on the LXC). The **same** token is stored in Core Configurator (`master_control_server` → API token). Registration reads it via `get_extra` and sends `Authorization: Bearer {token}` on every protected call. Registration does not keep its own copy of the token.

`/health` is intentionally unauthenticated so the `DataUpdateCoordinator` can detect availability without needing the token in every health probe.

---

## Primary / secondary failover

`central_client.fetch_players` tries `central_primary` first. If the URL is empty or the request fails, it tries `central_secondary`. If both fail, it returns an empty list and logs a warning. No retry loop — design principle 6 (remove root causes, not symptoms).

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
│   ├── main.py              FastAPI app, auth, endpoints, runtime config state
│   ├── models.py            Player, PlayerWrite, Roster, ConfigUpdate, HealthResponse
│   ├── player_normalize.py  Central aliases ↔ canonical Player fields
│   ├── central_client.py    async httpx — read/write + primary → secondary failover
│   └── tests/
│       ├── conftest.py      TestClient fixture, auth_headers, reset_config
│       ├── test_health.py   GET /health — unauthenticated, reflects config
│       ├── test_players.py  GET/POST/PUT/DELETE /players
│       ├── test_player_normalize.py  allegiance/mode/hunter mapping
│       ├── test_config.py   POST /config — auth, update, empty-string guard
│       └── test_central_client.py  fetch_players — primary/secondary failover
└── docs/
    └── README.md            ← this file
```
