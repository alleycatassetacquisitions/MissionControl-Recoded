# Master Control Server

Proxmox companion service. The **only** Central HTTP adapter for Mission Control.

**Code:** `master_control_server`  
**Path:** `Apps/Master_Control_Server/`  
**Shape:** Standalone FastAPI service — **not** a Home Assistant process.

---

## Role in the architecture

```
Operator (CC panel)
    │  saves central_primary / central_secondary URL
    ▼
Core Configurator (HA)
    │  fires core_configurator_updated
    ▼
Registration integration (HA)
    │  POST /config  (Bearer token)
    ▼
Master Control Server  ←──── GET /players, GET /players/{id}  ──── Registration
    │
    │  tries primary, falls back to secondary
    ▼
Central Server (online or LAN)
```

- **Home Assistant does not talk to the Central Server directly.** MCS is the gateway.
- `Registration` is MCS's HA face: coordinator, sensor, services, panel.
- `GBN` will call MCS for Player data in Phase 8.

---

## Environment variables (first-boot defaults)

| Variable | Default | Purpose |
|---|---|---|
| `MCS_API_TOKEN` | _(required)_ | Bearer token shared with the Registration HA integration |
| `CENTRAL_PRIMARY_URL` | `""` | Online / cloud Central Server (overwritten by HA via `/config`) |
| `CENTRAL_SECONDARY_URL` | `""` | LAN / local Central Server fallback (overwritten by HA via `/config`) |

Set these in the Proxmox LXC's `/etc/environment` or the service unit file.  
`CENTRAL_PRIMARY_URL` and `CENTRAL_SECONDARY_URL` are **first-boot defaults only** — the Registration integration overwrites them on every HA start via `POST /config`. After the first push, operators change Central URLs from the Core Configurator sidebar panel, not by SSH-ing into Proxmox.

---

## Endpoints

### `GET /health` — unauthenticated

Liveness check polled by the Registration `DataUpdateCoordinator`.

```json
{ "status": "ok", "central_primary": "https://...", "central_secondary": "http://..." }
```

### `GET /players` — Bearer required

Full player roster fetched from Central Server.

```json
{
  "count": 42,
  "players": [
    { "id": "abc123", "name": "Alice", "role": "hunter",
      "neocorp": "Helix", "faction": "Phoenix", "neo_id": "neo-001" }
  ]
}
```

### `GET /players/{player_id}` — Bearer required

Single player record. Returns `404` if not found.

### `POST /config` — Bearer required

Pushed by the Registration integration on every HA start and whenever `core_configurator_updated` fires for `central_primary` or `central_secondary`.

```json
{ "central_primary": "https://...", "central_secondary": "http://..." }
```

Returns `204 No Content`. Empty strings are ignored (existing value preserved).

---

## Auth contract

MCS uses a single static Bearer token (`MCS_API_TOKEN`). The Registration HA integration stores this token in its own config entry (never in Core Configurator — CC stores URLs, not credentials). Every request from Registration passes `Authorization: Bearer {token}`.

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
│   ├── models.py            Player, Roster, ConfigUpdate, HealthResponse
│   ├── central_client.py    async httpx — primary → secondary failover
│   └── tests/
│       ├── conftest.py      TestClient fixture, auth_headers, reset_config
│       ├── test_health.py   GET /health — unauthenticated, reflects config
│       ├── test_players.py  GET /players + /players/{id} — auth, field names
│       ├── test_config.py   POST /config — auth, update, empty-string guard
│       └── test_central_client.py  fetch_players — primary/secondary failover
└── docs/
    └── README.md            ← this file
```
