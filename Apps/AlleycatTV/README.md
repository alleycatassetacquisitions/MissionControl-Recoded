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
| Proxmox content server | Media files + playlists — **no MQTT client** |
| Pi client | mpv playback; subscribes to `mc/tv/cmd/…` |

Home Assistant is the **only** MQTT command publisher.

---

## Services (HA)

| Service | MQTT under `mc/tv/` |
|---|---|
| `play_broadcast_group` | `cmd/broadcast/{id}/play` + retained `desired/.../playback` |
| `stop_broadcast_group` | `cmd/broadcast/{id}/stop` + desired |
| `interrupt_broadcast_group` | `cmd/broadcast/{id}/interrupt` |
| `interrupt_pi` | `cmd/device/{pi_id}/interrupt` |
| `reload_playlist` | `cmd/broadcast/{id}/reload` |
| `set_volume_broadcast_group` | `cmd/broadcast/{id}/volume` |
| `cache_*` | `cmd/device/{pi_id}/cache_*` |

---

## Quick deploy pointers

| Step | Doc / command |
|---|---|
| Content LXC | [`Docs/install-alleycattv-proxmox.sh`](../../Docs/install-alleycattv-proxmox.sh) |
| Full checklist | [`Docs/AlleycatTV Config Steps.md`](../../Docs/AlleycatTV%20Config%20Steps.md) |
| HA scp + panels | Phase 6b in [`Home Assistant Config Steps.md`](../../Docs/Home%20Assistant%20Config%20Steps.md#phase-6--alleycattv-on-the-fabric) |
| Mosquitto login | Phase 5a — venue `alleycatTV` / `alleycat` (must **Save** in add-on) |
| Pi SD flash (plug-and-play) | `Client_Component/distro/flash.py` — Config Steps **§ D** (`.img.xz` OK; cloud-init + player bundle) |

Set Core Configurator key `alleycattv` to the content server URL (`cc_alleycattv` in secrets).

Pi flash session must use the same Mosquitto user/password as Phase 5a. MQTT **`rc=5`** on the Pi means auth rejected — the endpoint will not show in the AlleycatTV panel until that is fixed.

---

## Tests

```powershell
cd Apps\AlleycatTV\HA_Component; py -3 -m pytest
cd Apps\AlleycatTV\Server_Component; py -3 -m pytest
cd Apps\AlleycatTV\Client_Component\distro; py -3 -m pytest
```

HA integration tests that need the Home Assistant fixture run on Unix/CI (`fcntl`).
