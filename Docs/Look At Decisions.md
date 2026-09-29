# Look At Decisions

What Mission Control used, skipped, and deferred for Phase 10 (Lit + TypeScript panel kit, then Alleycat dashboard shell). Aesthetic choices originated in legacy [ProjectMissionControl](../../ProjectMissionControl) and were re-validated here against Design Principles §7 (prefer community tools that fit).

## Used


| Candidate                                         | Why                                                                                                                                                                                                  |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Lit + TypeScript**                              | HA’s own frontend stack. One typed `McPanelBase` (`Libraries/Shared_HA_Helpers/panel_kit`) with a Vite/esbuild build to static `www/`. Same design tokens and feedback helpers as the pre-Lit kit.   |
| **Vite + esbuild**                                | Workstation build only; HAOS never runs Node. `mc-panel.js` embeds Lit once; feature panels are IIFE bundles that extend `window.McPanel.Base`.                                                      |
| **HACS custom-sidebar**                           | Proven in ProjectMissionControl for renaming the sidebar/header. Needs both `HomeAssist/www/custom-sidebar-config.yaml` (`title: "Mission Control"`) **and** `/hacsfiles/custom-sidebar/custom-sidebar-plugin.js` on `frontend.extra_module_url` (YAML alone does nothing). |
| **HACS card-mod**                                 | Required for Alleycat theme `card-mod-theme` / `card-mod-root` / `card-mod-card` / `card-mod-view` scanline and card chrome on Lovelace.                                                             |
| **Alleycat HA theme**                             | Port of `ProjectMissionControl/.../themes/alleycat.yaml` → `HomeAssist/themes/alleycat.yaml`. Cyan `#00e5ff`, magenta `#ff2bd6`, dark surfaces, Share Tech Mono, HA 2026 form tokens + `modes.dark`. |
| **alleycat-scanlines.js**                         | Extra CRT overlay + dark native `<input>` fills (not expressible in theme YAML alone). Loaded via `frontend.extra_module_url`.                                                                       |
| **McPanel shared chrome**                         | Folded former `alleycat-panel.css` neon header/card rules into Lit `sharedStyles` so every panel shares one Alleycat look without a second competing stylesheet as the source of truth.              |
| **HA Areas**                                      | Already the venue placement model (Phase 7 Broadcast Group Controller).                                                                                                                              |
| **HA Core Proxmox VE**                            | Already owns monitoring sensors/buttons (Phase 9); Bug Buster stays console + MQTT spy + companion health.                                                                                           |
| **xterm.js**                                      | Already vendored in Bug Buster for termproxy; kept.                                                                                                                                                  |
| **pytest-homeassistant-custom-component**         | Already the HA test runner (Phase 2+); unchanged by Phase 10.                                                                                                                                        |
| **async_get_clientsession / shared HTTP helpers** | Already the integration HTTP path; panels still talk only through HA.                                                                                                                                |
| **Official Mosquitto add-on**                     | Venue broker (Phase 5); not aesthetic, still the rule.                                                                                                                                               |




## Not used


| Candidate                                             | Why not                                                                                                                                                   |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **kiosk-mode**                                        | Operator console is multi-panel `panel_custom`, not a locked single Lovelace view.                                                                        |
| **hass_ingress / webpage dashboard**                  | Would iframe companion manage UIs. Mission Control rejected that pattern: integrations own HTTP; panels call HA.                                          |
| **browser_mod**                                       | Never used in ProjectMissionControl; no Phase 10 popup/kiosk requirement.                                                                                 |
| **Mushroom / Bubble / Button / Layout Card**          | Lovelace card ecosystems are not the operator workflow surface. Sidebar panels remain the UI.                                                             |
| **Vendoring custom-sidebar / card-mod into git**      | HACS is the supported install path and keeps those plugins updated; we only vendor Alleycat-owned assets (theme, scanlines, sidebar title yaml, Lit kit). |
| **home-assistant-js-websocket as a panel dependency** | Panels still use `hass.callWS` / `hass.callService`. Typed WS client stays optional until a panel outgrows those wrappers.                                |
| **Stock / light HA theme**                            | Rejected for in-universe ops; Alleycat cyberpunk is the product look.                                                                                     |
| **Sidebar title “Alleycat Registration”**             | Legacy ProjectMissionControl title. Product name is **Mission Control**.                                                                                  |
| **Second neon stylesheet as SoR**                     | Per-app `alleycat-panel.css` copies may remain as optional `@import` on large legacyPaint panels; McPanel Lit styles are the shared contract.             |




## Deferred


| Candidate                                                            | Notes                                                                                                                                                                                                                                                    |
| -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **MQTT discovery**                                                   | Fabric already creates devices via custom integrations; revisit only if firmware moves to discovery JSON.                                                                                                                                                |
| **ESPHome + ESP-NOW**                                                | FDN firmware concern; not dashboard chrome.                                                                                                                                                                                                              |
| **HA Labels for Broadcast Groups**                                   | Spiked and **rejected** in Phase 7 (exclusive single-group membership). Areas stay for placement; BGC Store owns membership.                                                                                                                             |
| **python-mpv / Anthias**                                             | AlleycatTV player/signage decisions from Phase 6; unchanged.                                                                                                                                                                                             |
| **photobooth-app / MomentoBooth**                                    | GBN capture research only; poster identity stays GBN + MCS.                                                                                                                                                                                              |
| **OpenAPI client generation for MCS**                                | Useful if Central publishes a spec; no shell/aesthetic impact.                                                                                                                                                                                           |
| **Full Lit** `render()` **rewrite of AlleycatTV / GBN / Bug Buster** | Those panels run on Lit `McPanelBase` with `legacyPaint` (imperative `_render` preserved). Smaller panels (Core Configurator, Registration, DNN, BGC) use Lit templates. Completing the large-panel template ports is follow-up, not a Phase 10 blocker. |




## MQTT vs HTTP (device fabric)

Mission Control uses **both**. The split is by shape of the hop, not by preference for one protocol.

| Hop | Protocol | Why that one |
| --- | --- | --- |
| HA ↔ FDN / AlleycatTV Pi (commands, presence, membership) | **MQTT** | Pub/sub fabric: one publish can hit this device, `all`, or a Broadcast Group without HA holding per-device HTTP sessions or knowing LAN IPs. |
| HA ↔ MCS / AlleycatTV content / GBN / Proxmox APIs | **HTTP** | Request/response against a known companion URL + token (Core Configurator). Files, roster CRUD, and health checks are client/server, not fan-out. |
| FDN ↔ Central Server | **HTTP** | Central’s existing API. HA never talks to Central; MCS is the only Central HTTP adapter. |

### Why not HTTP for venue devices

- **Fan-out.** Paging every FDN or stopping every lobby TV is one MQTT topic (`cmd/all` or `cmd/broadcast/{id}`), not N outbound HTTP calls and not a list of device IPs in HA.
- **Presence without polling.** Status + LWT on the fabric become HA devices and `online` / `offline` / `unknown` entities. HTTP would need each Pi/FDN to run a server (or HA to poll), plus custom offline detection.
- **Dynamic membership.** Broadcast Group Controller assigns groups after a node appears; firmware resubscribes. That is awkward as per-device HTTP config and wrong as flash-time hardcoding.
- **Desired state while offline.** e.g. `mc/tv/desired/broadcast/{id}/playback` so a Pi that was powered off still joins the group’s current play/stop/volume when it reconnects. HTTP request/response does not give that “last known desired” for free.
- **Platform fit.** Official Mosquitto add-on + HA `mqtt` integration is the supported client path. A second pattern (each device an HTTP endpoint the panel `fetch`es, or a private MQTT client per app) fights the mapping in `Home Assistant Mapping.md`.

### What stays HTTP on purpose

Companion services are authoritative file/HTTP adapters. Home Assistant is the **client** (`async_get_clientsession` / shared helpers). The AlleycatTV **content** LXC stays HTTP-only and must **not** open an MQTT client — HA alone publishes TV commands on the fabric.

Topic ownership and command shapes: [`MQTT Communication Principles.md`](MQTT%20Communication%20Principles.md).


## Load order (shell)

Required `frontend.extra_module_url` order after Phase 10. Keep a **single** `frontend:` block in `/config/configuration.yaml`; prepend shell URLs into the existing list (do not duplicate `frontend:` / `themes:` / `extra_module_url:`):

1. `/hacsfiles/custom-sidebar/custom-sidebar-plugin.js`
2. `/hacsfiles/lovelace-card-mod/card-mod.js`
3. `/local/alleycat-scanlines.js`
4. `/local/shared_libraries/mc-panel.js`
5. `/local/core_configurator/core-configurator-client.js`

Deploy steps: `Home Assistant Config Steps.md`.