# Shared HA Helpers

Infrastructure library for Mission Control integrations. Not an operator-facing app — no sidebar, no config flow, no UI.

**Code:** `shared_libraries`  
**Path:** `Libraries/Shared_HA_Helpers/HA_Component/`  
**HA shape:** `custom_component`, `config_flow: false`, no sidebar

---

## What this ships

Three modules other integrations import directly:

| Module | What it provides |
|---|---|
| `http.py` | `async_request` — bearer-auth HTTP via HA's managed session + Core Configurator URL |
| `mqtt.py` | `mc_topic` topic builder, `async_subscribe` / `async_publish` / `async_subscribe_presence` wrappers |
| `www/shared_libraries/mc-panel.js` | CSS design tokens + `McPanelBase` class for `extra_module_url` panels |

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
from custom_components.shared_libraries.http import async_request

# GET with no auth — returns None if no URL is configured (fail-closed)
response = await async_request(hass, "gbn", "GET", "/api/posters")
if response is None:
    return  # no URL set, fail cleanly — never fall back to a hardcoded IP

data = await response.json()

# POST with bearer token (token usually from Core Configurator get_extra)
response = await async_request(
    hass, "master_control_server", "POST", "/players",
    token=my_token,
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
    async_subscribe,
    async_publish,
    async_subscribe_presence,
)

# Topic builder (pure function — no hass needed)
topic = mc_topic("dnn", "cmd", device_id)
# → "mc/dnn/cmd/<device_id>"

mc_topic("tv", "cmd", "all")
# → "mc/tv/cmd/all"

mc_topic("dnn", "cmd", "broadcast", group_id)
# → "mc/dnn/cmd/broadcast/<group_id>"

# Subscribe — returns an unsubscribe callable
unsub = await async_subscribe(hass, "dnn", "cmd", device_id, callback=handle_msg)

# Publish
await async_publish(hass, "tv", "cmd", "all", payload=json.dumps(cmd))

# Presence / LWT — subscribes to mc/{kind}/status/{device_id}
unsub = await async_subscribe_presence(hass, "dnn", device_id, callback=on_presence)
# payload is typically "online" or "offline"
```

**Rules:**
- Always build topics through `mc_topic`. Never hard-code topic strings.
- Use `"broadcast"` as the group-command segment. Never use `"zone"`.
- Never open a private MQTT client inside an integration. These wrappers delegate to HA's `mqtt` component.

### 4. Panel kit (frontend)

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
│   └── mqtt.py            mc_topic, async_subscribe, async_publish, async_subscribe_presence
├── www/shared_libraries/
│   └── mc-panel.js        McPanelBase + CSS tokens
└── tests/
    ├── conftest.py
    ├── test_http.py        12 tests — fail-closed, URL assembly, bearer auth, errors
    └── test_mqtt.py        24 tests — mc_topic pure unit + subscribe/publish/presence
```

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

**Coverage baseline (Phase 3):** 93% overall. The two uncovered lines are the `get_url is None` error-log branch in `http.py` — only reachable when `core_configurator` is missing, which cannot happen in a healthy HA install.
