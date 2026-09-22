# Core Configurator

Single source of truth for Alleycat app endpoints. Set an IP here — Registration, AlleycatTV, GBN, and Bug Buster follow. No app stores its own copy of a service URL.

**Code:** `core_configurator`  
**Path:** `Apps/Core_Configurator/HA_Component/`  
**HA shape:** config entry + options panel (no Proxmox companion)

---

## Service keys

Each key maps to one external service. Other integrations call `get_url(hass, key)` to read the current URL. The panel lets operators edit them without touching config files.

| Key | Label | Used by |
|---|---|---|
| `registration_primary` | Registration · online | Registration (cloud / DigitalOcean player API) |
| `registration_secondary` | Registration · local | Registration (LAN player API) |
| `alleycattv` | AlleycatTV streaming server | AlleycatTV, Content Manager, Digital Node Nexus |
| `gbn` | Galactic Bounty Network | GBN, Registration poster column |
| `proxmox` | Proxmox | Bug Buster (URL + node name only) |

> **Proxmox tokens** are owned by Bug Buster, not Core Configurator. This integration stores the Proxmox URL and node name. API credentials stay in Bug Buster's own config entry.

> **Dual Registration URLs** (`registration_primary` / `registration_secondary`) stay until Phase 4, when Master Control Server becomes the single Central HTTP adapter and Registration points at MCS instead.

---

## Fail-closed contract

`get_url` returns an empty string when no URL is stored. There are no built-in fallback IPs and no `DEFAULTS` dict. An integration that calls `get_url` and gets `""` must fail cleanly rather than silently contacting a hardcoded address.

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
| `urlutil.py` | `normalize_url`, `empty_services` (blank URLs by design), `services_from_mapping` |
| `helpers.py` | `get_url` (fail-closed), `get_extra`, `catalog_public`, `save_services`, `apply_service` |
| `config_flow.py` | One-time setup form; `async_step_import` for YAML seed; single-instance enforced |
| `__init__.py` | `async_setup` / `async_setup_entry`, websocket commands, fires `core_configurator_updated` |
| `strings.json` | UI labels and abort messages |

### JS panel

```
HA_Component/www/core_configurator/
```

| File | Purpose |
|---|---|
| `core-configurator-client.js` | `window.CoreConfigurator.{getUrl, getServices, setService, subscribe}` — no fallback IPs |
| `core-configurator-panel.js` | `<core-configurator-panel>` custom element — grid of service cards, Apply saves to config entry, blank cards marked **not set** |

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

Other integrations import directly from this component. List `core_configurator` in your `manifest.json` `after_dependencies`.

```python
from custom_components.core_configurator.helpers import get_url, get_extra, apply_service

# Read a URL — returns "" if not configured (fail-closed)
url = get_url(hass, "alleycattv")

# Read a Proxmox extra field
node = get_extra(hass, "proxmox", "node", default="pve")

# Write a URL from another integration
apply_service(hass, "gbn", url="http://192.168.1.206:8100")
```

## JS helper usage

Load `core-configurator-client.js` via `extra_module_url` before your feature panel. `window.CoreConfigurator` is available to all panels on the same page.

```js
// Read a URL — returns "" if not configured (fail-closed)
const url = await window.CoreConfigurator.getUrl(hass, "alleycattv");

// Subscribe to changes
const unsub = await window.CoreConfigurator.subscribe(hass, () => reload());

// Update a URL from a panel
await window.CoreConfigurator.setService(hass, "gbn", { url: "http://192.168.1.206:8100" });
```

---

## Home Assistant configuration

Add to `configuration.yaml` to seed URLs on first boot. After the config entry is created the YAML block is ignored — edit from the sidebar instead.

```yaml
core_configurator:
  registration_primary: https://your-cloud-player-api.example.com
  registration_secondary: http://192.168.1.234:8090
  alleycattv: http://headless-alleycat-streaming-server.local
  gbn: http://192.168.1.206:8100
  proxmox: https://192.168.1.1:8006
  proxmox_node: pve
```

Register the sidebar panel in `configuration.yaml`:

```yaml
frontend:
  extra_module_url:
    - /local/core_configurator/core-configurator-client.js

panel_custom:
  - name: core-configurator-panel
    sidebar_title: Core Configurator
    sidebar_icon: mdi:lan
    url_path: core-configurator
    module_url: /local/core_configurator/core-configurator-panel.js
```

Copy files into your HA `config/` directory:

```
custom_components/core_configurator/   ← HA_Component/custom_components/core_configurator/
www/core_configurator/                 ← HA_Component/www/core_configurator/
```

---

## What this phase ships

- One place to type an IP address.
- Integrations that call `get_url` fail closed if the URL is blank.
- No `secrets.yaml` as a live control plane after import.
- No `panel_custom server_url`, no `rest.yaml` URLs, no hardcoded LAN fallbacks.

## What is not in this phase

| Item | Reason |
|---|---|
| `master_control_server` key | Phase 4 — nothing talks to MCS yet |
| Shared HTTP / MQTT helpers | Phase 3 — `get_url` is enough for this slice |
| pytest / CI | Phase 2 — shipped. Run from `Apps/Core_Configurator/HA_Component/`: `pytest` |
| Patching the old `alleycat_directory` code | Old `HomeAssistConfig` is a contract reference, not the build target |
