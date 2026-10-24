# Handoff — Config push / peer fan-out / affiliation tags

**Date:** 2026-10-23  
**Plan:** `config_push_and_tags_9a1115a4.plan.md`  
**Continue in a new chat:** `@Docs/Handoff Config Push and Tags.md` — focus on **MCS peer fan-out reliability** and **HA auto-update on Core Configurator Save**.

---

## Venue map (corrected — do not swap again)

| Role | CTID | Hostname | LAN IP | Port | systemd |
|------|------|----------|--------|------|---------|
| **GBN** | **101** | `gbn` | `10.10.50.187` | 8100 | `gbn` |
| **MCS** | **102** | `master-control-server` | `10.10.50.110` | 8700 | `mcs` |
| AlleycatTV | 104 | alleycattv | (check `hostname -I`) | 8000 | `alleycattv-server` |
| Net Time | 105 | net-time | (check `hostname -I`) | 8720 | `net-time` |
| HA | — | — | `10.10.50.11` | — | — |
| Proxmox host | — | Proxmox-Server | `10.10.50.205` | — | host clock agent `:8721` |

**Original user note had CTIDs backwards** (said MCS=101 / GBN=102). Software was redeployed to match Proxmox names: GBN→101, MCS→102.

**Core Configurator must use:**
- MCS: `http://10.10.50.110:8700` + Bearer (same as `MCS_API_TOKEN` / `GBN_MCS_TOKEN`)
- GBN: `http://10.10.50.187:8100`
- Central primary: `https://alleycat-dl83g.ondigitalocean.app` (**no** `/players` suffix)
- Central secondary: **empty** for now (`192.168.1.234:8090` is unreachable from this venue → `HTTP 000`)

Token lives in `/etc/mcs.env` on CT 102 and `/etc/gbn.env` on CT 101 — do not paste into docs/chats if avoidable.

---

## What shipped (code — in repo)

### Part A — MCS peer hub
- `Apps/Master_Control_Server/Server_Component/models.py` — `ConfigUpdate` peer fields
- `Apps/Master_Control_Server/Server_Component/peer_fanout.py` — soft-fail HTTP POST to GBN + Net Time
- `Apps/Master_Control_Server/Server_Component/main.py` — store `_peers`, call `fanout_peers` after `/config`
- GBN: `app/runtime_config.py`, `app/routers/config.py` (`POST /config`), `mcs_client` uses runtime getters
- Net Time: `POST /config` for `host_clock_url` (+ optional token), persist `/etc/net-time.env`
- Registration HA: `_push_central_config` sends full peer snapshot; listens for peer-related CC keys
- AlleycatTV HA: retained MQTT `cmd/all/config`; Pi player apply + `/etc/alleycattv.env` rewrite

### Part B — Affiliation ownership
- Game Master: catalog cache + CRUD services + `game_master/get_affiliation_catalog` + panel UI
- Registration: tags chip UI only; catalog CRUD removed; WS delegates to GM
- GBN panel: select-only from GM catalog
- Docs: `Docs/Design Terms.md`, MCS Config Steps, GBN/Net Time READMEs

Panels built via `Libraries/Shared_HA_Helpers/panel_kit` → `npm run build`.

---

## What’s working (verified on venue)

- MCS CT 102 `/health`, `/game-state`, `/events/active` → **200** after restart + config push with **empty secondary**
- Central online `GET /game-state` → 200 (Development event `20000000-0000-4000-8000-000000000001`)
- GBN CT 101 `/health` active; can call MCS players; **manual** `POST http://10.10.50.187:8100/config` from MCS IP → **204** + log `GBN /config applied`
- Player roster still present (5 players) — data was not deleted
- UI recovered once MCS game-state worked again (active event / Game Master)

---

## What’s NOT done / broken — **continue here**

### 1. Automatic MCS → GBN fan-out unreliable
- Manual `POST /config` to **GBN** works.
- `POST /config` to **MCS** returns 204 and updates Central URLs, but GBN journal often shows **no** follow-on `POST /config` from fan-out.
- MCS app `INFO` logs (`MCS config updated`, `peer fan-out`) often **don’t appear** in journalctl (uvicorn access log does show `POST /config`).
- Live `_peers` / `_last_fanout` cannot be inspected via `python -c "import main"` (new process ≠ running uvicorn).

**Next steps:**
- Confirm fan-out runs after MCS `/config` (add temporary `print`/`logging.basicConfig`, or `GET /config/status` returning `_last_fanout`).
- Fix any silent httpx failure; ensure peer fields actually land in `_peers` on the running process.
- Re-test: MCS POST with `gbn_url` → GBN must log `GBN /config applied` from `10.10.50.110`.
- Same path for Net Time (`net_time_url` + token + `host_clock_url`).

### 2. HA auto peer push on Core Configurator Save
- Need to confirm **new** Registration (+ Game Master, AlleycatTV, Shared Helpers) is deployed to `10.10.50.11` and HA restarted.
- After Save / `registration.sync_now`, MCS should receive peer snapshot (not Central-only).
- AlleycatTV should publish retained MQTT `config` for Pis.
- Fix Central secondary empty in CC so HA doesn’t re-push the dead `192.168.1.234` URL.

### 3. Optional MCS robustness patch
- `central_client.fetch_game_state`: today any primary status `< 500` (including **404**) returns immediately and **never tries secondary**. Prefer falling through on 404/connection failure so a bad primary doesn’t brick the venue when secondary is good.

### 4. Deploy hygiene
- Windows `scp -r Server_Component` sometimes nests as `/opt/.../Server_Component/` — push helper should use contents of Server_Component as `SRC`, or promote nest after push.
- CT 101 previously had wrong `mcs.service`; CT 102 had wrong `gbn.service` — clean leftovers if any remain.
- Ensure `/etc/gbn.env` never has placeholder `PASTE_SAME_TOKEN_AS_MCS`.

### 5. Pi MQTT config
- Player code supports retained `config`; confirm HA AlleycatTV component redeployed; Pi package update if SD images are old.

---

## Useful commands (Proxmox host)

```bash
# Health
pct exec 102 -- curl -s http://127.0.0.1:8700/health
pct exec 101 -- curl -s http://127.0.0.1:8100/health

# Manual MCS peer push (TOKEN from /etc/mcs.env)
TOKEN=$(pct exec 102 -- bash -lc "grep ^MCS_API_TOKEN= /etc/mcs.env | cut -d= -f2-")
pct exec 102 -- curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8700/config \
  -H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json' \
  -d "{\"central_primary\":\"https://alleycat-dl83g.ondigitalocean.app\",\"central_secondary\":\"\",\"mcs_url\":\"http://10.10.50.110:8700\",\"gbn_url\":\"http://10.10.50.187:8100\",\"host_clock_url\":\"http://10.10.50.205:8721\"}"

# Did GBN get fan-out?
pct exec 101 -- journalctl -u gbn -n 30 --no-pager --since '2 min ago' | grep -iE 'GBN /config|POST /config'

# Direct GBN config (proves path)
pct exec 102 -- curl -s -o /dev/null -w '%{http_code}\n' -X POST http://10.10.50.187:8100/config \
  -H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json' \
  -d "{\"mcs_base\":\"http://10.10.50.110:8700\",\"mcs_token\":\"${TOKEN}\",\"public_base\":\"http://10.10.50.187:8100\"}"
```

**SPC push** (from host, after staging `/root/mcs-src` / `/root/gbn-src`):

```bash
CTID=102 UNIT=mcs DEST=/opt/mcs SRC=/root/mcs-src bash /root/push-server-component.sh
CTID=101 UNIT=gbn DEST=/opt/gbn SRC=/root/gbn-src bash /root/push-server-component.sh
```

---

## Suggested first message for the next chat

> Continue `@Docs/Handoff Config Push and Tags.md`. Venue: GBN CT101 `.187:8100`, MCS CT102 `.110:8700`, HA `10.10.50.11`. Peer fan-out: manual GBN `POST /config` works; MCS `POST /config` 204s but often doesn’t fan out to GBN. Also wire/verify HA Core Configurator Save → Registration peer snapshot → MCS → GBN/Net Time, plus AlleycatTV retained MQTT config. Optional: MCS `fetch_game_state` should fall through on primary 404 to secondary.

---

## Out of scope (year 1 — per plan)

- Pi MAC/IP rediscovery DB  
- HA multi-companion HTTP propagator (replaced by MCS hub)  
- MQTT client on MCS or AlleycatTV content LXC  

---

# Handoff — Venue one-line installer (this chat)

**Date:** 2026-10-20 (work) / noted 2026-10-23  
**Docs:** [`Docs/Venue Install.md`](Venue%20Install.md), [`Docs/Proxmox Config Steps.md`](Proxmox%20Config%20Steps.md)  
**Continue in a new chat:** `@Docs/Handoff Config Push and Tags.md` (venue installer section) or `@Docs/Venue Install.md` — focus on a **clean reinstall** after packaging, then verify residual HA clicks.

---

## Goal

One Proxmox-host installer so a non-expert can stand up Mission Control (HAOS + LXCs + HA deploy + secrets) without hand-clicking Registration/DNN/MQTT/Proxmox token/theme/sidebar. Offline venues must be told where Linux CT + HAOS images go.

---

## What shipped (code — in repo)

### Orchestrator / libs
- `ProxmoxInstallFiles/install-mission-control.sh` — venue orchestrator (`RESUME=ha-deploy` redeploy path)
- `ProxmoxInstallFiles/lib/mc-install-common.sh` — shared helpers including:
  - `mc_prepare_proxmox_host` — **first step**: disable enterprise repos → **pve-no-subscription**, patch subscription nag + APT hook `86no-nag-popup`, then **`apt-get update` + `dist-upgrade`** (skip upgrade: `SKIP_PVE_UPGRADE=1`; skip all prep: `SKIP_PVE_HOST_PREP=1`)
  - `mc_check_offline_prereqs` — fail early if no Ubuntu CT template and no internet
  - `mc_ensure_proxmox_api_token` — create `hass@pve!missioncontrol` (`PVEVMUser`) into secrets
  - `mc_prompt_central_urls` — prompt or env `CENTRAL_PRIMARY` / `CENTRAL_SECONDARY`
  - `mc_ha_force_cc_reseed` — drop Core Configurator config entry so YAML+secrets re-import
  - `mc_ha_bootstrap_mqtt` — Mosquitto + MQTT config entry (best effort)
  - `mc_ha_bootstrap_hacs` — unpack HACS when HA has internet (GitHub authorize still once in UI)
  - `mc_ha_apply_alleycat_theme` — write `.storage/frontend_theme` + `frontend.set_theme` Alleycat light/dark
- `ProxmoxInstallFiles/lib/deploy-ha-components.sh` — tar|ssh deploy (no rsync on HA SSH); themes + **mc-shell**
- `ProxmoxInstallFiles/lib/fetch-ha-shell.sh` — download custom-sidebar + card-mod → `HomeAssist/www/mc-shell/`
- `ProxmoxInstallFiles/package-venue-bundle.sh` — fetches mc-shell then stages `dist/mission-control-venue/`
- `ProxmoxInstallFiles/install-haos-proxmox.sh` — supports offline `HAOS_IMAGE=/path/to/haos_ova-*.qcow2.xz`
- Per-app installers: clearer offline template errors; `pveam download` stdout redirected to stderr

### HA automation (no more manual Add Integration for these)
- `registration: {}` / `digital_node_nexus: {}` + `async_step_import` / `async_setup` (same pattern as AlleycatTV)
- `HomeAssist/configuration.yaml` — `extra_module_url` uses **`/local/mc-shell/...`** (not `/hacsfiles/...`) so Mission Control sidebar title works offline
- Vendored: `HomeAssist/www/mc-shell/custom-sidebar-plugin.js`, `card-mod.js`

### Docs
- `Docs/Venue Install.md` — offline **where to put files** table, host prep, residual steps
- `Docs/Proxmox Config Steps.md` — notes venue installer runs § B + § C automatically

---

## Offline file locations (venue host)

| What | Path |
|------|------|
| Ubuntu 24.04 LXC template (`.tar.zst`) | `/var/lib/vz/template/cache/` then `pveam list local` |
| HAOS KVM image | `/root/haos_ova-*.qcow2.xz` + `HAOS_IMAGE=...` |
| Venue bundle | `/root/mission-control-venue/` |

---

## How to re-test (clean install)

On PC (Git Bash):

```bash
bash ProxmoxInstallFiles/package-venue-bundle.sh
```

PowerShell SCP → Proxmox `10.10.50.205`:

```powershell
scp -r "z:\CodingProjects\Alleycat\MissionControl\dist\mission-control-venue" root@10.10.50.205:/root/
```

On Proxmox shell (after VMs/CTs removed if starting fresh):

```bash
bash /root/mission-control-venue/install-mission-control.sh
# or offline HAOS:
# HAOS_IMAGE=/root/haos_ova-XX.qcow2.xz bash /root/mission-control-venue/install-mission-control.sh
```

Redeploy only into existing HA:

```bash
RESUME=ha-deploy bash /root/mission-control-venue/install-mission-control.sh
```

---

## Still manual / residual after Done

1. **Proxmox VE** HA integration (monitoring sensors) — host IP, user `hass`, realm PVE, token id `missioncontrol`, same secret as CC / secrets.yaml  
2. **HACS** Add Integration + one-time GitHub device code (sidebar title already works via mc-shell without this)  
3. Hard-refresh browser — confirm **Mission Control** title + **Alleycat** theme  
4. Flash AlleycatTV Pis / FDN MQTT (`alleycatTV` / `alleycat`)  
5. If kernel upgraded during host prep — reboot Proxmox when convenient  

---

## Known pitfalls from this work

- PowerShell has **no bash** — package with Git Bash; run installer only on Proxmox.  
- HA Terminal & SSH has **no rsync / no python3** — deploy uses tar|ssh; YAML merge runs on Proxmox then scp.  
- `pveam download` progress on stdout used to corrupt `TEMPLATE_REF` — must redirect to stderr.  
- Scanlines JS alone ≠ Alleycat theme — must set `frontend_theme` / `set_theme`.  
- Force CC reseed **wipes** operator CC edits on every full/RESUME deploy (secrets.yaml is source of truth for that pass).  
- MQTT/Registration depend on Mosquitto being up; Registration YAML import runs once `mqtt` is available.  

---

## Suggested first message (venue installer continue)

> Continue venue installer from `@Docs/Handoff Config Push and Tags.md` (Venue one-line installer section) and `@Docs/Venue Install.md`. Re-package, SCP to `10.10.50.205`, run clean install (VMs/CTs already cleared if needed). Verify: host prep update/upgrade, offline path messaging, Registration/DNN/MQTT/token/theme/Mission Control sidebar. Then finish residual Proxmox VE + HACS authorize if still needed.  
