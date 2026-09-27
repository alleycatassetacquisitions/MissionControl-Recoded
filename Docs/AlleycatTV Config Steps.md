# AlleycatTV Config Steps

Deploy AlleycatTV as three pieces in **dependency order**:

1. **Proxmox content server** (media + playlists — no MQTT)
2. **Home Assistant integration** (fabric presence + MQTT commands + Content Manager proxy)
3. **TV Pi SD cards** (distro tool on a prep PC)

Prerequisites: Home Assistant OS with **Mosquitto** + HA `mqtt` already working (Phase 5a in [`Home Assistant Config Steps.md`](Home%20Assistant%20Config%20Steps.md)). Shared HA Helpers must be on HA before AlleycatTV.

Home Assistant is the **only** MQTT command publisher. The content LXC must not open a Mosquitto client.

---

## Deployment order (checklist)

| Step | Where | Done when |
| --- | --- | --- |
| A. Content LXC | Proxmox host | `curl http://<IP>/health` → `"status":"ok","mqtt":false` |
| B. Core Configurator URL | HA | `alleycattv` = `http://<IP>` |
| C. HA integration + panels | HA | AlleycatTV + AlleycatTV Content in sidebar |
| D. Flash Pis | Prep PC | Each Pi publishes `mc/tv/status/{pi_id}` |
| E. Smoke test | HA | Play/stop Broadcast Group service publishes; Pi reacts |

---

## A. Install content server (Proxmox)

Run this on the **Proxmox node shell** (not inside a guest).

1. Copy `Docs/install-alleycattv-proxmox.sh` onto the host as `/root/install-alleycattv-proxmox.sh`.
2. Prefer a local checkout (no GitHub login):

```bash
chmod +x /root/install-alleycattv-proxmox.sh
ATV_SRC=/root/MissionControl/Apps/AlleycatTV/Server_Component \
  bash /root/install-alleycattv-proxmox.sh
```

3. Wait for `Done. CT … is ready.` Note the printed LAN IP.
4. Confirm from any PC on the LAN:

```bash
curl http://<printed-IP>/health
# → {"status":"ok","media_base":"…","mqtt":false}
```

5. Open `http://<printed-IP>/manage` for the content UI (ops). Operator day-to-day content work should go through the HA **AlleycatTV Content** panel (proxy).

### Defaults

| Setting | Default |
| --- | --- |
| Template | Ubuntu 24.04 standard |
| CPU / RAM / disk | 2 cores / 2 GB / 60 GB on `local-lvm` |
| Bridge | `vmbr0` (DHCP) |
| HTTP | nginx → uvicorn `:8000` on port **80** |
| Root password | `alleycat` |

### Optional overrides

| Variable | Default | Purpose |
| --- | --- | --- |
| `CTID` | next free | Container ID |
| `STORAGE` | `local-lvm` | Root disk |
| `DISK_SIZE` | `60` | GiB (raise for large libraries) |
| `ATV_SRC` | _(empty)_ | Host path to `Server_Component` (recommended) |
| `REPO_URL` | Mission Control git URL | Used only if `ATV_SRC` unset |
| `ROOT_PASSWORD` | `alleycat` | Console / SSH |
| `SKIP_CONFIRM` | `0` | `1` to skip countdown |

### Updating content-server code later

From your PC, sync `Server_Component` to the Proxmox host, then into the LXC (CT id from install output):

```powershell
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\AlleycatTV\Server_Component" root@<PROXMOX-IP>:/root/alleycattv-src
```

On the Proxmox host:

```bash
tar -C /root/alleycattv-src -cf - . | pct exec <CTID> -- tar -C /opt/alleycattv/server -xf -
pct exec <CTID> -- chown -R alleycattv:alleycattv /opt/alleycattv/server
pct exec <CTID> -- systemctl restart alleycattv-server nginx
curl http://<IP>/health
```

---

## B. Point Core Configurator at the content server

| Field | Value |
| --- | --- |
| Core Configurator key `alleycattv` / secret `cc_alleycattv` | `http://<printed-IP>` (no path) |

Seed via [`HomeAssist/secrets.yaml.example`](../HomeAssist/secrets.yaml.example) on first boot, or edit the Core Configurator sidebar after the entry exists.

---

## C. Deploy AlleycatTV onto Home Assistant

Mosquitto + Shared Helpers must already be installed (Phases 5a–5b).

```powershell
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\AlleycatTV\HA_Component\custom_components\alleycattv" root@<HA-IP>:/config/custom_components/
scp -r "z:\CodingProjects\Alleycat\MissionControl\Apps\AlleycatTV\HA_Component\www\alleycattv" root@<HA-IP>:/config/www/
```

Merge the AlleycatTV `panel_custom` blocks from [`HomeAssist/configuration.yaml`](../HomeAssist/configuration.yaml) into `/config/configuration.yaml`. Restart:

```bash
ha core restart
```

1. **Settings → Devices & services → Add integration → AlleycatTV** (install-only).
2. Confirm sidebar: **AlleycatTV** and **AlleycatTV Content**.
3. Hard-refresh the browser. Content panel Refresh should list media/groups via the HA proxy (no LAN `fetch`).

Playback services (examples):

- `alleycattv.play_broadcast_group` / `stop_broadcast_group` with `broadcast_group_id`
- `alleycattv.interrupt_pi` with `pi_id` + `file_url`

Topics: `mc/tv/…` — see [`MQTT Communication Principles.md`](MQTT%20Communication%20Principles.md).

---

## D. Flash TV Pi SD cards (prep PC)

Operators run the distro CLI on a Windows (or Linux) prep PC. Do **not** flash Broadcast Group membership (Phase 7).

1. Download **Raspberry Pi OS Lite (64-bit)** image.
2. Optionally bake player packages once onto a golden image (run `Client_Component/install.sh` on a reference Pi, then clone that image). Otherwise flash Lite and run `install.sh` over SSH after first boot; the distro tool still injects per-unit `alleycattv.env`.
3. From the Mission Control checkout:

```powershell
cd z:\CodingProjects\Alleycat\MissionControl\Apps\AlleycatTV\Client_Component\distro
py -3 flash.py --image path\to\raspios-lite-arm64.img
```

Dry run (no disk write):

```powershell
py -3 flash.py --dry-run --inject-only
```

4. Session flow:
   - Enter venue defaults once: content server URL, Mosquitto host/port/creds (HAOS broker)
   - Per card: Pi ID, hostname, optional Wi‑Fi
   - Select SD drive (tool refuses system disks / oversized disks)
   - Write image (Raspberry Pi Imager CLI when available) + inject `alleycattv.env` onto boot
   - Eject → insert next card → repeat

5. Boot each Pi on the venue LAN. Confirm in HA that `sensor.alleycattv_<pi>_presence` (or Devices list) shows **online**.

Pi MQTT broker must be the **Home Assistant Mosquitto** host (Phase 5a credentials), not a Proxmox Mosquitto LXC.

---

## E. Smoke test

1. Content: upload a short video via **AlleycatTV Content** or `/manage`; create a broadcast group + playlist id (e.g. `lobby`).
2. Temporarily set `ALLEYCATV_BROADCAST_GROUP_ID=lobby` on one Pi (env / `/etc/alleycattv.env`) so it can fetch that playlist until Phase 7 owns membership.
3. From HA: call `alleycattv.play_broadcast_group` with `broadcast_group_id: lobby`.
4. Pi plays; `media_player` / status JSON updates.
5. Call `stop_broadcast_group` — playback stops; retained desired topic updates.

---

## Ownership reminder

| Piece | Owns |
| --- | --- |
| HA `alleycattv` | MQTT commands, presence via fabric, Content Manager proxy |
| Proxmox content server | Files + playlists only |
| Pi client | mpv + subscribe `mc/tv/cmd/…` |
| Broadcast Group Controller | Membership + area placement — **Phase 7** |

App overview: [`Apps/AlleycatTV/README.md`](../Apps/AlleycatTV/README.md)  
HA phase slice: [`Home Assistant Config Steps.md` — Phase 6](Home%20Assistant%20Config%20Steps.md#phase-6--alleycattv-on-the-fabric)
