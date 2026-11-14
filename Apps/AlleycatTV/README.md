# AlleycatTV

Home Assistant face of AlleycatTV TV endpoints on the MQTT fabric, plus a
Proxmox content server and Pi client.

**Code:** `alleycattv`  
**Paths:**
- HA: `Apps/AlleycatTV/HA_Component/`
- Content server: `Apps/AlleycatTV/Server_Component/`
- Pi client: `Apps/AlleycatTV/Client_Component/`
- SD distro: `Apps/AlleycatTV/Client_Component/distro/`

**HA shape:** config entry + sidebar panels + `media_player` + MQTT services (`local_push`)

**Deploy (start here):** [`Docs/AlleycatTV Config Steps.md`](../../Docs/AlleycatTV%20Config%20Steps.md)

---

## Ownership

| Piece | Owner |
|---|---|
| Official **Mosquitto** add-on + HA `mqtt` | Broker + command path |
| Shared HA Helpers fabric | Presence (`mc/tv/status/#`) |
| AlleycatTV HA integration | Playback commands, media_player, Content Manager proxy |
| Core Configurator `rtsp` | Live RTSP URL / label / enabled (not Content Manager) |
| Proxmox content server | Media files + playlists — **no MQTT client** |
| Pi client | mpv playback; subscribes to `mc/tv/cmd/…` |

Home Assistant is the **only** MQTT command publisher.

---

## Services (HA)

| Service | MQTT under `mc/tv/` |
|---|---|
| `play_broadcast_group` | cmd nudge + retained desired `state=playing` (desired is authority) |
| `stop_broadcast_group` | cmd nudge + retained desired `state=stopped` |
| `interrupt_broadcast_group` | `cmd/broadcast/{id}/interrupt` (nudge only) |
| `interrupt_pi` | `cmd/device/{pi_id}/interrupt` (nudge only) |
| `reload_playlist` | `cmd/broadcast/{id}/reload` (nudge only) |
| `set_volume_broadcast_group` | cmd nudge + merge `volume` into retained desired (does not force playing) |
| `cache_*` | `cmd/device/{pi_id}/cache_*` |

**Panels:** AlleycatTV (live control) + AlleycatTV Content (full library/playlists via HA proxy). Placement and Broadcast Group membership: **Broadcast Group Controller**.

**Webpage items:** Content can add scoreboard URLs or **+ Poster cycle** (needs Core Configurator `gbn`). Poster cycle upserts a `webpage` item pointing at GBN `/poster-cycle` for **24h** (`duration: 86400`) — GBN rotates **active-event** posters every 30s inside Chromium; AlleycatTV advances to the next playlist item when that slot expires (set the active Event in Game Master first — see [`Docs/GBN Config Steps.md`](../../Docs/GBN%20Config%20Steps.md) § C).

**Membership:** Create playlist buckets in **AlleycatTV Content**; assign them in **Broadcast Groups** (dropdown). Pis learn `broadcast_group_id` from `mc/tv/cmd/device/{id}/membership` (Phase 7). Env `ALLEYCATV_BROADCAST_GROUP_ID` is lab bootstrap only. Retire or reuse a Pi ID via Broadcast Groups → **Remove from fabric** (offline only).

---

## Quick deploy pointers

| Step | Doc / command |
|---|---|
| Content LXC | [`ProxmoxInstallFiles/install-alleycattv-proxmox.sh`](../../ProxmoxInstallFiles/install-alleycattv-proxmox.sh) |
| Full checklist | [`Docs/AlleycatTV Config Steps.md`](../../Docs/AlleycatTV%20Config%20Steps.md) |
| HA scp + panels | Phase 6b in [`Home Assistant Config Steps.md`](../../Docs/Home%20Assistant%20Config%20Steps.md#phase-6--alleycattv-on-the-fabric) |
| Mosquitto login | Phase 5a — venue `alleycatTV` / `alleycat` (must **Save** in add-on) |
| Pi SD flash (plug-and-play) | `Client_Component/distro/flash.py` — Config Steps **§ D** (`.img.xz` OK; cloud-init + player bundle) |

Set Core Configurator key `alleycattv` to the content server URL (`cc_alleycattv` in secrets).

Pi flash session must use the same Mosquitto user/password as Phase 5a. MQTT **`rc=5`** on the Pi means auth rejected — the endpoint will not show in the AlleycatTV panel until that is fixed.

---

## Syntax

Stable identity strings for Ctrl+F rename / debug. Prefer changing the named
constant, then searching for leftover literals.

When you rename an identity string, update this section and `const.py` in the same PR.

### Rename blast radius

| Change this | Also touches |
|---|---|
| MQTT kind `tv` | BGC `KIND_TV` + `KIND_DOMAIN` map, fabric `mc/tv/status/#` subscriptions, Pi firmware MQTT topics, all AlleycatTV MQTT command topics |
| CC key `alleycattv` | Core Configurator catalog + `KEY_ALLEYCATTV`, `KEY_ALLEYCATTV` in DNN const, Bug Buster `HEALTH_KEYS`, AlleycatTV proxy routes, install scripts |
| Domain `alleycattv` | HA `custom_components/` folder, `manifest.json`, entity_id prefix, panel JS file refs, `www/alleycattv/` |

### Identity checklist

| Kind | Exact string | Constant / source |
|---|---|---|
| HA domain | `alleycattv` | `DOMAIN` in `const.py` |
| MQTT fabric kind | `tv` | `MQTT_KIND` in `const.py` |
| CC service key | `alleycattv` | `KEY_ALLEYCATTV` in `const.py` |
| CC key (RTSP source) | `rtsp` | `KEY_RTSP` in `const.py` |
| WS namespace | `alleycattv/get_devices` | `WS_GET_DEVICES` in `const.py` — areas/placement via `broadcast_group_controller` |
| Panel url_path (player) | `alleycattv` | bare literal in `HomeAssist/configuration.yaml` |
| Panel url_path (content) | `alleycattv-content` | bare literal in `HomeAssist/configuration.yaml` |
| MQTT topic root | `mc/tv/cmd/…`, `mc/tv/status/…`, `mc/tv/desired/…` | built via `mc_topic("tv", …)` in `Shared_HA_Helpers` |

---

## Tests

```powershell
cd Apps\AlleycatTV\HA_Component; py -3 -m pytest
cd Apps\AlleycatTV\Server_Component; py -3 -m pytest
cd Apps\AlleycatTV\Client_Component\distro; py -3 -m pytest
```

HA integration tests that need the Home Assistant fixture run on Unix/CI (`fcntl`).
