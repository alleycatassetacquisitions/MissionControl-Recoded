# Shared HA Helpers

Infrastructure library for Mission Control integrations. Not an operator-facing app — no sidebar, no config flow, no UI.

**Code:** `shared_libraries`  
**Path:** `Libraries/Shared_HA_Helpers/HA_Component/`  
**HA shape:** `custom_component`, `config_flow: false`, no sidebar

---

## What this ships

Modules other integrations import directly:

| Module | What it provides |
|---|---|
| `http.py` | `async_request` + `get_mcs_token` — bearer-auth HTTP via HA's managed session + Core Configurator URL/token |
| `proxy.py` | `async_proxy_lan` / `proxy_request_parts` — authenticated HA→LAN companion forward (GBN / AlleycatTV) |
| `mqtt.py` | `mc_topic`, `resolve_cmd_segments`, `async_subscribe` / `async_publish` / `async_subscribe_presence` |
| `fabric.py` | Presence tracking: `mc/{kind}/status/#` → device_registry + `online`/`offline`/`unknown` sensor; `async_forget_device` clears tracker + retained status |
| `www/shared_libraries/mc-panel.js` | Lit + TypeScript McPanel kit (`window.McPanel`) — build from `panel_kit/` |

Declared deps (`core_configurator`, `shared_libraries`) are hard-imported — missing packages fail import/setup loudly.

---

## Using this in an integration

### 1. Declare the dependency

In your integration's `manifest.json`:

```json
{
  "dependencies": ["http", "mqtt", "core_configurator", "shared_libraries"]
}
```

### 2. HTTP requests

```python
from custom_components.shared_libraries.http import async_request, get_mcs_token

# GET with no auth — returns None if no URL is configured (fail-closed)
response = await async_request(hass, "gbn", "GET", "/api/posters")
if response is None:
    return  # no URL set, fail cleanly — never fall back to a hardcoded IP

data = await response.json()

# POST with MCS Bearer from Core Configurator (single reader — do not copy get_extra)
token = get_mcs_token(hass)
response = await async_request(
    hass, "master_control_server", "POST", "/players",
    token=token,
    json={"name": "Player One"},
)
```

`async_request` signature:

```python
async def async_request(
    hass,
    service_key: str,       # Core Configurator key, e.g. "gbn", "master_control_server"
    method: str,            # "GET", "POST", "PUT", "DELETE", …
    path: str,              # starts with "/", e.g. "/api/posters"
    *,
    token: str | None = None,       # adds Authorization: Bearer {token}
    headers: dict | None = None,    # merged after bearer header
    json: Any | None = None,        # JSON body
    timeout: ClientTimeout = ...,   # default 10 s total
) -> ClientResponse | None
```

**Fail-closed contract:** returns `None` when Core Configurator has no URL stored for `service_key`. Never falls back to a hardcoded IP. Never opens a bare `aiohttp.ClientSession`.

### 3. MQTT

```python
from custom_components.shared_libraries.mqtt import (
    mc_topic,
    resolve_cmd_segments,
    async_subscribe,
    async_publish,
    async_subscribe_presence,
)

segments = resolve_cmd_segments(device_id=device_id)
# → ["cmd", "device", "<id>"]
topic = mc_topic("dnn", *segments, "page")
# → "mc/dnn/cmd/device/<id>/page"

mc_topic("tv", "cmd", "all")
# → "mc/tv/cmd/all"

mc_topic("dnn", "cmd", "broadcast", group_id)
# → "mc/dnn/cmd/broadcast/<group_id>"

unsub = await async_subscribe(hass, "dnn", *segments, "#", callback=handle_msg)
await async_publish(hass, "tv", "cmd", "all", "stop", payload=json.dumps(cmd))
unsub = await async_subscribe_presence(hass, "dnn", device_id, callback=on_presence)
```

**Rules:**
- Build command paths with `resolve_cmd_segments` + `mc_topic`. Never hard-code topic strings.
- Device scope is always `cmd/device/{id}` (TV and DNN). Use `"broadcast"` for groups — never `"zone"`.
- Never open a private MQTT client inside an integration. These wrappers delegate to HA's `mqtt` component.

### 4. Fabric presence

```python
from custom_components.shared_libraries.fabric import (
    async_start_presence_tracking,
    async_stop_presence_tracking,
    get_presence_tracker,
)

tracker = await async_start_presence_tracking(
    hass,
    "dnn",
    config_entry_id=entry.entry_id,
    domain="digital_node_nexus",
    name_prefix="FDN",
)
# Status on mc/dnn/status/{device_id} → HA device + sensor.*_presence
devices = tracker.list_devices()
```

On unload call `async_stop_presence_tracking(hass, "dnn")`.

### 5. Panel kit (frontend)

Load `mc-panel.js` via `extra_module_url` before your feature panel:

```yaml
panel_custom:
  - name: my-app-panel
    module_url: /local/my_app/my-panel.js
    config:
      extra_module_url:
        - /local/shared_libraries/mc-panel.js
```

`window.McPanel` is then available to your panel:

```js
class MyPanel extends window.McPanel.Base {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  // hass setter is inherited — triggers _render() + _boot() on first call
  set hass(hass) { super.hass = hass; }
  get hass()      { return super.hass; }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>${window.McPanel.Base.sharedStyles()}</style>
      <div class="wrap">
        <header class="page-header">
          <h1>My App</h1>
          <div class="header-actions">
            <span id="feedback" class="feedback"></span>
          </div>
        </header>
        <div id="cards"></div>
      </div>`;
  }

  async _boot() {
    // this._feedback("Saved", "ok")  — auto-clears after 3 s
    // this._feedback("Error", "err") — stays until cleared
  }
}
customElements.define("my-app-panel", MyPanel);
```

Inherited utilities:
- `this._esc(str)` — HTML-escape a value for safe `innerHTML`
- `this._feedback(msg, kind)` — `"ok"` / `"err"` / `"warn"` in `#feedback`
- `this._clearFeedback()` — immediately clear the feedback element
- `window.McPanel.Base.sharedStyles()` — full CSS string for shadow DOM

Copy the `www/` file into your HA config directory:

```
www/shared_libraries/   ← Libraries/Shared_HA_Helpers/HA_Component/www/shared_libraries/
```

---

## File structure

```
Libraries/Shared_HA_Helpers/HA_Component/
├── pyproject.toml
├── custom_components/shared_libraries/
│   ├── manifest.json      domain shared_libraries, deps: http, mqtt, core_configurator
│   ├── __init__.py        async_setup only — no config flow
│   ├── const.py           DOMAIN, MC_TOPIC_ROOT = "mc"
│   ├── http.py            async_request
│   ├── mqtt.py            mc_topic, async_subscribe, async_publish, async_subscribe_presence
│   └── fabric.py          status/# → device_registry + presence sensors
├── www/shared_libraries/
│   └── mc-panel.js        Lit McPanelBase + CSS tokens (built from panel_kit/)
├── panel_kit/             TypeScript sources — `npm run build` writes www/ outputs
└── tests/
    ├── conftest.py
    ├── test_http.py        fail-closed, URL assembly, bearer auth, errors
    ├── test_mqtt.py        mc_topic pure unit + subscribe/publish/presence
    └── test_fabric.py      presence parse + device/entity creation
```

Panel kit build:

```powershell
cd Libraries/Shared_HA_Helpers/panel_kit
npm install
npm run build
```

See `panel_kit/README.md`.
---

## Syntax

Stable identity strings for Ctrl+F rename / debug. Prefer changing the named
constant, then searching for leftover literals.

This README is the **fabric SoT** for `mc/{kind}/…` topic patterns. Apps that use the
fabric link here rather than duplicating the schema.

When you rename an identity string, update this section and `const.py` in the same PR.

### Rename blast radius

| Change this | Also touches |
|---|---|
| Domain `shared_libraries` | HA `custom_components/` folder, `manifest.json`, every integration `manifest.json` `dependencies` list |
| `MC_TOPIC_ROOT` (`mc`) | Every `mc_topic()` call site — changes all MQTT topics venue-wide |
| Fabric kind `tv` | AlleycatTV `MQTT_KIND`, BGC `KIND_TV`, Pi firmware, all `mc/tv/…` topics |
| Fabric kind `dnn` | DNN `MQTT_KIND`, BGC `KIND_DNN`, FDN firmware, all `mc/dnn/…` topics |
| Presence payload strings (`online`/`offline`/`unknown`) | `fabric.py` `PRESENCE_*` constants; FDN / Pi LWT payloads must match |

### Identity checklist

| Kind | Exact string | Constant / source |
|---|---|---|
| HA domain | `shared_libraries` | `DOMAIN` in `const.py` |
| MQTT topic root | `mc` | `MC_TOPIC_ROOT` in `const.py` |
| TV fabric kind | `tv` | used in `mc_topic("tv", …)`; named in AlleycatTV `MQTT_KIND` |
| DNN fabric kind | `dnn` | used in `mc_topic("dnn", …)`; named in DNN `MQTT_KIND` |
| Topic: device command | `mc/{kind}/cmd/device/{device_id}` | `resolve_cmd_segments(device_id=…)` → `mc_topic(kind, *segments, action)` |
| Topic: all / broadcast | `mc/{kind}/cmd/all/…`, `mc/{kind}/cmd/broadcast/{id}/…` | same helper — always `broadcast`, never `zone` |
| Topic: presence / LWT | `mc/{kind}/status/{device_id}` | `mc_topic(kind, "status", device_id)` |
| Topic: desired state | `mc/{kind}/desired/…` | `mc_topic(kind, "desired", …)` |
| Presence: online | `online` | `PRESENCE_ONLINE` in `fabric.py` |
| Presence: offline | `offline` | `PRESENCE_OFFLINE` in `fabric.py` |
| Presence: unknown | `unknown` | `PRESENCE_UNKNOWN` in `fabric.py` |
| Kind names | `tv` vs `dnn` | different kind segments; **same** `cmd/device/{id}` address grammar |

---

## Running tests

```powershell
cd Libraries/Shared_HA_Helpers/HA_Component
pytest
```

Or with coverage:

```powershell
pytest --cov=custom_components/shared_libraries --cov-report=term-missing
```

Requires `requirements_test.txt` installed at repo root. CI runs both this suite and the Core Configurator suite on every push.

**Coverage:** run with `--cov` as above. `core_configurator` is hard-imported (declared dependency); Shared Helpers tests add its HA_Component path in `tests/conftest.py`.
