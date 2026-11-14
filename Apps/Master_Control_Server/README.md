# Master Control Server

Proxmox companion service. The **only** Central HTTP adapter for Mission Control.

**Code:** `master_control_server` (Core Configurator key)  
**Path:** `Apps/Master_Control_Server/`  
**Shape:** Standalone FastAPI on Proxmox (`/opt/mcs/`) — **not** a Home Assistant integration (no `HA_Component/`).

Full endpoint reference, env vars, and peer-config notes: [`docs/README.md`](docs/README.md).

---

## Role

- HA never talks to Central directly; MCS is the gateway.
- Registration / Game Master / Bug Buster call MCS with the Bearer from Core Configurator.
- Scoring, delayed-scores, and teams on Central are **active-event-only** (`/scoring`, `/delayed-scores`, `/teams`). MCS compatibility routes under `/events/{id}/…` return **409** when that id is not active.

---

## Syntax

Stable identity strings for Ctrl+F rename / debug. Prefer changing the named
constant, then searching for leftover literals.

When you rename an identity string, update this section in the same PR.

### Rename blast radius

| Change this | Also touches |
| --- | --- |
| Core Configurator key `master_control_server` | Registration, Game Master, Bug Buster, DNN, install scripts, secrets |
| `MCS_API_TOKEN` / install path `/opt/mcs/` | Proxmox unit, Venue Install, Config Steps |
| HTTP paths `/health`, `/players`, `/scoring`, `/teams` | HA integrations + panels + tests |

### Identity checklist

| Kind | Exact string | Constant / source |
| --- | --- | --- |
| Core Configurator key | `master_control_server` | Core Configurator `KEY_*` / catalog |
| Env token | `MCS_API_TOKEN` | systemd / installer |
| Install root | `/opt/mcs/` | Proxmox install script |
| Health | `/health` | `main.py` (unauthenticated) |
| Roster | `/players` | `main.py` |
| Scoring (Central + MCS convenience) | `/scoring` | `central_client._scoring_url` |
| Delayed scores | `/delayed-scores` | `central_client._delayed_scores_url` |
| Teams (Central) | `/teams` | `central_client._teams_url` |
| Game state | `/game-state` | `central_client._game_state_url` |
