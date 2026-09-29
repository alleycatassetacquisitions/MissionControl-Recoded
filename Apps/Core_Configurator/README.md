# Core Configurator

Single source of truth for Alleycat service **URLs and API tokens**. Set an address or credential here — Registration, AlleycatTV, GBN, and Bug Buster follow. No app stores its own copy of a service URL or shared API token.

**Code:** `core_configurator`  
**Path:** `Apps/Core_Configurator/HA_Component/`  
**HA shape:** config entry + options panel (no Proxmox companion)

---

## Service keys

Each key maps to one external service. Other integrations call `get_url(hass, key)` and `get_extra(hass, key, field)` to read the current values. The panel lets operators edit them without touching config files.

| Key | Label | Used by |
|---|---|---|
| `master_control_server` | Master Control Server | Registration (URL + `extra.token`) |
| `central_primary` | Central Server · online | Master Control Server (via Registration push) |
| `central_secondary` | Central Server · local | Master Control Server (via Registration push) |
| `alleycattv` | AlleycatTV streaming server | AlleycatTV, Content Manager, Digital Node Nexus |
| `gbn` | Galactic Bounty Network | GBN, Registration poster column |
| `proxmox` | Proxmox | Bug Buster (URL + `extra.node` / `token_id` / `token_secret`) |
| `rtsp` | Live RTSP | AlleycatTV live interrupt (`extra.label` / `extra.enabled`) |

> **Credentials live here.** MCS Bearer (`extra.token` on `master_control_server`) and Proxmox API tokens (`extra.token_id` / `extra.token_secret` on `proxmox`) are Core Configurator fields. Paste the same Proxmox token into HA Core **Proxmox VE** for monitoring entities. Bug Buster is Proxmox console, MQTT spy, and companion health — it does not own tokens. RTSP camera/encoder URLs also live here (not in AlleycatTV Content Manager).

---

## Fail-closed contract

`get_url` / `get_extra` return an empty string when nothing is stored. There are no built-in fallback IPs and no `DEFAULTS` dict. An integration that gets `""` must fail cleanly rather than silently contacting a hardcoded address.

Form placeholders in the UI are example hosts only — they are never used as runtime values.

---

## File structure

### Python integration

```
HA_Component/custom_components/core_configurator/
```

| File | Purpose |
|---|---|
| `manifest.json` | Domain `core_configurator`, depends on `http`, `config_flow: true` |
| `const.py` | `DOMAIN`, service keys, `SERVICE_CATALOG`, `YAML_KEYS` |
| `urlutil.py` | `normalize_url`, `empty_services`, `services_from_mapping` (incl. MCS token) |
| `helpers.py` | `get_url`, `get_extra`, `catalog_public`, `save_services`, `apply_service` |
| `config_flow.py` | One-time setup form; `async_step_import` for YAML seed; single-instance |
| `__init__.py` | Setup, websocket commands, fires `core_configurator_updated` |
| `strings.json` | UI labels and abort messages |

### JS panel

```
HA_Component/www/core_configurator/
```

| File | Purpose |
|---|---|
| `core-configurator-client.js` | `window.CoreConfigurator.{getUrl, getServices, setService, subscribe}` |
| `core-configurator-panel.js` | Service cards; sensitive extras use password inputs |

---

## Websocket API

All commands require an authenticated HA connection. `set_service` requires an admin user.

| Command type | Direction | Payload |
|---|---|---|
| `core_configurator/get_services` | → HA | _(none)_ |
| `core_configurator/get_url` | → HA | `{ key }` |
| `core_configurator/set_service` | → HA | `{ key, url?, extra? }` |

HA fires `core_configurator_updated` on every successful write. Other integrations subscribe to this event to resync without polling.

---

## Python helper usage

```python
from custom_components.core_configurator.helpers import get_url, get_extra, apply_service

url = get_url(hass, "master_control_server")
token = get_extra(hass, "master_control_server", "token")
node = get_extra(hass, "proxmox", "node", default="pve")
```

List `core_configurator` in your `manifest.json` `after_dependencies` / `dependencies`.

## JS helper usage

```js
const url = await window.CoreConfigurator.getUrl(hass, "alleycattv");
const unsub = await window.CoreConfigurator.subscribe(hass, () => reload());
await window.CoreConfigurator.setService(hass, "gbn", { url: "http://192.168.1.206:8100" });
```

---

## Home Assistant configuration

```yaml
core_configurator:
  master_control_server: !secret cc_master_control_server
  master_control_server_token: !secret cc_master_control_server_token
  central_primary: !secret cc_central_primary
  central_secondary: !secret cc_central_secondary
  alleycattv: !secret cc_alleycattv
  gbn: !secret cc_gbn
  proxmox: !secret cc_proxmox
  proxmox_node: !secret cc_proxmox_node
  proxmox_token_id: !secret cc_proxmox_token_id
  proxmox_token_secret: !secret cc_proxmox_token_secret
  rtsp: !secret cc_rtsp
  rtsp_label: !secret cc_rtsp_label
  rtsp_enabled: !secret cc_rtsp_enabled
```

Sidebar panel registration and `extra_module_url` are in [`HomeAssist/configuration.yaml`](../../HomeAssist/configuration.yaml).

Copy files into your HA `config/` directory:

```
custom_components/core_configurator/   ← HA_Component/custom_components/core_configurator/
www/core_configurator/                 ← HA_Component/www/core_configurator/
```

---

## Running tests

```powershell
cd Apps/Core_Configurator/HA_Component
pytest
```

Requires `requirements_test.txt` at repo root. CI runs via `.github/workflows/test.yml`.

---

## What this ships

- One place to type a URL **and** shared API tokens.
- Integrations that call `get_url` / `get_extra` fail closed if blank.
- No `secrets.yaml` as a live control plane after import.
- No `panel_custom server_url`, no `rest.yaml` URLs, no hardcoded LAN fallbacks.

## Related

- Shared HTTP / MQTT helpers: [`Libraries/Shared_HA_Helpers/README.md`](../../Libraries/Shared_HA_Helpers/README.md)
- MCS deploy: [`Docs/Master Control Server Config Steps.md`](../../Docs/Master%20Control%20Server%20Config%20Steps.md) (installer script)
